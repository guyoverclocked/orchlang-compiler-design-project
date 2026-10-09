#!/usr/bin/env python3
"""Render the current Markdown research manuscript with ReportLab.

This deliberately small renderer handles the manuscript's headings, prose,
lists, tables and code. It preserves source content and hyperlinks; it does
not apply a publisher's unverified article template.
"""
import argparse
import html
from pathlib import Path
import re
import sys

from reportlab import __file__ as reportlab_file
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Preformatted, Spacer, Table, TableStyle, KeepTogether

ROOT = Path(__file__).resolve().parents[1]


def fonts(directory):
    candidates = [directory] if directory else []
    candidates.extend([
        Path('/usr/share/fonts/truetype/dejavu'),
        Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/native/libreoffice-headless/libreoffice/LibreOfficeDev.app/Contents/Resources/fonts/truetype',
    ])
    font_root = next((p for p in candidates if p and (p / 'DejaVuSans.ttf').exists()), None)
    if font_root:
        files = [('Paper', 'DejaVuSans.ttf'), ('Paper-Bold', 'DejaVuSans-Bold.ttf'),
                 ('Paper-Italic', 'DejaVuSans-Oblique.ttf'),
                 ('Paper-BoldItalic', 'DejaVuSans-BoldOblique.ttf'), ('PaperMono', 'DejaVuSansMono.ttf')]
    else:
        raise RuntimeError('Supply --font-dir containing DejaVuSans regular/bold/oblique/boldoblique and DejaVuSansMono fonts')
    for name, filename in files:
        pdfmetrics.registerFont(TTFont(name, str(font_root / filename)))
    pdfmetrics.registerFontFamily('Paper', normal='Paper', bold='Paper-Bold', italic='Paper-Italic', boldItalic='Paper-BoldItalic')


