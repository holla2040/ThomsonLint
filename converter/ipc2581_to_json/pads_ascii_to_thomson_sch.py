#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, json, re, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "pads-ascii-adapter-0.2"


def now_iso(): return datetime.now(timezone.utc).isoformat()

def normalize_bom_headers(headers):
    m = {}
    for h in headers:
        n = re.sub(r"[^a-z0-9]", "", h.lower())
        if n in {"designator","refdes","refdesig","reference","references","item","partreference"}: m[h] = "refdes"
        elif n in {"value","comment","componentvalue"}: m[h] = "value"
        elif n in {"mpn","manufacturerpartnumber","manufacturerpn","partnumber","manufacturerpart","mfrpartnumber"}: m[h] = "part_number"
        elif n in {"manufacturer","mfr","mfg"}: m[h] = "manufacturer"
        elif n in {"description","componentdescription","libref"}: m[h] = "description"
        elif n in {"footprint","pattern","pcbfootprint","package"}: m[h] = "footprint"
        elif n in {"quantity","qty"}: m[h] = "quantity"
        else: m[h] = h
    return m

def expand_refdes_token(tok: str):
    tok = tok.strip()
    m = re.match(r"^([A-Za-z]+)(\d+)-([A-Za-z]+)?(\d+)$", tok)
    if m and (m.group(3) in (None, m.group(1))):
        p = m.group(1); a = int(m.group(2)); b = int(m.group(4))
        if a <= b and (b-a) < 500: return [f"{p}{i}" for i in range(a,b+1)]
    return [tok]

def parse_bom_csv(path: Path):
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        nm = normalize_bom_headers(r.fieldnames or [])
        for row in r:
            o = {nm[k]: v.strip() for k,v in row.items() if k is not None}
            refraw = o.get("refdes", "")
            toks = re.split(r"[,\s]+", refraw)
            refs = []
            for t in toks:
                if t: refs.extend(expand_refdes_token(t))
            o["refdes_list"] = refs
            rows.append(o)
    return rows

