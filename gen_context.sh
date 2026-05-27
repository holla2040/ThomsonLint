#!/bin/bash
# Generates review_instructions.txt — a single-file bundle for upload to web AIs
# (Gemini, Claude.ai, ChatGPT, etc.). This path is untested by the maintainers.
# The tested driver is Claude Code, which reads docs/REVIEWER_INSTRUCTIONS.md and
# the knowledge base files directly and does NOT need this bundle (see README §5).
#
# Reviewer-procedural content is kept in docs/REVIEWER_INSTRUCTIONS.md so both
# paths (Claude Code, web AI bundle) consume one source of truth.

# 1. Reviewer instructions (process + final instructions).
cat docs/REVIEWER_INSTRUCTIONS.md

# 2. Knowledge base, concatenated for the bundle path.
cat << 'EOF'

---
### KNOWLEDGE BASE START
---

The knowledge base referenced by the instructions above follows. Process it
before beginning the review.

--- START OF ONTOLOGY ---
EOF

cat ontology/ontology.json

cat << 'EOF'

--- END OF ONTOLOGY ---


--- START OF EXAMPLES ---
EOF

cat examples/examples.json

cat << 'EOF'

--- END OF EXAMPLES ---


--- START OF KNOWLEDGE BASE DOCUMENT ---
EOF

cat docs/AI_Hardware_Design_Review_KnowledgeBase.md

cat << 'EOF'

--- END OF KNOWLEDGE BASE DOCUMENT ---

---
### KNOWLEDGE BASE END
---
EOF