def inline(value):
    # ASCII hyphens for visual portability; semantic math symbols remain.
    value = value.translate(str.maketrans({'–': '-', '—': '-', '‑': '-', '\u00a0': ' '}))
    escaped = html.escape(value, quote=False)
    def link(match):
        label, url = match.groups()
        if not url.startswith(('https://', 'http://')):
            return label
        return '<link href="%s" color="#1F6F66">%s</link>' % (html.escape(url, quote=True), label)
    escaped = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', link, escaped)
    escaped = re.sub(r'`([^`]+)`', r'<font name="PaperMono" size="8.5">\1</font>', escaped)
    escaped = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', escaped)
    escaped = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<i>\1</i>', escaped)
    return escaped


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--source', type=Path, default=ROOT / 'docs/PAPER.md')
    cli.add_argument('--output', type=Path, default=ROOT / 'output/pdf/OrchLang_Technical_Report.pdf')
    cli.add_argument('--font-dir', type=Path)
    args = cli.parse_args()
    fonts(args.font_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    page_width, page_height = A4
    content_width = page_width - 104
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('PaperBody', fontName='Paper', fontSize=9.6, leading=14.0, spaceAfter=7.5,
                              textColor=colors.HexColor('#202837'), splitLongWords=True, allowWidows=0, allowOrphans=0))
    styles.add(ParagraphStyle('PaperTitle', fontName='Paper-Bold', fontSize=20, leading=25, spaceAfter=13,
                              textColor=colors.HexColor('#131A29'), keepWithNext=True))
    styles.add(ParagraphStyle('PaperH1', fontName='Paper-Bold', fontSize=13.4, leading=18, spaceBefore=15,
                              spaceAfter=7, textColor=colors.HexColor('#131A29'), keepWithNext=True))
    styles.add(ParagraphStyle('PaperH2', fontName='Paper-Bold', fontSize=10.9, leading=15, spaceBefore=10,
                              spaceAfter=6, textColor=colors.HexColor('#1F6F66'), keepWithNext=True))
    styles.add(ParagraphStyle('PaperSmall', parent=styles['PaperBody'], fontSize=8.4, leading=11.8, spaceAfter=4))
    styles.add(ParagraphStyle('PaperList', parent=styles['PaperBody'], leftIndent=15, firstLineIndent=-10,
                              spaceAfter=5))
    styles.add(ParagraphStyle('PaperCode', fontName='PaperMono', fontSize=7.9, leading=11,
                              textColor=colors.HexColor('#131A29'), backColor=colors.HexColor('#F4F6F7'),
                              borderPadding=8, spaceBefore=6, spaceAfter=10))
    lines = args.source.read_text().splitlines()
    story, cursor = [], 0
    while cursor < len(lines):
        line = lines[cursor]
        if not line.strip():
            cursor += 1
            continue
        if line.startswith('```'):
            cursor += 1
            code = []
            while cursor < len(lines) and not lines[cursor].startswith('```'):
                code.append(lines[cursor]); cursor += 1
            code_text = '\n'.join(code)
            story.append(KeepTogether([Preformatted(code_text, styles['PaperCode'])]))
            cursor += 1
            continue
        if line.startswith('|'):
            rows = []
            while cursor < len(lines) and lines[cursor].startswith('|'):
                cells = [x.strip() for x in lines[cursor].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', x) for x in cells): rows.append(cells)
                cursor += 1
            data = [[Paragraph(inline(cell), styles['PaperSmall']) for cell in row] for row in rows]
            widths = [content_width * 0.57, content_width * 0.43] if len(rows[0]) == 2 else [content_width / len(rows[0])] * len(rows[0])
            table = Table(data, colWidths=widths, repeatRows=1, hAlign='LEFT')
            table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#E9EFED')),
                ('LINEBELOW', (0,0), (-1,0), 0.65, colors.HexColor('#1F6F66')),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F6F7F8')]),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('LEFTPADDING', (0,0), (-1,-1), 8), ('RIGHTPADDING', (0,0), (-1,-1), 8),
                ('TOPPADDING', (0,0), (-1,-1), 6), ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ]))
            story.append(KeepTogether([table, Spacer(1,9)]) if len(rows) < 8 else table)
            if len(rows) >= 8: story.append(Spacer(1,9))
            continue
        heading = re.match(r'^(#{1,3})\s+(.+)', line)
        if heading:
            depth, text = heading.groups()
            style = 'PaperTitle' if len(depth) == 1 else 'PaperH1' if len(depth) == 2 else 'PaperH2'
            story.append(Paragraph(inline(text), styles[style])); cursor += 1
            continue
        listing = re.match(r'^(- |\d+\. )(.+)', line)
        if listing:
            prefix, text = listing.groups()
            marker = '• ' if prefix == '- ' else prefix
            story.append(Paragraph(inline(marker + text), styles['PaperList'])); cursor += 1
            continue
        prose = [line.strip()]
        cursor += 1
        while cursor < len(lines) and lines[cursor].strip() and not re.match(r'^(#|\||```|- |\d+\. )', lines[cursor]):
            prose.append(lines[cursor].strip()); cursor += 1
        story.append(Paragraph(inline(' '.join(prose)), styles['PaperBody']))

    def page(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#D8DEDD'))
        canvas.line(52, page_height - 35, page_width - 52, page_height - 35)
        canvas.setFont('Paper', 7.4)
        canvas.setFillColor(colors.HexColor('#5A6573'))
        canvas.drawString(52, page_height - 26, 'ORCHLANG  /  TECHNICAL REPORT  /  0.5.0-rc1')
        canvas.drawString(52, 29, '9 October 2026  ·  Software-paper draft for author review')
        canvas.drawRightString(page_width - 52, 29, str(document.page))
        canvas.restoreState()

    document = SimpleDocTemplate(str(args.output), pagesize=A4, leftMargin=52, rightMargin=52,
                                  topMargin=53, bottomMargin=50, title='OrchLang: Replayable Contracts for Token Usage and Request-Equivalent LLM Workflows',
                                  author='Nambi Rajan M', subject='Research software technical report')
    document.build(story, onFirstPage=page, onLaterPages=page)
    print(args.output)


if __name__ == '__main__':
    main()
