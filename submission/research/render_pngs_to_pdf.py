#!/usr/bin/env python3
"""Assemble the final Artifact Tool slide renders into a 16:9 handout PDF.

This fallback preserves the exact reviewed slide renders as raster pages when
PowerPoint/LibreOffice export is unavailable. The last page receives a clickable
loopback-demo annotation over the visible URL.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "dist_current"
SLIDE_DIR = OUT / "slide_png"
PDF = OUT / "OrchLang_Current_Software_Review.pdf"
DEMO_URL = "http://127.0.0.1:8765/"
PAGE_W, PAGE_H = 960.0, 540.0  # 13⅓ × 7½ inches at 72 points per inch.
EXPECTED = 32


def main() -> None:
    slides = sorted(SLIDE_DIR.glob("slide-*.png"))
    if len(slides) != EXPECTED:
        raise SystemExit(f"Expected {EXPECTED} rendered slides; found {len(slides)}")

    pdf = canvas.Canvas(str(PDF), pagesize=(PAGE_W, PAGE_H), pageCompression=1)
    pdf.setTitle("OrchLang: Replayable Contracts for Token Usage and Request-Equivalent LLM Workflows")
    pdf.setAuthor("Nambi Rajan M")
    pdf.setSubject("Software and compiler-design review presentation")

    for index, path in enumerate(slides, start=1):
        image = ImageReader(str(path))
        image_w, image_h = image.getSize()
        if abs(image_w / image_h - PAGE_W / PAGE_H) > 1e-6:
            raise SystemExit(f"Slide {index} has unexpected aspect ratio: {image_w}x{image_h}")
        pdf.drawImage(image, 0, 0, width=PAGE_W, height=PAGE_H, preserveAspectRatio=True, mask="auto")
        if index == EXPECTED:
            # The visible URL spans x=90..1180, y=292..354 in the 1280×720 render.
            scale_x, scale_y = PAGE_W / image_w, PAGE_H / image_h
            rect = (
                90 * scale_x,
                PAGE_H - 354 * scale_y,
                1180 * scale_x,
                PAGE_H - 292 * scale_y,
            )
            pdf.linkURL(DEMO_URL, rect, relative=0, thickness=0, kind="URI")
        pdf.showPage()

    pdf.save()
    print(f"Wrote {PDF} with {EXPECTED} raster pages from the reviewed slide PNGs.")


if __name__ == "__main__":
    main()
