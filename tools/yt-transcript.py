#!/usr/bin/env python3
"""Pull a YouTube video transcript for knowledge-base ingestion.

Downloads the video's English subtitles (manual if present, else auto-generated)
with yt-dlp, cleans the rolling-caption duplicates into timestamped paragraphs,
and writes a transcript .txt whose header carries the creator metadata needed
for the **Source:** attribution line required by CLAUDE.md / CONTRIBUTING.md.

Usage:
    python tools/yt-transcript.py <youtube-url> [--output <dir>] [--yt-dlp <path>]

Output:
    <output-dir>/<video-id>-transcript.txt

The default output directory is /tmp: transcripts are working material for KB
distillation, not framework content, and must not be committed to the repo.

Requires a CURRENT yt-dlp (YouTube breaks old versions). If the system yt-dlp
fails, install the latest into a venv and point --yt-dlp at it:
    python3 -m venv /tmp/ytdlp-venv && /tmp/ytdlp-venv/bin/pip install -U yt-dlp
    python tools/yt-transcript.py <url> --yt-dlp /tmp/ytdlp-venv/bin/yt-dlp

After running, fetch the creator's homepage (the "Creator homepage" URL in the
transcript header) and record the creator's name, channel, and site links —
that information feeds the **Source:** line of any KB section derived from
the video. The creator's effort is part of this project's knowledge; credit it.
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PARAGRAPH_SECONDS = 30  # group caption lines into ~30 s paragraphs


def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        sys.exit(f"command failed: {' '.join(cmd)}")
    return result.stdout


def clean_vtt(vtt_text):
    """Collapse YouTube's rolling auto-captions into timestamped paragraphs."""
    cue_re = re.compile(
        r'(\d{2}:\d{2}:\d{2}\.\d{3}) --> \d{2}:\d{2}:\d{2}\.\d{3}.*\n'
        r'((?:.+\n?)*?)(?=\n|\Z)')
    entries = []
    last_line = None
    for m in cue_re.finditer(vtt_text):
        start, block = m.group(1), m.group(2)
        block = re.sub(r'<[^>]+>', '', block)  # strip word-timing tags
        for line in block.splitlines():
            line = line.strip()
            if not line or line == '[Music]':
                continue
            if line == last_line:  # rolling window repeats each line once
                continue
            last_line = line
            entries.append((start, line))

    def secs(ts):
        h, m_, s = ts.split(':')
        return int(h) * 3600 + int(m_) * 60 + float(s)

    paragraphs, para, para_start = [], [], None
    for start, text in entries:
        if para_start is None:
            para_start = start
        para.append(text)
        if secs(start) - secs(para_start) >= PARAGRAPH_SECONDS:
            paragraphs.append((para_start, ' '.join(para)))
            para, para_start = [], None
    if para:
        paragraphs.append((para_start, ' '.join(para)))

    out = []
    for start, text in paragraphs:
        ts = start[3:8] if start.startswith('00:') else start[:8]
        out.append(f'[{ts}] {text}')
    return '\n\n'.join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('url', help='YouTube video URL')
    ap.add_argument('--output', default='/tmp',
                    help='output directory (default: /tmp — keep transcripts out of the repo)')
    ap.add_argument('--yt-dlp', default='yt-dlp', help='path to yt-dlp binary')
    args = ap.parse_args()

    meta = json.loads(run([
        args.yt_dlp, '--skip-download', '-J', '--no-playlist', args.url]))
    video_id = meta['id']
    creator_home = meta.get('uploader_url') or meta.get('channel_url') or ''

    with tempfile.TemporaryDirectory() as tmp:
        run([args.yt_dlp, '--skip-download', '--write-subs', '--write-auto-subs',
             '--sub-langs', 'en.*', '--sub-format', 'vtt',
             '-o', f'{tmp}/{video_id}', args.url])
        vtts = sorted(Path(tmp).glob(f'{video_id}*.vtt'))
        if not vtts:
            sys.exit('no English subtitles available for this video')
        # prefer manual subs ('.en.vtt') over auto ('.en-orig.vtt') if both exist
        vtt = min(vtts, key=lambda p: len(p.name))
        body = clean_vtt(vtt.read_text(encoding='utf-8'))

    upload_date = meta.get('upload_date') or ''
    if len(upload_date) == 8:
        upload_date = f'{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}'

    header = '\n'.join([
        f"Title:            {meta.get('title', '')}",
        f"Creator:          {meta.get('channel', meta.get('uploader', ''))}",
        f"Creator homepage: {creator_home}",
        f"Video URL:        https://youtu.be/{video_id}",
        f"Uploaded:         {upload_date}",
        f"Duration:         {meta.get('duration_string', '')}",
        "Transcript:       YouTube captions, cleaned by tools/yt-transcript.py",
    ])

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f'{video_id}-transcript.txt'
    out_path.write_text(f'{header}\n\n---\n\n{body}\n', encoding='utf-8')

    print(f'wrote {out_path}')
    print(f'\nNEXT STEP (attribution): visit the creator homepage —\n'
          f'  {creator_home}\n'
          f'and record the creator name, channel, and any site links for the\n'
          f'**Source:** line of the KB section (see CLAUDE.md "Source Attribution").')


if __name__ == '__main__':
    main()
