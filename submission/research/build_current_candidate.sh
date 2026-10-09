#!/bin/sh
set -eu

RESEARCH_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
export PRESENTATION_DATA_MODULE="deck_data_current_candidate.mjs"
export PRESENTATION_EVIDENCE_MODE="current-candidate"
export PRESENTATION_EXPECTED_SLIDE_COUNT="32"
export PRESENTATION_FILENAME="OrchLang_Current_Software_Review.pptx"
export PRESENTATION_BUILD_DIR=".build/current"
export PRESENTATION_OUTPUT_DIR="dist_current"

FINAL_PPTX="$RESEARCH_DIR/dist_current/OrchLang_Current_Software_Review.pptx"
PREVIOUS_PPTX=""
if [ -e "$FINAL_PPTX" ]; then
  ARCHIVE_DIR="$RESEARCH_DIR/.build/current/previous"
  mkdir -p "$ARCHIVE_DIR"
  STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  PREVIOUS_PPTX="$ARCHIVE_DIR/OrchLang_Current_Software_Review.$STAMP.pptx"
  SUFFIX=1
  while [ -e "$PREVIOUS_PPTX" ]; do
    PREVIOUS_PPTX="$ARCHIVE_DIR/OrchLang_Current_Software_Review.$STAMP.$SUFFIX.pptx"
    SUFFIX=$((SUFFIX + 1))
  done
  mv "$FINAL_PPTX" "$PREVIOUS_PPTX"
fi

if "$RESEARCH_DIR/build.sh"; then
  exit 0
else
  STATUS=$?
  if [ -n "$PREVIOUS_PPTX" ] && [ -e "$PREVIOUS_PPTX" ] && [ ! -e "$FINAL_PPTX" ]; then
    mv "$PREVIOUS_PPTX" "$FINAL_PPTX"
  fi
  exit "$STATUS"
fi
