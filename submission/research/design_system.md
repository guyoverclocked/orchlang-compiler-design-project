# OrchLang review deck design system

## Reference and canvas

- Reference: ArchiveGate Review 1, especially the editorial cover, paired
  sequence diagrams, decision tables, and restrained references slide.
- Canvas: 16:9, 1280 × 720 px.
- Alternate warm light slides and deep navy slides to pace the narrative.
- Keep the headline to one claim, with one diagram or evidence object as the
  focal point. Avoid stock imagery and decorative raster graphics.

## Palette

| Token | Hex | Use |
|---|---|---|
| Paper | `#F5F2EA` | Primary light background |
| Ink | `#141B2B` | Main text on paper |
| Night | `#131A29` | Dark background |
| Coral | `#FF8A5C` | Secret-controlled path, key callout |
| Rust | `#C2461F` | Error/rejection, only when needed |
| Teal | `#5CC8B8` | Aligned/accepted path |
| Deep teal | `#1F6F66` | Teal on light backgrounds |
| Warm white | `#FFFDF8` | Panels on light slides |
| Slate | `#646B7A` | Secondary text |
| Pale slate | `#B8C1D1` | Secondary text on dark slides |
| Sand | `#D9CBB6` | Secondary diagrams and dividers |

Use coral for the secret-dependent decision edge and rust for an actual
rejection. Use teal for an established alignment or accepted case. Do not use
color alone: every state also gets a label or symbol.

## Typography

- Headline and body: `Avenir Next`, with bold headlines.
- Code and mathematical traces: `Menlo`.
- Title sizes: 44–52 px; cover headline 62–70 px.
- Body sizes: 22–26 px; caption and source label 15–17 px; never make the
  visible main-slide body smaller than 18 px.
- Use sentence case, short line lengths, and generous white space.

These are design-selected fonts, checked against the current macOS host. The
ArchiveGate source HTML uses Space Grotesk, IBM Plex Sans, and JetBrains Mono;
those fonts were not present on the host. The deck keeps the reference's
editorial hierarchy with installed fonts rather than silently relying on a
fallback.

## Editable evidence objects

- Use native textboxes, rectangles, lines, tables, and charts for every diagram
  and quantitative element.
- Put units beside numbers. On the central counterexample, distinguish a
  configured cap, observed input tokens, returned output tokens, and the bill.
- Label the two sides of every relational comparison and state which values are
  held fixed.
- Avoid mock interface chrome; model the compiler's actual output only where a
  source or harness can reproduce it.

## Slide furniture

- Small all-caps project/section eyebrow at top left.
- Section label at top right.
- Short title below the eyebrow.
- Thin footer rule with project/course label at left and slide number at right.
- Main-deck pages 1–18; appendix pages labeled `A1`–`A8` in footer, while the
  PowerPoint's physical slide numbers continue normally.
