#!/bin/sh
set -eu

RESEARCH_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
BUILD_DIR="$RESEARCH_DIR/.build"
OUT_DIR="$RESEARCH_DIR/dist"
case "${PRESENTATION_BUILD_DIR:-}" in
  /*) BUILD_DIR="$PRESENTATION_BUILD_DIR" ;;
  ?*) BUILD_DIR="$RESEARCH_DIR/$PRESENTATION_BUILD_DIR" ;;
esac
case "${PRESENTATION_OUTPUT_DIR:-}" in
  /*) OUT_DIR="$PRESENTATION_OUTPUT_DIR" ;;
  ?*) OUT_DIR="$RESEARCH_DIR/$PRESENTATION_OUTPUT_DIR" ;;
esac
RUNTIME_NODE="/Users/nambi/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
RUNTIME_NODE_MODULES="/Users/nambi/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules"
RUNTIME_PYTHON="/Users/nambi/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
SKILL_DIR="/Users/nambi/.codex/plugins/cache/openai-primary-runtime/presentations/26.1007.11041/skills/presentations"

mkdir -p "$BUILD_DIR" "$OUT_DIR"
mkdir -p "$RESEARCH_DIR/node_modules"
if [ -e "$RESEARCH_DIR/node_modules/@oai" ] || [ -L "$RESEARCH_DIR/node_modules/@oai" ]; then
  echo "Refusing to replace existing node_modules/@oai" >&2
  exit 1
fi
ln -s "$RUNTIME_NODE_MODULES/@oai" "$RESEARCH_DIR/node_modules/@oai"
cleanup() {
  rm -f "$RESEARCH_DIR/node_modules/@oai"
  rmdir "$RESEARCH_DIR/node_modules" 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM
export RUNTIME_NODE_MODULES
if [ -n "${PRESENTATION_PREVIEW_DIR:-}" ]; then
  export PRESENTATION_PREVIEW_DIR
  "$RUNTIME_NODE" "$RESEARCH_DIR/build_deck.mjs"
  echo "Layout preview written to $PRESENTATION_PREVIEW_DIR"
  exit 0
fi
"$RUNTIME_NODE" "$RESEARCH_DIR/build_deck.mjs"
if [ "${PRESENTATION_SKIP_FINAL_PNGS:-0}" = "1" ]; then
  echo "Finalized editable PPTX is in $OUT_DIR; final slide rendering was skipped."
  exit 0
fi
"$RUNTIME_PYTHON" "$SKILL_DIR/container_tools/create_montage.py" \
  --input_dir "$OUT_DIR/slide_png" \
  --output_file "$OUT_DIR/montage.png" \
  --num_col 5 --cell_width 400 --cell_height 225 --label_mode number --fail_on_image_error
echo "Editable PPTX and slide renders are in $OUT_DIR."
echo "Export the PPTX to PDF in PowerPoint, then run ./submission/research/render_pdf.sh."