def parse_pads_ascii(netlist_path: Path):
    """Parse a PADS ASCII netlist (.asc or .net) into components and nets.

    Standard mode (.asc with *PART* block): populates footprints from the
    *PART* section.  Inference mode (.net or missing *PART*): infers the
    component list from net nodes; footprint is null and "footprint" is added
    to each component's unresolved_fields list.

    Returns (components, nets, warnings, unsupported, parse_mode) where
    parse_mode is "standard" or "inference".
    """
    text = netlist_path.read_text(encoding="utf-8", errors="ignore")
    lines = [l.rstrip() for l in text.splitlines()]
    components: dict = {}
    nets: dict = {}
    warnings: list = []
    unsupported: list = []
    current_net = None
    mode = "header"        # header | parts | nets
    has_part_block = False

    # Pin token: REF.PIN where PIN may contain letters, digits, hyphens, underscores,
    # and forward slashes (e.g. CN3.A4/B9 for USB-C dual-orientation pads).
    _NODE_PAT = re.compile(r'^([A-Za-z]+\d+)\.([A-Za-z0-9_\-/]+)$')

    def _add_node(ref: str, pin: str, line_num: int) -> None:
        nets[current_net].append({"refdes": ref, "pin": pin})
        components.setdefault(ref, {
            "refdes": ref, "value": None, "part_number": None,
            "description": None, "footprint": None, "pins": [], "bom": {},
            "source": {"source_element": "node_record", "line": line_num},
        })
        components[ref]["pins"].append(
            {"pin": pin, "net": current_net, "name": None, "electrical_type": "unknown"}
        )

    if not any("*NET*" in l.upper() for l in lines):
        warnings.append("no explicit *NET* section marker found")

    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue

        if s.startswith("*"):
            upper = s.upper()
            if upper.startswith("*NET*"):
                mode = "nets"
                current_net = None
            elif upper.startswith("*PART*") or upper.startswith("*COMP*"):
                mode = "parts"
                has_part_block = True
            elif upper.startswith("*SIGNAL*"):
                # *SIGNAL* NETNAME [optional inline node tokens]
                rest = s[len("*SIGNAL*"):].strip()
                tokens = rest.split()
                if tokens:
                    current_net = tokens[0]
                    nets.setdefault(current_net, [])
                    for tok in tokens[1:]:  # handle uncommon inline nodes
                        m = _NODE_PAT.match(tok)
                        if m:
                            _add_node(m.group(1), m.group(2), i + 1)
                elif mode == "nets":
                    warnings.append(f"empty *SIGNAL* marker at line {i+1}")
            elif upper in ("*PADS-PCB*", "*PADS-NETLIST*") or upper.startswith("*END*"):
                pass  # known file-level markers; no action needed
            else:
                unsupported.append(f"unsupported section marker at line {i+1}: {s}")
            continue

        if mode == "parts":
            # Form 1: COMP/PART keyword with key=value pairs (test fixtures, some tools)
            mcomp = re.match(r"^(?:COMP|PART)\s+([A-Za-z]+\d+)\s*(.*)$", s, re.I)
            if mcomp:
                ref = mcomp.group(1)
                rest = mcomp.group(2)
                c = components.setdefault(ref, {
                    "refdes": ref, "value": None, "part_number": None,
                    "description": None, "footprint": None, "pins": [], "bom": {},
                    "source": {"source_element": "component_record", "line": i + 1},
                })
                for kv in re.findall(r"([A-Za-z_]+)=([^\s]+)", rest):
                    k, v = kv[0].lower(), kv[1]
                    if k in {"value", "val"}:
                        c["value"] = v
                    elif k in {"footprint", "package", "pattern"}:
                        c["footprint"] = v
                    elif k in {"mpn", "partnumber", "pn"}:
                        c["part_number"] = v
                continue
            # Form 2: plain "REFDES FOOTPRINT" pairs (standard PADS .asc)
            toks = s.split()
            if len(toks) >= 2 and re.match(r'^[A-Za-z]+\d+$', toks[0]):
                ref, fp = toks[0], toks[1]
                c = components.setdefault(ref, {
                    "refdes": ref, "value": None, "part_number": None,
                    "description": None, "footprint": None, "pins": [], "bom": {},
                    "source": {"source_element": "component_record", "line": i + 1},
                })
                c["footprint"] = fp
            continue

        if mode == "nets":
            # Legacy NET keyword (some older tools / test fixtures)
            mnet = re.match(r"^NET\s+([^\s]+)", s, re.I)
            if mnet:
                current_net = mnet.group(1)
                nets.setdefault(current_net, [])
                continue
            # Space-separated node list (one or more REF.PIN tokens per line)
            if current_net is not None:
                for tok in s.split():
                    m = _NODE_PAT.match(tok)
                    if m:
                        _add_node(m.group(1), m.group(2), i + 1)

    # ------------------------------------------------------------------
    # Post-processing: determine parse mode and annotate missing footprints
    # ------------------------------------------------------------------
    is_inference = not has_part_block or netlist_path.suffix.lower() == ".net"
    parse_mode = "inference" if is_inference else "standard"
    if is_inference:
        warnings.append(
            "inference mode: *PART* block absent — component footprints are unknown"
        )
    # Any component with a null footprint gets unresolved_fields annotation
    # (covers all components in inference mode and any orphan in standard mode).
    for c in components.values():
        if c.get("footprint") is None:
            uf = c.setdefault("unresolved_fields", [])
            if "footprint" not in uf:
                uf.append("footprint")

    return components, nets, warnings, unsupported, parse_mode

