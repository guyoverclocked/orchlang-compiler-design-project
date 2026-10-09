#!/bin/sh
set -eu

RESEARCH_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
OUT_DIR="$RESEARCH_DIR/dist_current"
PDF="$OUT_DIR/OrchLang_Current_Software_Review.pdf"
PNG_DIR="$OUT_DIR/pdf_slide_png"
RUNTIME_PYTHON="/Users/nambi/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
SKILL_DIR="/Users/nambi/.codex/plugins/cache/openai-primary-runtime/presentations/26.1007.11041/skills/presentations"

PDFINFO="$(command -v pdfinfo || true)"
PDFTOPPM="$(command -v pdftoppm || true)"
SOFFICE_APP="/Applications/LibreOffice.app/Contents/MacOS/soffice"
if [ -z "$PDFINFO" ] || [ -z "$PDFTOPPM" ]; then
  echo "Poppler (pdfinfo and pdftoppm) is required to render slide PNGs." >&2
  exit 1
fi

PPTX="$OUT_DIR/OrchLang_Current_Software_Review.pptx"
if [ ! -s "$PPTX" ]; then
  echo "Editable deck not found: $PPTX" >&2
  exit 1
fi

rm -f "$PDF"
if [ -x "$SOFFICE_APP" ]; then
  "$SOFFICE_APP" --headless --convert-to pdf --outdir "$OUT_DIR" "$PPTX"
else
  echo "LibreOffice app is unavailable; assembling PDF pages from the reviewed editable-deck renders." >&2
  "$RUNTIME_PYTHON" "$RESEARCH_DIR/render_pngs_to_pdf.py"
fi
if [ ! -s "$PDF" ]; then
  echo "LibreOffice did not produce $PDF." >&2
  exit 1
fi

PAGES="$("$PDFINFO" "$PDF" | awk '$1 == "Pages:" { print $2 }')"
if [ "$PAGES" != "32" ]; then
  echo "Expected 32 PDF pages; found ${PAGES:-unknown}." >&2
  exit 1
fi

rm -rf "$PNG_DIR"
mkdir -p "$PNG_DIR"
"$PDFTOPPM" -png -r 96 -f 1 -l 32 "$PDF" "$PNG_DIR/slide"
COUNT="$(find "$PNG_DIR" -maxdepth 1 -type f -name 'slide-*.png' | wc -l | tr -d ' ')"
if [ "$COUNT" != "32" ]; then
  echo "Expected 32 slide PNGs; found $COUNT." >&2
  exit 1
fi

"$RUNTIME_PYTHON" "$SKILL_DIR/container_tools/create_montage.py" \
  --input_dir "$PNG_DIR" \
  --output_file "$OUT_DIR/montage.png" \
  --num_col 5 --cell_width 400 --cell_height 225 --label_mode number --fail_on_image_error
