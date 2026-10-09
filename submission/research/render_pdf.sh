#!/bin/sh
set -eu

RESEARCH_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
OUT_DIR="$RESEARCH_DIR/dist"
PDF="$OUT_DIR/OrchLang_Compiler_Design_Review.pdf"
PNG_DIR="$OUT_DIR/slide_png"
RUNTIME_PYTHON="/Users/nambi/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
SKILL_DIR="/Users/nambi/.codex/plugins/cache/openai-primary-runtime/presentations/26.1007.11041/skills/presentations"

PDFINFO="$(command -v pdfinfo || true)"
PDFTOPPM="$(command -v pdftoppm || true)"
if [ -z "$PDFINFO" ] || [ -z "$PDFTOPPM" ]; then
  echo "Poppler (pdfinfo and pdftoppm) is required to render slide PNGs." >&2
  exit 1
fi
if [ ! -s "$PDF" ]; then
  echo "Export the PowerPoint deck to $PDF before running this script." >&2
  exit 1
fi

PAGES="$("$PDFINFO" "$PDF" | awk '$1 == "Pages:" { print $2 }')"
if [ "$PAGES" != "26" ]; then
  echo "Expected 26 PDF pages; found ${PAGES:-unknown}." >&2
  exit 1
fi

mkdir -p "$PNG_DIR"
"$PDFTOPPM" -png -r 96 -f 1 -l 26 "$PDF" "$PNG_DIR/slide"
COUNT="$(find "$PNG_DIR" -maxdepth 1 -type f -name 'slide-*.png' | wc -l | tr -d ' ')"
if [ "$COUNT" != "26" ]; then
  echo "Expected 26 slide PNGs; found $COUNT." >&2
  exit 1
fi

"$RUNTIME_PYTHON" "$SKILL_DIR/container_tools/create_montage.py" \
  --input_dir "$PNG_DIR" \
  --output_file "$OUT_DIR/montage.png" \
  --num_col 5 --cell_width 400 --cell_height 225 --label_mode number --fail_on_image_error