def merge_bom_into_components(components: dict, bom_rows: list[dict[str, Any]]):
    warnings, matched, unmatched = [], 0, []
    comp_refs = set(components.keys()); seen = set()
    for row in bom_rows:
        for ref in row.get("refdes_list", []):
            if ref in components:
                matched += 1; seen.add(ref)
                components[ref]["bom"] = row
                for fld in ["value","part_number","description","footprint"]:
                    if not components[ref].get(fld) and row.get(fld): components[ref][fld] = row.get(fld)
            else:
                unmatched.append(ref)
    for ref in sorted(unmatched): warnings.append(f"BOM refdes not found in netlist: {ref}")
    for ref in sorted(comp_refs-seen): warnings.append(f"Netlist component missing from BOM: {ref}")
    return {"warnings": warnings, "matched": matched, "unmatched": unmatched}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--netlist", required=True); ap.add_argument("--bom"); ap.add_argument("--project", required=True); ap.add_argument("--output", default="exports")
    ap.add_argument("--erc"); ap.add_argument("--strict", action="store_true"); ap.add_argument("--warnings-as-errors", action="store_true"); ap.add_argument("--pretty", action="store_true"); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--report-only", action="store_true"); ap.add_argument("--inspect", action="store_true"); ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    net = Path(args.netlist)
    if not net.exists(): print("ERROR: netlist missing", file=sys.stderr); return 2
    if net.stat().st_size == 0:
        print("ERROR: netlist is empty", file=sys.stderr); return 2
    components, nets, warnings, unsupported, parse_mode = parse_pads_ascii(net)
    if args.inspect: print(f"Inspect: components={len(components)} nets={len(nets)}")
    bom_rows = []
    if args.bom:
        b = Path(args.bom)
        if not b.exists(): print("ERROR: BOM missing", file=sys.stderr); return 2
        bom_rows = parse_bom_csv(b)
        mr = merge_bom_into_components(components, bom_rows)
        warnings.extend(mr["warnings"])
    net_list = [{"name": n, "nodes": nodes, "node_count": len(nodes), "source": {"source_element": "NET"}} for n, nodes in nets.items()]
    pin_count = sum(len(c["pins"]) for c in components.values())
    if len(components)==0: warnings.append("zero components extracted")
    if len(net_list)==0: warnings.append("zero nets extracted")
    if pin_count==0: warnings.append("zero pin/nodes extracted")
    for n in net_list:
        if n["node_count"] == 1: warnings.append(f"single-node net: {n['name']}")
    export = {"metadata": {"project": args.project, "source_format": "pads_ascii_netlist", "parse_mode": parse_mode, "source_files": {"netlist": str(net), "bom": args.bom, "erc": args.erc}, "converter": VERSION, "conversion_timestamp": now_iso(), "warnings": warnings, "limitations": ["PADS ASCII netlist provides connectivity, not full schematic semantics."]}, "components": list(components.values()), "nets": net_list, "erc": {"source_file": args.erc, "text": Path(args.erc).read_text(encoding='utf-8', errors='ignore') if args.erc and Path(args.erc).exists() else None, "parsed_findings": []}, "analysis": {"schematic_only_fields_missing": ["pin_electrical_type","symbol_graphics","sheet_hierarchy","ERC_semantics"]}, "aerospace_hi_rel_summary": {"note": "Aerospace fields (component_mass_g, solder_alloy, lead_finish) are extracted per-component from BOM CSV when present. Use thomson_bundle_converter.py for full extraction with JESD201 suffix detection.", "data_source_required_fields": ["component_mass_g", "solder_alloy", "lead_finish"]}}
    report = {"inputs": {"netlist": str(net), "bom": args.bom}, "counts": {"schematic_components": len(components), "schematic_nets": len(net_list), "schematic_pins_nodes": pin_count, "bom_rows": len(bom_rows)}, "warnings": warnings, "errors": [], "unsupported_features": unsupported}
    out = Path(args.output)
    if not args.dry_run:
        out.mkdir(parents=True, exist_ok=True)
    ind=2 if args.pretty else None
    if not args.dry_run and not args.report_only:
        (out / f"{args.project}-thomson-export-sch.json").write_text(json.dumps(export, indent=ind), encoding="utf-8")
    if not args.dry_run:
        (out / f"{args.project}-conversion-report.json").write_text(json.dumps(report, indent=ind), encoding="utf-8")
        (out / f"{args.project}-conversion-report.md").write_text("# PADS Conversion Report\n", encoding="utf-8")
    if args.warnings_as_errors and warnings: return 1
    if args.strict and any(w.startswith("zero ") for w in warnings): return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
