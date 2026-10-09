import fs from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";
import { Presentation, PresentationFile, FileBlob } from "@oai/artifact-tool";

const THIS_DIR = path.dirname(fileURLToPath(import.meta.url));
const DATA_MODULE = process.env.PRESENTATION_DATA_MODULE || "deck_data.mjs";
const { deck } = await import(pathToFileURL(path.resolve(THIS_DIR, DATA_MODULE)).href);
const RESEARCH_DIR = THIS_DIR;
const ROOT_DIR = path.resolve(RESEARCH_DIR, "../..");
const SKILL_DIR = "/Users/nambi/.codex/plugins/cache/openai-primary-runtime/presentations/26.1007.11041/skills/presentations";
const RUNTIME_PYTHON = "/Users/nambi/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3";
const BUILD_DIR = process.env.PRESENTATION_BUILD_DIR
  ? path.resolve(RESEARCH_DIR, process.env.PRESENTATION_BUILD_DIR)
  : path.join(RESEARCH_DIR, ".build");
const OUTPUT_DIR = process.env.PRESENTATION_OUTPUT_DIR
  ? path.resolve(RESEARCH_DIR, process.env.PRESENTATION_OUTPUT_DIR)
  : path.join(RESEARCH_DIR, "dist");
const FINAL_NAME = process.env.PRESENTATION_FILENAME || "OrchLang_Compiler_Design_Review.pptx";
const FINAL_PPTX = path.join(OUTPUT_DIR, FINAL_NAME);
const PNG_DIR = path.join(OUTPUT_DIR, "slide_png");
const PREVIEW_DIR = process.env.PRESENTATION_PREVIEW_DIR
  ? path.resolve(process.env.PRESENTATION_PREVIEW_DIR)
  : undefined;
const CURRENT_CANDIDATE = process.env.PRESENTATION_EVIDENCE_MODE === "current-candidate";
const GRAPH_CANDIDATE = process.env.PRESENTATION_EVIDENCE_MODE === "graph-candidate" || CURRENT_CANDIDATE;
const EXPECTED_SLIDE_COUNT = Number(process.env.PRESENTATION_EXPECTED_SLIDE_COUNT || 26);
const SKIP_FINAL_PNGS = process.env.PRESENTATION_SKIP_FINAL_PNGS === "1";
const W = 1280;
const H = 720;

const C = {
  paper: "#F5F2EA",
  ink: "#141B2B",
  night: "#131A29",
  coral: "#FF8A5C",
  rust: "#C2461F",
  teal: "#5CC8B8",
  deepTeal: "#1F6F66",
  white: "#FFFDF8",
  slate: "#646B7A",
  pale: "#B8C1D1",
  sand: "#D9CBB6",
  border: "#D7D0C4",
  darkBorder: "#343D50",
};

const FONT = { body: "Avenir Next", mono: "Menlo" };
const noLine = { style: "solid", fill: "none", width: 0 };

function shape(slide, geometry, name, x, y, w, h, fill = "none", line = noLine, radius) {
  const config = {
    geometry,
    name,
    position: { left: x, top: y, width: w, height: h },
    fill,
    line,
  };
  if (radius !== undefined) config.borderRadius = radius;
  return slide.shapes.add(config);
}

function rect(slide, name, x, y, w, h, fill, stroke = "none", radius = 0) {
  return shape(
    slide,
    radius ? "roundRect" : "rect",
    name,
    x,
    y,
    w,
    h,
    fill,
    stroke === "none" ? noLine : { style: "solid", fill: stroke, width: 1 },
    radius || undefined,
  );
}

function text(slide, name, value, x, y, w, h, opts = {}) {
  const box = shape(slide, "textbox", name, x, y, w, h, "none", noLine);
  box.text = String(value ?? "");
  box.text.style = {
    typeface: opts.mono ? FONT.mono : (opts.typeface || FONT.body),
    fontSize: opts.size ?? 22,
    color: opts.color ?? C.ink,
    bold: opts.bold ?? false,
    italic: opts.italic ?? false,
    alignment: opts.align ?? "left",
    verticalAlignment: opts.valign ?? "top",
    autoFit: opts.autoFit ?? "shrinkText",
    wrap: "square",
    insets: opts.insets ?? 0,
  };
  return box;
}

function label(slide, name, value, x, y, w, opts = {}) {
  const dark = opts.dark ?? false;
  const fill = opts.fill ?? (dark ? C.darkBorder : C.sand);
  const fg = opts.color ?? (dark ? C.paper : C.ink);
  rect(slide, `${name}-pill`, x, y, w, 28, fill, "none", 10);
  text(slide, `${name}-text`, value.toUpperCase(), x + 10, y + 5, w - 20, 20, {
    size: 13,
    color: fg,
    bold: true,
    align: "center",
    valign: "middle",
  });
}

function card(slide, name, x, y, w, h, title, body, opts = {}) {
  const dark = opts.dark ?? false;
  const fill = opts.fill ?? (dark ? "#1C2638" : C.white);
  const edge = opts.edge ?? (dark ? C.darkBorder : C.border);
  const titleColor = opts.titleColor ?? (dark ? C.paper : C.ink);
  const bodyColor = opts.bodyColor ?? (dark ? C.pale : C.slate);
  const panel = rect(slide, `${name}-panel`, x, y, w, h, fill, edge, 8);
  if (opts.accent) rect(slide, `${name}-accent`, x, y, 6, h, opts.accent);
  text(slide, `${name}-title`, title, x + 22, y + 18, w - 44, opts.titleH ?? 48, {
    size: opts.titleSize ?? 24,
    color: titleColor,
    bold: true,
  });
  if (body) text(slide, `${name}-body`, body, x + 22, y + (opts.bodyY ?? 74), w - 44, h - (opts.bodyY ?? 88), {
    size: opts.bodySize ?? 20,
    color: bodyColor,
    mono: opts.mono ?? false,
  });
  return panel;
}

function baseSlide(pres, spec, physicalIndex) {
  const slide = pres.slides.add();
  const dark = Boolean(spec.dark);
  slide.background.fill = dark ? C.night : C.paper;
  const pageLabel = spec.footerLabel || String(physicalIndex);
  const fg = dark ? C.paper : C.ink;
  const secondary = dark ? C.pale : C.slate;
  text(slide, `s${physicalIndex}-brand`, "ORCHLANG  /  COMPILER DESIGN REVIEW", 70, 38, 510, 24, {
    size: 14, color: dark ? C.pale : C.slate, bold: true,
  });
  text(slide, `s${physicalIndex}-section`, spec.section || "REVIEW", 830, 38, 380, 24, {
    size: 14, color: dark ? C.teal : C.deepTeal, bold: true, align: "right",
  });
  text(slide, `s${physicalIndex}-title`, spec.title, 70, 82, 1140, 90, {
    size: spec.titleSize ?? 42, color: fg, bold: true,
  });
  if (spec.subtitle) text(slide, `s${physicalIndex}-subtitle`, spec.subtitle, 72, 176, 1120, 45, {
    size: 21, color: secondary,
  });
  rect(slide, `s${physicalIndex}-source-rule`, 70, 642, 1140, 1, dark ? C.darkBorder : C.border);
  const visibleSource = spec.footerSources || (typeof spec.sources === "string" ? spec.sources.split(";")[0] : "See speaker notes");
  text(slide, `s${physicalIndex}-sources`, `SOURCE  ${visibleSource}`, 72, 649, 1080, 19, {
    size: 13.5, color: secondary,
  });
  rect(slide, `s${physicalIndex}-footer-rule`, 70, 676, 1140, 1, dark ? C.darkBorder : C.border);
  text(slide, `s${physicalIndex}-footer`, "ORCHLANG  ·  VIT  ·  COMPILER DESIGN LAB", 72, 686, 600, 20, {
    size: 13.5, color: secondary, bold: true,
  });
  text(slide, `s${physicalIndex}-page`, pageLabel, 1140, 686, 68, 20, {
    size: 14, color: dark ? C.teal : C.deepTeal, bold: true, align: "right",
  });
  slide.speakerNotes.text = `${spec.notes || ""}\n\nSources: ${spec.sources || "See sources.md"}`;
  return slide;
}

function drawCover(pres, spec) {
  const slide = pres.slides.add();
  slide.background.fill = C.paper;
  rect(slide, "cover-coral-rail", 0, 0, 18, H, C.coral);
  text(slide, "cover-eyebrow", "ORCHLANG  /  COMPILER DESIGN REVIEW", 76, 64, 620, 28, {
    size: 15, color: C.slate, bold: true,
  });
  text(slide, "cover-title", spec.title, 74, 140, 660, 220, {
    size: 68, color: C.ink, bold: true,
  });
  text(slide, "cover-subtitle", spec.subtitle, 78, 378, 620, 112, {
    size: 26, color: C.slate,
  });
  text(slide, "cover-byline", deck.author, 78, 578, 650, 26, {
    size: 16, color: C.ink, bold: true,
  });

  rect(slide, "cover-evidence-panel", 808, 70, 404, 575, C.night, "none", 12);
  label(slide, "cover-relation", "modeled comparison", 846, 100, 190, { dark: true, fill: C.darkBorder, color: C.pale });
  const rows = [
    ["OBSERVER", "itemized model usage", C.sand],
    ["PUBLIC INPUTS", "held equal", C.teal],
    ["MODEL BEHAVIOR", "aligned by relation", C.teal],
    ["SECRET", "varies", C.coral],
  ];
  rows.forEach(([head, value, accent], i) => {
    const y = 153 + i * 49;
    text(slide, `cover-cond-${i}-head`, head, 846, y, 180, 20, { size: 13.5, color: C.pale, bold: true });
    text(slide, `cover-cond-${i}-value`, value, 1025, y - 1, 160, 26, { size: 16, color: accent, bold: true, align: "right" });
    rect(slide, `cover-cond-${i}-rule`, 846, y + 31, 338, 1, C.darkBorder);
  });
  text(slide, "cover-invoice-title", "MODEL USAGE TRACE", 846, 366, 220, 24, { size: 14, color: C.pale, bold: true });
  text(slide, "cover-invoice-head", "MODEL        USAGE EVENT", 846, 403, 338, 24, { size: 14, color: C.pale, mono: true, bold: true });
  text(slide, "cover-invoice-row-a", "fast         branch A", 846, 443, 338, 30, { size: 18, color: C.paper, mono: true });
  text(slide, "cover-invoice-row-b", "large        branch B", 846, 485, 338, 30, { size: 18, color: C.coral, mono: true });
  rect(slide, "cover-invoice-rule", 846, 526, 338, 1, C.darkBorder);
  text(slide, "cover-conclusion", "If usage is itemized, the selected path is visible.", 846, 549, 340, 58, { size: 18, color: C.teal, bold: true });
  slide.speakerNotes.text = `${spec.notes}\n\nSources: ${spec.sources}`;
  return slide;
}

function drawBranch(slide) {
  card(slide, "branch-secret", 78, 314, 205, 135, "secret flag", "is_enterprise", { dark: true, accent: C.coral, mono: true, titleSize: 22, bodySize: 19 });
  text(slide, "branch-arrow-1", "→", 292, 355, 60, 48, { size: 38, color: C.coral, bold: true, align: "center" });
  const condition = card(slide, "branch-condition", 352, 314, 200, 135, "if / else", "same public ticket", { dark: true, accent: C.sand, titleSize: 22, bodySize: 18 });
  const fast = card(slide, "branch-fast", 614, 234, 230, 126, "small model", "call acknowledge(ticket)", { dark: true, accent: C.teal, mono: true, titleSize: 21, bodySize: 16 });
  const large = card(slide, "branch-large", 614, 414, 230, 126, "large model", "call escalate(ticket)", { dark: true, accent: C.coral, mono: true, titleSize: 21, bodySize: 16 });
  for (const target of [fast, large]) {
    slide.shapes.connect(condition, target, {
      kind: "straight",
      fromSide: "right",
      toSide: "left",
      line: { style: "solid", fill: C.coral, width: 2 },
      tail: { type: "triangle", width: "sm", length: "sm" },
    });
  }
  text(slide, "branch-arrow-3", "→", 846, 340, 56, 48, { size: 36, color: C.teal, bold: true, align: "center" });
  card(slide, "branch-bill", 904, 274, 290, 230, "per-model usage ledger", "branch A → small model\nbranch B → large model\n\nIf itemized, usage reveals the path.", { dark: true, accent: C.teal, mono: true, titleSize: 20, bodySize: 16.5, bodyY: 68 });
  text(slide, "branch-footnote", "SECRET-DEPENDENT CONTROL FLOW  →  MODELED USAGE OBSERVATION", 78, 568, 1115, 32, { size: 17.5, color: C.coral, bold: true, align: "center" });
}

function drawValueFlow(slide) {
  label(slide, "vf-secret", "secret condition", 82, 250, 205, { fill: C.coral, color: C.ink });
  card(slide, "vf-branch", 82, 296, 255, 104, "if enterprise", "selects one call path", { fill: C.white, accent: C.coral, titleSize: 22, bodySize: 18, bodyY: 58 });
  card(slide, "vf-prompt", 408, 250, 324, 150, "prompt input", "public ticket\nflows to the model", { fill: C.white, accent: C.deepTeal, titleSize: 23, bodySize: 21 });
  card(slide, "vf-sinks", 809, 250, 340, 150, "value sinks", "no secret argument\nno secret output\nno secret tool effect", { fill: C.white, accent: C.teal, titleSize: 23, bodySize: 18 });
  text(slide, "vf-arrow-secret", "→", 344, 322, 54, 40, { size: 35, color: C.coral, bold: true, align: "center" });
  text(slide, "vf-arrow-public", "ticket →", 741, 309, 68, 46, { size: 20, color: C.deepTeal, bold: true, align: "center" });
  rect(slide, "vf-separator", 82, 445, 1067, 1, C.border);
  text(slide, "vf-resource-observation", "RESOURCE OBSERVATION", 82, 475, 236, 22, { size: 14, color: C.slate, bold: true });
  text(slide, "vf-bill-claim", "The branch changes whether a model is called and what appears in the modeled usage record.", 82, 514, 1050, 50, { size: 24, color: C.ink, bold: true });
}

function drawObservation(slide, spec) {
  text(slide, "obs-equation", "Obs(e)[model] = (input, output, calls)", 95, 267, 1085, 66, { size: 34, color: C.paper, bold: true, mono: true, align: "center" });
  const items = spec.fields || [];
  const xs = [120, 475, 830];
  items.forEach((f, i) => card(slide, `obs-field-${i}`, xs[i], 389, 300, 128, f, "measured per model", { dark: true, accent: i === 0 ? C.teal : (i === 1 ? C.coral : C.sand), titleSize: 23, bodySize: 18, bodyY: 70 }));
  text(slide, "obs-scope", "The mock model defines this trace; no live-provider invoice was measured.", 140, 557, 1000, 38, { size: 18, color: C.pale, align: "center" });
}

function drawTwoGuarantees(slide) {
  card(slide, "guarantee-unary", 86, 264, 525, 300, "ONE EXECUTION", "Question\nHow much can this workflow consume?\n\nClaim\nCost(e) ≤ B\n\nEvidence\nStructural worst-case bound", { fill: C.white, accent: C.deepTeal, titleSize: 23, bodySize: 21, bodyY: 64 });
  card(slide, "guarantee-relational", 668, 264, 525, 300, "PAIRED EXECUTIONS", "Question\nCan changing the secret change the bill?\n\nClaim\nObs(e₀) = Obs(e₁)\n\nEvidence\nPaired-run check under declared relation", { fill: C.white, accent: C.coral, titleSize: 23, bodySize: 21, bodyY: 64 });
}

function drawCounterexample(slide, ev) {
  card(slide, "counter-left", 90, 265, 510, 290, "SECRET = 0", `fixed public value: left_source\ncap = ${ev.capX} tokens\nrealized length = n\ninput usage = ${ev.billX}\nshared-oracle output = ${ev.outputTokens}`, { dark: true, accent: C.teal, titleSize: 23, bodySize: 20, mono: true, bodyY: 76 });
  card(slide, "counter-right", 680, 265, 510, 290, "SECRET = 1", `fixed public value: right_source\ncap = ${ev.capY} tokens\nrealized length = m\ninput usage = ${ev.billY}\nshared-oracle output = ${ev.outputTokens}`, { dark: true, accent: C.coral, titleSize: 23, bodySize: 20, mono: true, bodyY: 76 });
  text(slide, "counter-equal-caps", `same per-call envelope: ${ev.certifiedArmBound}`, 120, 575, 1040, 34, { size: 18, color: C.sand, bold: true, align: "center" });
}

function drawCapActual(slide, ev) {
  card(slide, "cap-envelope", 132, 256, 1016, 95, "BOTH ARMS HAVE THE SAME DECLARED ENVELOPE", "input ≤ 35 estimated tokens   ·   output ≤ 4 tokens   ·   calls = 1", { fill: C.white, accent: C.deepTeal, titleSize: 18, titleH: 30, bodyY: 53, bodySize: 20, mono: true });
  card(slide, "cap-branch-a", 130, 388, 478, 122, "SECRET = 0", "input usage = 3 + n\noutput = o₀  ·  default oracle at i=0", { fill: C.white, accent: C.teal, titleSize: 21, titleH: 30, bodyY: 53, bodySize: 17.5, mono: true });
  card(slide, "cap-branch-b", 672, 388, 478, 122, "SECRET = 1", "input usage = 3 + m\noutput = o₀  ·  default oracle at i=0", { fill: C.white, accent: C.coral, titleSize: 21, titleH: 30, bodyY: 53, bodySize: 17.5, mono: true });
  text(slide, "cap-lesson", "For a fixed public fixture where n ≠ m, the shared cap does not make the traces equal.", 118, 552, 1050, 46, { size: 20, color: C.ink, bold: true, align: "center" });
}

function drawCoupling(slide) {
  const coupleA = card(slide, "couple-a", 84, 278, 390, 236, "EXECUTION A", "public inputs = p\nsecret = s₀\nsourced test: ω(K, i)\ntheorem mode: Ω(K, i, Q)", { dark: true, accent: C.teal, mono: true, titleSize: 23, bodySize: 19, bodyY: 78 });
  const coupleB = card(slide, "couple-b", 806, 278, 390, 236, "EXECUTION B", "public inputs = p\nsecret = s₁\nsourced test: ω(K, i)\ntheorem mode: Ω(K, i, Q)", { dark: true, accent: C.coral, mono: true, titleSize: 23, bodySize: 19, bodyY: 78 });
  slide.shapes.connect(coupleA, coupleB, {
    kind: "straight", fromSide: "right", toSide: "left",
    line: { style: "solid", fill: C.sand, width: 2 },
    tail: { type: "triangle", width: "sm", length: "sm" },
  });
  slide.shapes.connect(coupleB, coupleA, {
    kind: "straight", fromSide: "left", toSide: "right",
    line: { style: "solid", fill: C.sand, width: 2 },
    tail: { type: "triangle", width: "sm", length: "sm" },
  });
  text(slide, "couple-fixed", "FIXED", 545, 308, 190, 26, { size: 14, color: C.teal, bold: true, align: "center" });
  text(slide, "couple-result", "K = resolved contract   ·   i = per-contract call index   ·   Q = DSL abstract request", 160, 558, 960, 42, { size: 17, color: C.paper, bold: true, align: "center" });
}

function drawSignature(slide) {
  label(slide, "sig-left-label", "arm 0", 92, 252, 110, { fill: C.sand, color: C.ink });
  label(slide, "sig-right-label", "arm 1", 92, 426, 110, { fill: C.teal, color: C.ink });
  const call = "contract=K  ·  template=\"reply {ticket}\"  ·  args=[outer(ticket#7)]";
  card(slide, "sig-arm0", 228, 242, 958, 112, "call event", call, { fill: C.white, accent: C.deepTeal, titleSize: 19, titleH: 30, bodyY: 49, bodySize: 19, mono: true });
  card(slide, "sig-arm1", 228, 416, 958, 112, "call event", call, { fill: C.white, accent: C.deepTeal, titleSize: 19, titleH: 30, bodyY: 49, bodySize: 19, mono: true });
  text(slide, "sig-equal", "same ordered request-and-billing structure", 300, 558, 820, 32, { size: 20, color: C.deepTeal, bold: true, align: "center" });
}

function drawAcceptReject(slide) {
  card(slide, "rule-accept", 86, 270, 525, 300, "✓  ACCEPT", "arm 0: Call(m, τ + |ticket|)\narm 1: Call(m, τ + |ticket|)\n\nresolved events are equal", { dark: true, accent: C.teal, titleColor: C.teal, mono: true, titleSize: 24, bodySize: 19, bodyY: 78 });
  card(slide, "rule-reject", 668, 270, 525, 300, "×  REJECT", "arm 0: Call(m, τ + |x|)\narm 1: Call(m, τ + |y|)\n\nterms are not known to agree", { dark: true, accent: C.coral, titleColor: C.coral, mono: true, titleSize: 24, bodySize: 19, bodyY: 78 });
  text(slide, "rule-scope", "Sufficient and deliberately incomplete for the declared observation.", 168, 585, 950, 29, { size: 18, color: C.pale, align: "center" });
}

function drawChained(slide) {
  card(slide, "chain-a1", 85, 265, 290, 136, "first call", "resolved model M₁\nrequest R₁", { fill: C.white, accent: C.deepTeal, mono: true, titleSize: 22, bodySize: 18 });
  text(slide, "chain-arrow-a", "→", 380, 308, 60, 40, { size: 34, color: C.deepTeal, bold: true, align: "center" });
  const chainA2 = card(slide, "chain-a2", 446, 265, 290, 136, "second call", "resolved model M₂\nrequest R₂(result₁)", { fill: C.white, accent: C.deepTeal, mono: true, titleSize: 22, bodySize: 18 });
  const chainB = card(slide, "chain-b", 848, 265, 342, 136, "paired trace", "same identities\nsame aligned result₁", { fill: C.white, accent: C.coral, mono: true, titleSize: 22, bodySize: 18 });
  slide.shapes.connect(chainA2, chainB, {
    kind: "straight", fromSide: "right", toSide: "left",
    line: { style: "solid", fill: C.coral, width: 2 },
    tail: { type: "triangle", width: "sm", length: "sm" },
  });
  slide.shapes.connect(chainB, chainA2, {
    kind: "straight", fromSide: "left", toSide: "right",
    line: { style: "solid", fill: C.coral, width: 2 },
    tail: { type: "triangle", width: "sm", length: "sm" },
  });
  card(slide, "chain-proof", 176, 445, 928, 110, "Required evidence", "Final rule must explain why both second requests and their resulting bills align.", { fill: C.white, accent: C.sand, titleSize: 21, titleH: 38, bodyY: 56, bodySize: 19 });
}

function drawPipeline(slide) {
  const stages = [
    ["SOURCE", "lexer + parser", C.sand],
    ["SCOPES", "resolved names", C.teal],
    ["ANALYSES", "flow + bound + relation", C.coral],
    ["IR", "regions + certificate", C.sand],
    ["EVIDENCE", "diagnostics + offline run", C.teal],
  ];
  const x0 = 78;
  const gap = 18;
  const w = 205;
  stages.forEach(([tag, body, accent], i) => {
    const x = x0 + i * (w + gap);
    card(slide, `pipe-${i}`, x, 304, w, 178, tag, body, { dark: true, accent, titleSize: 18, bodySize: 18, bodyY: 72 });
    if (i < stages.length - 1) text(slide, `pipe-arrow-${i}`, "→", x + w, 358, gap + 2, 42, { size: 26, color: C.pale, bold: true, align: "center" });
  });
  text(slide, "pipe-bottom", "No model key, live provider call, or network access is needed for the static checks.", 100, 543, 1080, 44, { size: 19, color: C.pale, align: "center" });
}

function drawDiagnostic(slide, evidence) {
  card(slide, "diag-source", 82, 255, 520, 300, "SOURCE SPAN", evidence.diagnosticSourceSnippet, { fill: C.white, accent: C.coral, titleSize: 20, bodySize: 16.5, mono: true, bodyY: 65 });
  const diagnosticExcerpt = evidence.diagnosticOutput.replace(
    /^examples\/research\/rejected\/([^:\n]+):(\d+:\d+:)/,
    "$1:$2\n",
  );
  card(slide, "diag-output", 680, 255, 520, 300, "COMPILER DIAGNOSTIC", diagnosticExcerpt, { fill: C.white, accent: C.rust, titleSize: 20, bodySize: 16.5, mono: true, bodyY: 65 });
}

function drawProtocol(slide) {
  const rows = [
    ["1  COMPILE", "Regression suite and exact diagnostics", C.sand],
    ["2  BOUND", "Run generated workflows; compare each component to its bound", C.teal],
    ["3  RELATION", "Pair executions with fixed public inputs and aligned oracle", C.coral],
  ];
  rows.forEach(([title, body, accent], i) => card(slide, `protocol-${i}`, 98, 258 + i * 108, 1084, 86, title, body, { dark: true, accent, titleSize: 20, titleH: 34, bodyY: 42, bodySize: 17 }));
  text(slide, "protocol-caveat", "Finite runs validate implementation behavior; formal soundness needs a separate argument.", 145, 594, 990, 29, { size: 17, color: C.pale, align: "center" });
}

function drawMetrics(slide, evidence) {
  const items = evidence.metrics || [];
  const xs = [82, 372, 662, 952];
  items.forEach((m, i) => {
    const accent = [C.deepTeal, C.coral, C.teal, C.rust][i % 4];
    rect(slide, `metric-${i}-panel`, xs[i], 302, 246, 220, C.white, C.border, 8);
    rect(slide, `metric-${i}-stripe`, xs[i], 302, 246, 8, accent);
    text(slide, `metric-${i}-value`, m.value, xs[i] + 18, 340, 210, 65, { size: 36, color: accent, bold: true, align: "center" });
    text(slide, `metric-${i}-label`, m.label, xs[i] + 18, 410, 210, 52, { size: 19, color: C.ink, bold: true, align: "center" });
    text(slide, `metric-${i}-detail`, m.detail, xs[i] + 18, 472, 210, 35, { size: 15, color: C.slate, align: "center" });
  });
  text(slide, "metric-revision", `${evidence.sourceReportsChecked} independent source-bound reports checked  ·  compiler SHA-256 ${evidence.compilerShaShort}`, 95, 558, 1090, 30, { size: 13.5, color: C.slate, mono: true, align: "center" });
}

function drawTrace(slide, ev) {
  const colW = 490;
  const showPair = (pair) =>
    "secret=false  " + pair.false.calls + "/" + pair.false.input + "/" + pair.false.output +
    "\nsecret=true   " + pair.true.calls + "/" + pair.true.input + "/" + pair.true.output +
    "\n\ncalls / input / output · " + pair.modelLabel;
  card(slide, "trace-ordinal", 90, 275, colW, 258, "ORDINAL MOCK  ·  contract/index", showPair(ev.ordinal), { dark: true, accent: C.teal, titleSize: 21, bodySize: 17, mono: true, bodyY: 72 });
  card(slide, "trace-request", 700, 275, colW, 258, "REQUEST-SENSITIVE  ·  contract/index/Q", showPair(ev.requestSensitive), { dark: true, accent: C.coral, titleSize: 20, bodySize: 17, mono: true, bodyY: 72 });
  text(slide, "trace-same", "SAME PUBLIC FIXTURE  ·  2,250/2,250 witnesses per mode  ·  repeated grids are not extra patterns", 105, 566, 1070, 34, { size: 15.5, color: C.sand, bold: true, align: "center" });
}
function drawLiterature(slide) {
  const cards = [
    ["RESOURCE-AWARE IFC", "Ngo et al. · IEEE S&P 2017\nResource behavior can be part of a noninterference guarantee.", C.deepTeal],
    ["RELATIONAL COST", "Çiçek et al. · POPL 2017\nRelational reasoning bounds cost differences between runs.", C.coral],
    ["PROBABILISTIC COST", "Ngo et al. · PLDI 2018\nExpected resource bounds for probabilistic programs.", C.deepTeal],
    ["PROBABILISTIC LLM FLOWS", "Mandel et al. · ICML 2026\nPPDL propagates uncertainty across LLM and tool calls.", C.coral],
    ["QUANTITATIVE SIDE CHANNELS", "Basin & Köpf · CCS 2007\nInformation-theoretic analysis of adaptive observations.", C.deepTeal],
    ["LLM LENGTH CHANNELS", "Weiss et al. · 2024; Zhang et al. · 2024\nToken length and timing can expose information.", C.rust],
  ];
  cards.forEach(([head, body, accent], i) => {
    const x = 76 + (i % 3) * 390;
    const y = i < 3 ? 252 : 423;
    card(slide, `lit-${i}`, x, y, 354, 146, head, body, { fill: C.white, accent, titleSize: 17, titleH: 42, bodyY: 62, bodySize: 17.5 });
  });
  text(slide, "lit-scope", "OrchLang's scope: a sufficient compiler check for its declared bill observation and coupling.", 98, 586, 1084, 30, { size: 17, color: C.ink, bold: true, align: "center" });
}

function drawLimits(slide) {
  card(slide, "limits-supported", 84, 265, 520, 275, "SUPPORTED ENVELOPE", "Local structural signature check\nUnary token bounds under declared caps\nMatched two-call alignment for compatible contracts", { dark: true, accent: C.teal, titleSize: 21, bodySize: 19, bodyY: 68 });
  card(slide, "limits-open", 676, 265, 520, 275, "OPEN / ASSUMPTIONS", "Certificate withholds workflow claim on declassification\nFull provider payload and real tokenizers\nIncomplete rule; three mock precision probes", { dark: true, accent: C.coral, titleSize: 21, bodySize: 18, bodyY: 68 });
  text(slide, "limits-close", "A useful guarantee starts by naming exactly what is observed and compared.", 115, 564, 1050, 40, { size: 22, color: C.paper, bold: true, align: "center" });
}

function drawAppendix(slide, spec, index) {
  const blocks = spec.blocks || [];
  const xs = [82, 652];
  const ys = [260, 378, 496];
  blocks.forEach((b, i) => {
    const x = xs[i % 2];
    const y = ys[Math.floor(i / 2)];
    const body = spec.details[i];
    card(slide, `app-${index}-${i}`, x, y, 545, 94, b, body, {
      dark: Boolean(spec.dark),
      accent: [C.teal, C.coral, C.sand, C.deepTeal][i % 4],
      titleSize: 17,
      titleH: 25,
      bodyY: 48,
      bodySize: 15.5,
    });
  });
}

function drawQA(slide, spec) {
  const questions = spec.questions || [];
  const rowGap = Math.min(61, 360 / Math.max(questions.length, 1));
  const rowHeight = rowGap - 9;
  questions.forEach(([q, a], i) => {
    const y = 248 + i * rowGap;
    text(slide, `qa-${i}-q`, q, 78, y, 330, rowHeight, { size: 16.5, color: i % 2 ? C.teal : C.coral, bold: true });
    text(slide, `qa-${i}-a`, a, 420, y, 770, rowHeight, { size: 16, color: C.paper });
    if (i < questions.length - 1) rect(slide, `qa-${i}-rule`, 78, y + rowGap - 8, 1114, 1, C.darkBorder);
  });
}

function drawReferences(slide) {
  const refs = [
    "[1] Ngo et al. · IEEE S&P 2017 · resource-aware noninterference · DOI 10.1109/SP.2017.53",
    "[2] Çiçek et al. · POPL 2017 · Relational Cost Analysis · DOI 10.1145/3009837.3009858",
    "[3] Ngo et al. · PLDI 2018 · Bounded Expectations · DOI 10.1145/3192366.3192394",
    "[4] Mandel et al. · ICML 2026 · PPDL · PMLR 306:86172–86197",
    "[5] Basin & Köpf · CCS 2007 · quantitative side channels · DOI 10.1145/1315245.1315282",
    "[6] Weiss et al. · USENIX Security 2024 · token-length inference",
    "[7] Zhang et al. · Time Will Tell · arXiv:2412.15431 (preprint)",
    "[8] Dong et al. · ACL 2025 · APPL · DOI 10.18653/v1/2025.acl-long.63",
  ];
  refs.forEach((r, i) => {
    const y = 273 + i * 43;
    text(slide, `ref-${i}`, r, 78, y, 690, 38, { size: 14.5, color: C.ink });
    if (i < refs.length - 1) rect(slide, `ref-rule-${i}`, 78, y + 39, 690, 1, C.border);
  });

  text(slide, "ref-heading", "CORE REFERENCES", 78, 238, 690, 22, { size: 14, color: C.deepTeal, bold: true });
  rect(slide, "ref-column-rule", 784, 238, 1, 382, C.border);
  rect(slide, "novelty-panel", 808, 238, 400, 382, C.night, C.darkBorder, 10);
  text(slide, "novelty-heading", "NOVELTY RUBRIC  ·  0–10", 830, 257, 354, 24, { size: 15, color: C.teal, bold: true });
  text(slide, "novelty-scale", "5 = focused contribution from established ideas\n10 = major field-level advance · not acceptance odds", 830, 286, 354, 42, { size: 14, color: C.pale });
  text(slide, "novelty-legend-before", "BEFORE", 830, 333, 110, 18, { size: 12, color: C.pale, bold: true });
  text(slide, "novelty-legend-current", "CURRENT", 1072, 333, 110, 18, { size: 12, color: C.teal, bold: true, align: "right" });

  const rows = [
    { label: "Overall applied", before: 4.5, current: 5.5, delta: "+1.0" },
    { label: "Domain-specific method", before: 3.5, current: 5.5, delta: "+2.0" },
    { label: "General theory", before: 2.5, current: 3.0, delta: "+0.5" },
  ];
  rows.forEach((r, i) => {
    const y = 356 + i * 82;
    text(slide, `novelty-label-${i}`, r.label, 830, y, 245, 24, { size: 15.5, color: C.paper, bold: true });
    text(slide, `novelty-score-${i}`, `${r.before.toFixed(1)} → ${r.current.toFixed(1)}  (${r.delta})`, 1050, y, 134, 24, { size: 13.5, color: C.coral, bold: true, align: "right" });
    rect(slide, `novelty-track-before-${i}`, 830, y + 31, 350, 6, C.darkBorder);
    rect(slide, `novelty-bar-before-${i}`, 830, y + 31, 35 * r.before, 6, C.sand);
    rect(slide, `novelty-track-current-${i}`, 830, y + 44, 350, 6, C.darkBorder);
    rect(slide, `novelty-bar-current-${i}`, 830, y + 44, 35 * r.current, 6, C.teal);
    if (i < rows.length - 1) rect(slide, `novelty-separator-${i}`, 830, y + 66, 350, 1, C.darkBorder);
  });
  text(slide, "novelty-footnote", "Scores reflect a narrower applied claim; theory stays modest.", 830, 603, 354, 14, { size: 11.5, color: C.pale, italic: true });
}

function drawRelatedSystems(slide) {
  const items = [
    ["APPL · ACL 2025", "Prompt language and parallel/asynchronous runtime; tracing and replay.", C.teal],
    ["PPDL · ICML 2026", "Probabilistic LLM flows; uncertainty propagates across calls and tools.", C.coral],
    ["CaMeL · preprint", "Separates trusted control/data flow and constrains tool capabilities.", C.teal],
    ["Fides · preprint", "Information-flow labels and policy enforcement for AI agents.", C.coral],
    ["Agentproof · preprint", "Static workflow-graph checks and policy-trace verification.", C.teal],
    ["AgentFlow · preprint", "Flow policies, bounded verification, and runtime monitoring.", C.coral],
  ];
  items.forEach(([head, body, accent], i) => {
    const x = 76 + (i % 3) * 390;
    const y = i < 3 ? 251 : 420;
    card(slide, `neighbor-${i}`, x, y, 354, 142, head, body, {
      dark: true, accent, titleSize: 19, titleH: 38, bodyY: 58, bodySize: 17,
    });
  });
  text(slide, "neighbor-boundary", "These systems address workflow, uncertainty, and agent security. OrchLang checks equality of modeled bill traces.", 88, 582, 1105, 36, { size: 17, color: C.pale, bold: true, align: "center" });
}

function drawGraphArchitecture(slide) {
  card(slide, "graph-arch-dsl", 78, 255, 520, 296, "FROZEN C++ FRONT END", "OrchLang source\n→ finite AST\n→ flow, unary bounds, relational gate\n\nLiteral bounded retries; no general cyclic syntax.", {
    dark: true, accent: C.sand, titleSize: 23, bodySize: 19, mono: true, bodyY: 74,
  });
  card(slide, "graph-arch-json", 682, 255, 520, 296, "EXPERIMENTAL JSON FRONT END", "orchlang-request-graph v1\n→ finite control states with back-edges\n→ relational product worklist\n→ certificate + separate replayer", {
    dark: true, accent: C.teal, titleSize: 22, bodySize: 19, mono: true, bodyY: 74,
  });
  text(slide, "graph-arch-separate", "SEPARATE INPUT MODEL", 505, 318, 270, 26, { size: 14, color: C.coral, bold: true, align: "center" });
  text(slide, "graph-arch-caveat", "The JSON graph is an explicit model. No source-to-graph or framework-to-graph fidelity is established.", 108, 581, 1065, 32, { size: 18, color: C.pale, bold: true, align: "center" });
}

function drawGraphCounterexample(slide) {
  text(slide, "graph-loop-fixed", "FIXED PUBLIC QUERY  ·  seed 1  ·  first finite witness", 96, 246, 1080, 25, { size: 15, color: C.pale, mono: true, bold: true, align: "center" });
  const left = card(slide, "graph-loop-false", 82, 296, 515, 218, "route = false", "call #0  Process(query)\n\nthen STOP", { dark: true, accent: C.teal, titleSize: 22, bodySize: 20, mono: true, bodyY: 72 });
  const right = card(slide, "graph-loop-true", 682, 296, 515, 218, "route = true", "call #0  Process(query)\ncall #1  Process(result)\npublic result guard → loop or stop", { dark: true, accent: C.coral, titleSize: 22, bodySize: 18.5, mono: true, bodyY: 68 });
  slide.shapes.connect(left, right, { kind: "straight", fromSide: "right", toSide: "left", line: { style: "solid", fill: C.sand, width: 2 }, tail: { type: "triangle", width: "sm", length: "sm" } });
  slide.shapes.connect(right, left, { kind: "straight", fromSide: "left", toSide: "right", line: { style: "solid", fill: C.sand, width: 2 }, tail: { type: "triangle", width: "sm", length: "sm" } });
  text(slide, "graph-loop-shared", "event 0 matches", 515, 326, 250, 25, { size: 15, color: C.teal, bold: true, align: "center" });
  text(slide, "graph-loop-diff", "event 1:  stop  vs  call   →   reject", 301, 548, 678, 34, { size: 20, color: C.coral, bold: true, mono: true, align: "center" });
}

function drawGraphObservation(slide) {
  card(slide, "graph-observe-premise", 82, 264, 1085, 92, "PAIRED RUNS", "same graph · equal public-input identities · secrets may differ", { fill: C.white, accent: C.deepTeal, titleSize: 20, titleH: 29, bodyY: 47, bodySize: 19, mono: true });
  card(slide, "graph-observe-event", 82, 379, 525, 130, "VISIBLE EVENT", "(resolved contract, input usage, output usage)", { fill: C.white, accent: C.coral, titleSize: 20, titleH: 30, bodyY: 62, bodySize: 19, mono: true });
  card(slide, "graph-observe-coupling", 642, 379, 525, 130, "COUPLING", "Ω(contract, per-contract index, exact DSL request)", { fill: C.white, accent: C.teal, titleSize: 20, titleH: 30, bodyY: 62, bodySize: 18.5, mono: true });
  text(slide, "graph-observe-claim", "Claim: every finite modeled usage-event prefix agrees; termination and total-cost bounds are separate.", 100, 554, 1050, 38, { size: 18, color: C.ink, bold: true, align: "center" });
}

function drawGraphProduct(slide) {
  const left = card(slide, "product-left", 80, 275, 330, 228, "LEFT RUN", "pcL = state 12\nregisters: a, b", { dark: true, accent: C.coral, mono: true, titleSize: 21, bodySize: 19, bodyY: 74 });
  const right = card(slide, "product-right", 870, 275, 330, 228, "RIGHT RUN", "pcR = state 27\nregisters: x, y", { dark: true, accent: C.teal, mono: true, titleSize: 21, bodySize: 19, bodyY: 74 });
  const product = card(slide, "product-node", 474, 260, 332, 258, "PRODUCT WORK ITEM", "(pcL, pcR, R)\n\nR = justified equal-register pairs\n{ a ↔ x, b ↔ y }", { dark: true, accent: C.sand, mono: true, titleSize: 20, bodySize: 18, bodyY: 68 });
  slide.shapes.connect(left, product, { kind: "straight", fromSide: "right", toSide: "left", line: { style: "solid", fill: C.coral, width: 2 }, tail: { type: "triangle", width: "sm", length: "sm" } });
  slide.shapes.connect(right, product, { kind: "straight", fromSide: "left", toSide: "right", line: { style: "solid", fill: C.teal, width: 2 }, tail: { type: "triangle", width: "sm", length: "sm" } });
  text(slide, "product-invariant", "The relation is updated only when a matched call and shared Ω justify equal results.", 120, 563, 1040, 37, { size: 18, color: C.pale, bold: true, align: "center" });
}

function drawGraphRules(slide) {
  const cards = [
    ["SECRET GUARD", "Explore every left/right successor pair.", C.coral],
    ["PUBLIC GUARD", "Same normalized test on R-related values; take the same arm.", C.teal],
    ["CALL / CALL", "Match full contract, template, ordered atoms; update R after Ω.", C.deepTeal],
    ["STOP / STOP", "Both stop together. A stop/call mismatch rejects.", C.rust],
  ];
  cards.forEach(([head, body, accent], i) => {
    const x = 82 + (i % 2) * 562;
    const y = 270 + Math.floor(i / 2) * 140;
    card(slide, `graph-rule-${i}`, x, y, 525, 112, head, body, { dark: Boolean(i % 2), accent, titleSize: 19, titleH: 31, bodyY: 54, bodySize: 17.5 });
  });
  text(slide, "graph-rules-alg", "Reachable product worklist · universal secret choices · fail closed on unsupported states or state-cap exhaustion", 96, 576, 1088, 36, { size: 16.5, color: C.slate, bold: true, align: "center" });
}

function drawGraphCycle(slide, evidence) {
  const left = card(slide, "cycle-left-path", 82, 266, 495, 222, "LEFT CONTROL CYCLE", "call m(Process query) → a\ncall m(Process a) → b\ngoto choose", { fill: C.white, accent: C.coral, titleSize: 20, titleH: 34, bodyY: 74, bodySize: 18.5, mono: true });
  const right = card(slide, "cycle-right-path", 700, 266, 495, 222, "RIGHT CONTROL CYCLE", "call m(Process query) → x\ncall m(Process x) → y\ngoto choose", { fill: C.white, accent: C.teal, titleSize: 20, titleH: 34, bodyY: 74, bodySize: 18.5, mono: true });
  slide.shapes.connect(left, right, {
    kind: "straight", fromSide: "right", toSide: "left", line: { style: "solid", fill: C.sand, width: 2 }, tail: { type: "triangle", width: "sm", length: "sm" },
  });
  slide.shapes.connect(right, left, {
    kind: "straight", fromSide: "left", toSide: "right", line: { style: "solid", fill: C.sand, width: 2 }, tail: { type: "triangle", width: "sm", length: "sm" },
  });
  label(slide, "cycle-close", "coinductive product-cycle closure", 370, 515, 540, { fill: C.deepTeal, color: C.paper });
  text(slide, "cycle-claim", "Closes all finite usage prefixes under Ω. It does not prove termination or a finite total-token / price bound.", 95, 563, 1090, 44, { size: 17, color: C.paper, bold: true, align: "center" });
  if (evidence?.graph) {
    text(slide, "cycle-probe", `${evidence.graph.productiveCalls.toLocaleString()} calls in the finite probe · ${evidence.graph.truncatedCycleRuns} runs hit the 120-call cap`, 150, 614, 980, 20, { size: 13, color: C.pale, mono: true, align: "center" });
  }
}

function drawGraphReplay(slide, evidence) {
  const nodes = [
    ["GRAPH INPUT", "raw JSON + source hash", C.sand],
    ["PRODUCER", "product closure + certificate", C.coral],
    ["REPLAYER", "rebuild every node, edge, rule, R", C.teal],
  ];
  const boxes = nodes.map(([head, body, accent], i) => card(slide, `replay-${i}`, 76 + i * 402, 282, 352, 190, head, body, { dark: true, accent, titleSize: 20, bodySize: 17, bodyY: 72 }));
  for (let i = 0; i < 2; i++) slide.shapes.connect(boxes[i], boxes[i + 1], { kind: "straight", fromSide: "right", toSide: "left", line: { style: "solid", fill: C.pale, width: 2 }, tail: { type: "triangle", width: "sm", length: "sm" } });
  text(slide, "replay-verdict", `VERIFIED  ·  ${evidence.graph.replayedCertificates}/${evidence.graph.acceptedCertificates} accepting certificates replayed`, 96, 508, 1088, 34, { size: 19, color: C.teal, bold: true, align: "center" });
  text(slide, "replay-limit", "Replay checks certificate closure under the graph rules; it does not verify graph-to-source fidelity or mechanize the relational theorem.", 98, 558, 1085, 46, { size: 16.5, color: C.pale, align: "center" });
}

function drawStaleRegister(slide, evidence) {
  const rows = [
    ["LEFT", "#0 query → a", "#1 query → a  (overwrite)", "#2 request(a) → b", C.coral],
    ["RIGHT", "#0 query → x", "#1 query → y", "#2 request(x) → y", C.teal],
  ];
  rows.forEach(([side, first, second, third, accent], i) => {
    const y = 276 + i * 132;
    label(slide, `stale-${i}-side`, side, 78, y + 30, 98, { fill: accent, color: C.ink });
    card(slide, `stale-${i}-first`, 197, y, 266, 92, "CALL 0", first, { fill: C.white, accent, titleSize: 16.5, titleH: 26, bodyY: 50, bodySize: 16, mono: true });
    card(slide, `stale-${i}-second`, 500, y, 300, 92, "CALL 1", second, { fill: C.white, accent, titleSize: 16.5, titleH: 26, bodyY: 50, bodySize: 15.5, mono: true });
    card(slide, `stale-${i}-third`, 837, y, 350, 92, "CALL 2", third, { fill: C.white, accent: i === 0 ? C.rust : accent, titleSize: 16.5, titleH: 26, bodyY: 50, bodySize: 15.5, mono: true });
  });
  text(slide, "stale-relation", "After overwrite: a ↔ y, not x. The third arguments are not proved equal.", 150, 548, 980, 30, { size: 18, color: C.ink, bold: true, align: "center" });
  const witness = evidence.graph.staleWitness;
  text(slide, "stale-witness", `One finite mock witness at event ${witness.eventIndex}: input usage ${witness.leftInput} vs ${witness.rightInput} · not a provider invoice.`, 110, 584, 1060, 30, { size: 15.5, color: C.rust, mono: true, align: "center" });
}

function drawGraphMetrics(slide, evidence) {
  const g = evidence.graph;
  const items = [
    { value: String(g.fixtureCount), label: "authored JSON fixtures", detail: `${g.acceptedFixtures} accept · ${g.rejectedFixtures} reject · ${g.invalidFixtures} invalid` },
    { value: g.acceptedRuns.toLocaleString(), label: "accepted reference runs", detail: `${g.acceptedComparisons.toLocaleString()} secret-assignment pairs` },
    { value: "0", label: "accepted mismatches", detail: `${g.accountingChecks.toLocaleString()} call-accounting checks` },
    { value: `${g.replayedCertificates}/${g.acceptedCertificates}`, label: "accepted certs replayed", detail: `${g.finiteWitnessRejects}/${g.rejectedFixtures} rejected with finite full-trace witnesses` },
  ];
  items.forEach((m, i) => {
    const accent = [C.deepTeal, C.coral, C.teal, C.rust][i];
    const x = [82, 372, 662, 952][i];
    rect(slide, `graph-metric-${i}-panel`, x, 290, 246, 218, C.white, C.border, 8);
    rect(slide, `graph-metric-${i}-stripe`, x, 290, 246, 8, accent);
    text(slide, `graph-metric-${i}-value`, m.value, x + 14, 326, 218, 61, { size: 34, color: accent, bold: true, align: "center" });
    text(slide, `graph-metric-${i}-label`, m.label, x + 16, 394, 214, 52, { size: 17, color: C.ink, bold: true, align: "center" });
    text(slide, `graph-metric-${i}-detail`, m.detail, x + 14, 456, 218, 43, { size: 14, color: C.slate, align: "center" });
  });
  text(slide, "graph-metric-scope", "Authored graph models · finite Ω probes · no external framework ports · not a proof of the checker semantics", 90, 548, 1100, 33, { size: 16, color: C.slate, bold: true, align: "center" });
}

function drawStressMetrics(slide, evidence) {
  const s = evidence.stress;
  const items = [
    { value: String(s.caseCount), label: "generated C++ cases", detail: `${s.acceptedCases} accepted · ${s.rejectedCases} mutations rejected` },
    { value: s.referenceRuns.toLocaleString(), label: "independent reference runs", detail: "full rendered request text" },
    { value: `0 / ${s.pairComparisons.toLocaleString()}`, label: "mismatch / accepted pairs", detail: "request and usage traces" },
    { value: s.accountingChecks.toLocaleString(), label: "per-call accounting checks", detail: `${s.witnessCases} mutation witnesses · ${s.unknownCases} unknown` },
  ];
  items.forEach((m, i) => {
    const accent = [C.deepTeal, C.coral, C.teal, C.rust][i];
    const x = [82, 372, 662, 952][i];
    rect(slide, `stress-metric-${i}-panel`, x, 286, 246, 218, C.white, C.border, 8);
    rect(slide, `stress-metric-${i}-stripe`, x, 286, 246, 8, accent);
    text(slide, `stress-metric-${i}-value`, m.value, x + 14, 322, 218, 61, { size: 32, color: accent, bold: true, align: "center" });
    text(slide, `stress-metric-${i}-label`, m.label, x + 16, 390, 214, 52, { size: 17, color: C.ink, bold: true, align: "center" });
    text(slide, `stress-metric-${i}-detail`, m.detail, x + 14, 452, 218, 43, { size: 14, color: C.slate, align: "center" });
  });
  text(slide, "stress-scope", "C++ checker only compiles cases; a separate Python interpreter substitutes full text. Synthetic cases, not a proof or provider test.", 95, 548, 1090, 42, { size: 15.5, color: C.pale, bold: true, align: "center" });
}

function drawGraphAdversarial(slide, evidence) {
  const a = evidence.graphAdversarial;
  card(slide, "adversarial-counts", 82, 267, 520, 248, "SEEDED SMALL-GRAPH PROBE", `${a.generated.toLocaleString()} generated graphs\n${a.accepted.toLocaleString()} accepted\n${a.comparisons.toLocaleString()} ordered equal-public store pairs\n${a.distinctSecretComparisons.toLocaleString()} distinct-secret pairs`, { dark: true, accent: C.teal, titleSize: 20, bodySize: 19, mono: true, bodyY: 74 });
  card(slide, "adversarial-zero", 682, 267, 520, 248, "OBSERVED ON THE PROBE GRID", `${a.mismatches} complete-observation mismatches\n\nrequest · input/output usage\nresponse bytes · stop/truncation status`, { dark: true, accent: C.coral, titleSize: 20, bodySize: 18, mono: true, bodyY: 74 });
  text(slide, "adversarial-caveat", "Supplementary adversarial coverage only: generator and reference use the same producer module; small Boolean/literal graph domain; prefixes capped at 20 calls.", 95, 553, 1090, 48, { size: 16, color: C.slate, align: "center" });
}

function drawContributionBoundary(slide) {
  card(slide, "delta-established", 82, 270, 515, 280, "ESTABLISHED FOUNDATIONS", "Self-composition and product programs\nResource-aware noninterference\nRelational cost analysis\nUnary graph-level resource bounds", { dark: true, accent: C.sand, titleSize: 20, bodySize: 18, bodyY: 72 });
  card(slide, "delta-project", 682, 270, 515, 280, "THIS PROTOTYPE'S NARROW DELTA", "A finite product over a workflow graph\nResolved model-call event matching\nRequest-linked result-register relation\nReplayable reachable-product certificate", { dark: true, accent: C.teal, titleSize: 19, bodySize: 18, bodyY: 72 });
  text(slide, "delta-boundary", "Application and software artifact contribution; no new general product-program theory.", 140, 574, 1000, 34, { size: 17, color: C.pale, bold: true, align: "center" });
}

function drawGraphLimits(slide) {
  card(slide, "graph-limit-claim", 82, 258, 515, 298, "CHECKED UNDER THE MODEL", "Finite JSON control graph\nPublic inputs equal by identity\nSecret choices universally paired\nPer-call usage-event prefixes\nShared Ω(contract, index, request)", { fill: C.white, accent: C.deepTeal, titleSize: 19, bodySize: 17, bodyY: 68, mono: true });
  card(slide, "graph-limit-open", 682, 258, 515, 298, "NOT ESTABLISHED", "Source/framework → graph fidelity\nReal provider request serialization\nTermination or finite total-cost bound\nTiming, tools, output confidentiality\nMechanized relational metatheory", { fill: C.white, accent: C.rust, titleSize: 19, bodySize: 17, bodyY: 68 });
  text(slide, "graph-limit-close", "A verified certificate is a checked graph-model result, not a verified deployed workflow.", 95, 574, 1090, 35, { size: 18, color: C.ink, bold: true, align: "center" });
}

function drawGraphReferences(slide) {
  const refs = [
    "[1] Barthe et al. · self-composition · IEEE CSFW 2004 · DOI 10.1109/CSFW.2004.1310735",
    "[2] Barthe, Crespo & Kunz · product programs · JLAMP 2016 · DOI 10.1016/j.jlamp.2016.05.004",
    "[3] Ngo et al. · resource-aware IFC · IEEE S&P 2017 · DOI 10.1109/SP.2017.53",
    "[4] Çiçek et al. · Relational Cost Analysis · POPL 2017 · DOI 10.1145/3009837.3009858",
    "[5] Dickerson · Petri-net LLM cost bounds · Loom Research, May 2026 · author-reported, unrefereed",
    "[6] Mandel et al. · PPDL · ICML 2026 · PMLR 306:86172–86197",
    "[7] Agentproof · arXiv:2603.20356 · preprint; AgentFlow · arXiv:2608.22868 · preprint",
    "[8] Weiss et al. · USENIX Security 2024 · token-length leakage; see sources.md for full bibliography",
  ];
  refs.forEach((r, i) => {
    const y = 259 + i * 41;
    text(slide, `graph-ref-${i}`, r, 77, y, 682, 36, { size: 13.5, color: C.ink });
    if (i < refs.length - 1) rect(slide, `graph-ref-rule-${i}`, 77, y + 37, 682, 1, C.border);
  });
  text(slide, "graph-ref-heading", "SELECTED PRIOR WORK", 78, 228, 690, 22, { size: 14, color: C.deepTeal, bold: true });
  rect(slide, "graph-ref-column", 784, 230, 1, 385, C.border);
  card(slide, "graph-ref-delta", 808, 239, 400, 370, "CONTRIBUTION BOUNDARY", "Established: resource-aware IFC, relational cost, product programs, unary graph cost bounds.\n\nProposed delta: model-call request/event matching in a cyclic workflow-graph product, with an independently replayed closure.\n\nNo score is shown before the research assessment is frozen.", { dark: true, accent: C.teal, titleSize: 18, bodySize: 16.5, bodyY: 72 });
}

function drawUsageLaws(slide) {
  text(slide, "laws-axis-title", "OUTPUT USAGE PER CALL  ·  tokens", 90, 244, 390, 24, { size: 14, color: C.pale, bold: true });
  const xs = [405, 548, 691];
  [1, 2, 3].forEach((n, i) => text(slide, `laws-axis-${n}`, String(n), xs[i] + 10, 560, 34, 22, { size: 15, color: C.pale, mono: true, align: "center" }));
  text(slide, "laws-a", "TEMPLATE A", 90, 305, 250, 27, { size: 16, color: C.coral, bold: true });
  text(slide, "laws-a-sub", "P(1)=1/2   P(3)=1/2", 90, 335, 260, 54, { size: 18, color: C.paper, mono: true });
  rect(slide, "laws-a-baseline", 360, 386, 440, 1, C.darkBorder);
  rect(slide, "laws-a-bar1", xs[0], 316, 54, 70, C.coral);
  rect(slide, "laws-a-bar3", xs[2], 316, 54, 70, C.coral);
  text(slide, "laws-a-prob1", "1/2", xs[0] + 2, 284, 50, 24, { size: 15, color: C.paper, bold: true, mono: true, align: "center" });
  text(slide, "laws-a-prob3", "1/2", xs[2] + 2, 284, 50, 24, { size: 15, color: C.paper, bold: true, mono: true, align: "center" });

  text(slide, "laws-b", "TEMPLATE B", 90, 454, 250, 27, { size: 16, color: C.teal, bold: true });
  text(slide, "laws-b-sub", "P(2)=1", 90, 484, 260, 54, { size: 18, color: C.paper, mono: true });
  rect(slide, "laws-b-baseline", 360, 535, 440, 1, C.darkBorder);
  rect(slide, "laws-b-bar2", xs[1], 415, 54, 120, C.teal);
  text(slide, "laws-b-prob2", "1", xs[1] + 2, 383, 50, 24, { size: 15, color: C.paper, bold: true, mono: true, align: "center" });

  rect(slide, "laws-stat-divider", 840, 264, 1, 323, C.darkBorder);
  text(slide, "laws-mean-label", "EXPECTED OUTPUT", 880, 286, 300, 24, { size: 14, color: C.pale, bold: true });
  text(slide, "laws-mean-value", "2  =  2", 876, 324, 310, 55, { size: 34, color: C.paper, mono: true, bold: true, align: "center" });
  rect(slide, "laws-mean-rule", 890, 393, 275, 1, C.darkBorder);
  text(slide, "laws-tv", "TV  =  1", 876, 424, 310, 48, { size: 30, color: C.coral, mono: true, bold: true, align: "center" });
  text(slide, "laws-mi", "I(secret ; usage)  ≈  1 bit", 860, 486, 340, 48, { size: 18, color: C.teal, mono: true, bold: true, align: "center" });
  text(slide, "laws-scope", "Uniform prior · finite authored kernel · H=1", 154, 601, 982, 24, { size: 15, color: C.pale, align: "center" });
}

function drawObserverSplit(slide) {
  text(slide, "obs-setup", "TWO CALLS  ·  SAME MODEL  ·  BOTH RUNS STOP", 90, 238, 1090, 24, { size: 14, color: C.deepTeal, bold: true, mono: true, align: "center" });
  card(slide, "obs-left-a", 86, 282, 500, 92, "SECRET = 0", "output usage: 1  →  3", { fill: C.white, accent: C.coral, titleSize: 18, titleH: 27, bodyY: 48, bodySize: 20, mono: true });
  card(slide, "obs-left-b", 86, 394, 500, 92, "SECRET = 1", "output usage: 3  →  1", { fill: C.white, accent: C.teal, titleSize: 18, titleH: 27, bodyY: 48, bodySize: 20, mono: true });
  text(slide, "obs-left-label", "ORDERED TRACE", 90, 507, 220, 24, { size: 14, color: C.slate, bold: true });
  text(slide, "obs-left-values", "(1,3) ≠ (3,1)", 90, 535, 300, 38, { size: 23, color: C.rust, mono: true, bold: true });
  text(slide, "obs-left-tv", "TV = 1", 424, 530, 144, 42, { size: 25, color: C.rust, mono: true, bold: true, align: "right" });

  rect(slide, "obs-split", 630, 272, 1, 306, C.border);
  card(slide, "obs-right-a", 690, 282, 500, 92, "SECRET = 0", "calls=2 · input=2 · output=4", { fill: C.white, accent: C.coral, titleSize: 18, titleH: 27, bodyY: 48, bodySize: 18, mono: true });
  card(slide, "obs-right-b", 690, 394, 500, 92, "SECRET = 1", "calls=2 · input=2 · output=4", { fill: C.white, accent: C.teal, titleSize: 18, titleH: 27, bodyY: 48, bodySize: 18, mono: true });
  text(slide, "obs-right-label", "AGGREGATE VECTOR", 694, 507, 250, 24, { size: 14, color: C.slate, bold: true });
  text(slide, "obs-right-values", "same billing row", 694, 535, 300, 38, { size: 21, color: C.deepTeal, bold: true });
  text(slide, "obs-right-tv", "TV = 0", 1028, 530, 144, 42, { size: 25, color: C.deepTeal, mono: true, bold: true, align: "right" });
  text(slide, "obs-horizon", "Exact channel result at horizon H=2 under the supplied finite kernel", 125, 596, 1030, 24, { size: 15, color: C.slate, align: "center" });
}

function drawThreeQuestions(slide) {
  const items = [
    ["01", "Unary bound", "How much can one run use?", "C(I) ≤ declared envelope", C.sand],
    ["02", "Paired trace", "Does changing a secret change usage?", "trace(run₀) = trace(run₁)", C.coral],
    ["03", "Finite channel", "What does an observation reveal?", "TV, vulnerability, MI", C.teal],
  ];
  items.forEach(([n, title, question, result, accent], i) => {
    const x = 86 + i * 382;
    text(slide, `questions-${i}-number`, n, x, 273, 80, 48, { size: 34, color: accent, mono: true, bold: true });
    rect(slide, `questions-${i}-rule`, x, 334, 316, 3, accent);
    text(slide, `questions-${i}-title`, title, x, 354, 320, 34, { size: 22, color: C.paper, bold: true });
    text(slide, `questions-${i}-question`, question, x, 401, 320, 67, { size: 18, color: C.pale });
    text(slide, `questions-${i}-result`, result, x, 500, 320, 55, { size: 16.5, color: accent, bold: true, mono: true });
    if (i < items.length - 1) rect(slide, `questions-${i}-separator`, x + 340, 275, 1, 290, C.darkBorder);
  });
  text(slide, "questions-scope", "Different inputs, different assumptions, different outputs", 160, 590, 960, 29, { size: 17, color: C.pale, align: "center" });
}

function drawArchitectureAll(slide) {
  const rows = [
    ["C++ COMPILER", "bounded OrchLang AST", "flow + unary cost + request relation", "finite syntax", C.deepTeal],
    ["JSON GRAPH", "versioned finite-control model", "product closure + certificate replay", "productive call cycles", C.coral],
    ["SOURCE PATHS", "OrchLang subset / Python AST", "export, replay, offline LangGraph", "authored restricted subsets", C.deepTeal],
    ["FINITE KERNELS", "graph + rational kernel", "DP channels + bisimulation + exact row span", "explicit finite stores", C.coral],
  ];
  rows.forEach(([head, inp, process, scope, accent], i) => {
    const y = 253 + i * 88;
    rect(slide, `arch-${i}-stripe`, 82, y, 6, 68, accent);
    text(slide, `arch-${i}-head`, head, 102, y + 4, 214, 25, { size: 15, color: accent, bold: true });
    text(slide, `arch-${i}-input`, inp, 102, y + 32, 270, 30, { size: 17, color: C.ink, bold: true });
    text(slide, `arch-${i}-process`, process, 415, y + 13, 510, 40, { size: 18, color: C.ink });
    text(slide, `arch-${i}-scope`, scope, 963, y + 14, 245, 38, { size: 15, color: C.slate, align: "right" });
    if (i < rows.length - 1) rect(slide, `arch-${i}-line`, 100, y + 73, 1108, 1, C.border);
  });
  text(slide, "arch-columns", "INPUT ARTIFACT                                      ANALYSIS                                     CLAIM SCOPE", 102, 231, 1105, 20, { size: 12.5, color: C.slate, bold: true });
  text(slide, "arch-caveat", "These paths share assumptions and report formats; the source and proof boundaries remain separate.", 104, 614, 1070, 22, { size: 15, color: C.slate, align: "center" });
}

function drawMetricRow(slide, items, prefix, opts = {}) {
  const xs = [82, 372, 662, 952];
  items.forEach((m, i) => {
    const accent = [C.deepTeal, C.coral, C.teal, C.rust][i];
    rect(slide, `${prefix}-${i}-panel`, xs[i], opts.top ?? 282, 246, opts.height ?? 224, opts.dark ? "#1C2638" : C.white, opts.dark ? C.darkBorder : C.border, 8);
    rect(slide, `${prefix}-${i}-stripe`, xs[i], opts.top ?? 282, 246, 8, accent);
    text(slide, `${prefix}-${i}-value`, m.value, xs[i] + 14, (opts.top ?? 282) + 34, 218, 60, { size: m.value.length > 12 ? 25 : 34, color: accent, bold: true, align: "center", mono: m.mono ?? false });
    text(slide, `${prefix}-${i}-label`, m.label, xs[i] + 16, (opts.top ?? 282) + 101, 214, 51, { size: 17, color: opts.dark ? C.paper : C.ink, bold: true, align: "center" });
    text(slide, `${prefix}-${i}-detail`, m.detail, xs[i] + 14, (opts.top ?? 282) + 161, 218, 48, { size: 14, color: opts.dark ? C.pale : C.slate, align: "center" });
  });
  if (opts.scope) text(slide, `${prefix}-scope`, opts.scope, 92, (opts.top ?? 282) + (opts.height ?? 224) + 33, 1096, 34, { size: 15, color: opts.dark ? C.pale : C.slate, bold: true, align: "center" });
}

function drawBoundedRuleMetrics(slide, evidence) {
  const left = card(slide, "bounded-request-left", 82, 274, 485, 220, "SECRET ALTERNATIVE 0", "M = (provider, actual ID, cap, price)\nQ = exact template + ordered atoms", { fill: C.white, accent: C.deepTeal, titleSize: 19, bodySize: 18, bodyY: 72, mono: true });
  const right = card(slide, "bounded-request-right", 713, 274, 485, 220, "SECRET ALTERNATIVE 1", "same resolved M\nsame Q and result position", { fill: C.white, accent: C.teal, titleSize: 19, bodySize: 18, bodyY: 72, mono: true });
  slide.shapes.connect(left, right, { kind: "straight", fromSide: "right", toSide: "left", line: { style: "solid", fill: C.deepTeal, width: 2 }, tail: { type: "triangle", width: "sm", length: "sm" } });
  text(slide, "bounded-pattern-count", "15 / 15", 130, 529, 260, 50, { size: 30, color: C.deepTeal, bold: true, mono: true, align: "center" });
  text(slide, "bounded-pattern-label", "balanced source-derived projections admitted", 112, 578, 305, 35, { size: 15, color: C.slate, align: "center" });
  text(slide, "bounded-baseline", "8 / 15", 512, 529, 220, 50, { size: 27, color: C.rust, bold: true, mono: true, align: "center" });
  text(slide, "bounded-baseline-label", "preceding frozen version", 502, 578, 240, 35, { size: 15, color: C.slate, align: "center" });
  text(slide, "bounded-variants", "45 authored variants · 30 source-bound reports checked · partial projections", 765, 542, 405, 55, { size: 16, color: C.ink, bold: true, align: "center" });
}

function drawSourceBridgeMetrics(slide, evidence) {
  const s = evidence.sourceBridge;
  drawMetricRow(slide, [
    { value: `${s.attempted}/${s.attempted}`, label: "source candidates", detail: "C++ gate passed" },
    { value: `${s.exported}/${s.attempted}`, label: "exported", detail: `${s.excluded} retry cases outside graph v1` },
    { value: s.runPairs.toLocaleString(), label: "source/graph run pairs", detail: "complete modeled traces" },
    { value: String(s.traceDifferences), label: "trace differences", detail: `${s.secretPairs} secret-trace comparisons` },
  ], "bridge-metric", { top: 278, height: 222, scope: "An experimental source adapter with a narrow subset; hashes bind files but do not verify translation." });
}

function drawLangGraphSourceMetrics(slide, evidence) {
  const s = evidence.langgraphSource;
  drawMetricRow(slide, [
    { value: s.frontendTests.toLocaleString(), label: "frontend tests", detail: "static AST subset" },
    { value: s.sourceRuns.toLocaleString(), label: "original-source runs", detail: "authored StateGraph functions" },
    { value: `${s.tracePairs} + ${s.valuePairs}`, label: "matched comparisons", detail: "accepted traces + rejection probes" },
    { value: String(s.traceDifferences + s.valueDifferences), label: "comparison differences", detail: "across the reported source grid" },
  ], "lg-source", { top: 278, height: 222, dark: true, scope: "Restricted Python AST programs only; no general source-to-graph correctness theorem." });
}

function drawLangGraphRuntimeMetrics(slide, evidence) {
  const s = evidence.langgraph;
  drawMetricRow(slide, [
    { value: s.version, label: "pinned LangGraph", detail: "offline runtime" },
    { value: s.executions.toLocaleString(), label: "executions", detail: `${s.stopped} stopped · ${s.truncated} truncated` },
    { value: s.events.toLocaleString(), label: "call-event pairs", detail: "request and usage traces" },
    { value: String(s.differences), label: "trace differences", detail: "on the finite test grid" },
  ], "lg-runtime", { top: 278, height: 222, scope: "Pinned local backend with a deterministic offline oracle; no provider call or billing record." });
}

function drawProbabilityModel(slide) {
  const nodes = [
    ["WORKFLOW", "finite control graph", C.deepTeal],
    ["KERNEL", "exact rational outcomes", C.coral],
    ["SCENARIOS", "fixed public store + prior", C.deepTeal],
    ["OBSERVER", "aggregate or ordered usage", C.coral],
  ];
  const boxes = nodes.map(([head, body, accent], i) => card(slide, `prob-input-${i}`, 76 + i * 304, 290, 274, 132, head, body, { fill: C.white, accent, titleSize: 18, titleH: 28, bodyY: 59, bodySize: 17 }));
  const center = card(slide, "prob-analyzer", 345, 475, 590, 88, "FINITE CHANNEL ANALYZER", "Horizon H = 1…32 · exact probability mass", { dark: true, accent: C.teal, titleSize: 20, titleH: 28, bodyY: 51, bodySize: 17.5, mono: true });
  for (const box of boxes) slide.shapes.connect(box, center, { kind: "straight", fromSide: "bottom", toSide: "top", line: { style: "solid", fill: C.sand, width: 1.5 }, tail: { type: "triangle", width: "sm", length: "sm" } });
  text(slide, "prob-scope", "Probabilities describe the supplied finite kernel, not a learned or provider-certified distribution.", 115, 588, 1050, 29, { size: 16, color: C.slate, bold: true, align: "center" });
}

function drawProbabilityDP(slide) {
  const stages = [
    ["depth d", "control + values\ncontract ordinals", C.deepTeal],
    ["call", "lookup K(M,k,Q,h)\ndistribute rational mass", C.coral],
    ["depth d+1", "usage + trace + history\nresource footprint", C.deepTeal],
  ];
  const nodes = stages.map(([head, body, accent], i) => card(slide, `dp-stage-${i}`, 76 + i * 403, 286, 350, 152, head, body, { dark: true, accent, titleSize: 20, titleH: 32, bodyY: 62, bodySize: 17, mono: true }));
  slide.shapes.connect(nodes[0], nodes[1], { kind: "straight", fromSide: "right", toSide: "left", line: { style: "solid", fill: C.pale, width: 2 }, tail: { type: "triangle", width: "sm", length: "sm" } });
  slide.shapes.connect(nodes[1], nodes[2], { kind: "straight", fromSide: "right", toSide: "left", line: { style: "solid", fill: C.pale, width: 2 }, tail: { type: "triangle", width: "sm", length: "sm" } });
  text(slide, "dp-merge-title", "MERGE CONDITION", 100, 485, 210, 22, { size: 14, color: C.teal, bold: true });
  text(slide, "dp-merge-text", "Every future-relevant value and observed/resource field is equal", 100, 514, 540, 54, { size: 19, color: C.paper, bold: true });
  rect(slide, "dp-split", 650, 486, 1, 96, C.darkBorder);
  text(slide, "dp-reference-title", "REFERENCE", 682, 485, 190, 22, { size: 14, color: C.coral, bold: true });
  text(slide, "dp-reference-text", "No-merge DFS path enumeration", 682, 514, 430, 54, { size: 19, color: C.paper, bold: true });
  text(slide, "dp-limits", "Rational caps or state/path limits return unknown", 118, 605, 1040, 22, { size: 15, color: C.pale, align: "center" });
}

function drawProbabilityMetrics(slide, evidence) {
  const p = evidence.probability;
  drawMetricRow(slide, [
    { value: String(p.fixtures), label: "authored fixtures", detail: `${p.accepted} accepted · ${p.rejected} rejected` },
    { value: String(p.analyses), label: "channel analyses", detail: "fixed stores, scenarios and horizons" },
    { value: `0 / ${p.histogramComparisons}`, label: "histogram differences", detail: "DP versus independent DFS" },
    { value: String(p.equalMeanPositiveTV), label: "equal-mean / positive-TV", detail: `${p.unknownProbes} resource probes returned unknown` },
  ], "prob-metric", { top: 278, height: 222, scope: "Exact rational histograms and TV; logarithm displays approximate. Authored finite kernels, not provider-fitted data." });
}

function drawStochasticBisimulation(slide) {
  const left = card(slide, "bisim-input", 76, 274, 326, 182, "FINITE INPUT MODEL", "fixed public store\nexplicit secret stores\nrational kernel K(M,k,Q,h)", { fill: C.white, accent: C.deepTeal, titleSize: 18, bodySize: 17, bodyY: 67, mono: true });
  const center = card(slide, "bisim-state", 477, 274, 326, 182, "FINITE SEMANTIC STATE", "control + all values\nordinals saturated at 33\nbounded complete history", { dark: true, accent: C.coral, titleSize: 18, bodySize: 17, bodyY: 67, mono: true });
  const right = card(slide, "bisim-partition", 878, 274, 326, 182, "EXACT PARTITION", "visible usage labels\nterminal / call class\nprobability per successor block", { fill: C.white, accent: C.teal, titleSize: 18, bodySize: 16.5, bodyY: 67, mono: true });
  slide.shapes.connect(left, center, { kind: "straight", fromSide: "right", toSide: "left", line: { style: "solid", fill: C.deepTeal, width: 2 }, tail: { type: "triangle", width: "sm", length: "sm" } });
  slide.shapes.connect(center, right, { kind: "straight", fromSide: "right", toSide: "left", line: { style: "solid", fill: C.teal, width: 2 }, tail: { type: "triangle", width: "sm", length: "sm" } });
  text(slide, "bisim-same", "SAME INITIAL BLOCK", 95, 498, 430, 24, { size: 14, color: C.deepTeal, bold: true });
  text(slide, "bisim-same-desc", "sufficient for equal ordered usage laws at every finite call horizon", 95, 527, 505, 52, { size: 18, color: C.ink, bold: true });
  rect(slide, "bisim-lower-divider", 625, 494, 1, 94, C.border);
  text(slide, "bisim-split", "SPLIT BLOCKS", 665, 498, 300, 24, { size: 14, color: C.rust, bold: true });
  text(slide, "bisim-split-desc", "inconclusive; not a trace-law witness", 665, 527, 480, 52, { size: 18, color: C.ink, bold: true });
  text(slide, "bisim-scope", "Success-only semantics · finite explicit stores · no cumulative cost or infinite-run claim", 116, 604, 1060, 26, { size: 15, color: C.slate, align: "center" });
}

function drawStochasticBisimMetrics(slide, evidence) {
  const b = evidence.stochasticBisim;
  drawMetricRow(slide, [
    { value: `${b.acceptedCases} / ${b.inconclusiveCases}`, label: "proved / inconclusive", detail: `${b.fixtureCount} authored finite fixtures` },
    { value: `${b.replayed}/${b.certificates}`, label: "normal certificates replayed", detail: "independent stable-partition check" },
    { value: String(b.dpComparisons), label: "exact DP cross-checks", detail: "H=1, 2, 4, 8, 16, 32 · two observers" },
    { value: String(b.histograms), label: "scenario histograms", detail: "all unit mass · all comparisons matched" },
  ], "bisim-metric", { top: 278, height: 222, dark: true, scope: `${b.producerTests} producer tests · ${b.replayerTests} replayer tests · ${b.capUnknown}/${b.fixtureCount} fresh cap probes UNKNOWN · split blocks are inconclusive.` });
}

function drawTraceEquivalence(slide) {
  card(
    slide,
    "trace-eq-left",
    82,
    250,
    535,
    132,
    "SECRET BRANCH A · RESPONSE-DEPENDENT",
    "FIRST returns output count 1. Red or blue (½ each) becomes the NEXT request.\nRed yields 1; blue yields 3 output tokens.",
    { fill: C.white, accent: C.coral, titleSize: 16.5, titleH: 38, bodyY: 59, bodySize: 15.5 },
  );
  card(
    slide,
    "trace-eq-right",
    663,
    250,
    535,
    132,
    "SECRET BRANCH B · LITERAL REQUEST",
    "FIRST also returns output count 1. NEXT(\"pink\") returns 1 or 3 output tokens, each with probability ½.",
    { fill: C.white, accent: C.teal, titleSize: 16.5, titleH: 38, bodyY: 59, bodySize: 15.5 },
  );
  text(slide, "trace-eq-bisim-label", "STRONG BISIMULATION · INCONCLUSIVE", 92, 401, 450, 22, { size: 14, color: C.rust, bold: true });
  text(slide, "trace-eq-bisim-result", "successor states split", 92, 429, 410, 32, { size: 19, color: C.ink, bold: true });
  text(slide, "trace-eq-observer-label", "ORDERED OUTPUT-COUNT WORDS · H=2 · TV=0", 671, 401, 505, 22, { size: 14, color: C.deepTeal, bold: true });
  text(slide, "trace-eq-observer-result", "(1,1): ½     (1,3): ½", 671, 429, 480, 32, { size: 19, color: C.deepTeal, bold: true, mono: true });
  rect(slide, "trace-eq-mid-rule", 82, 472, 1116, 1, C.border);

  text(slide, "trace-eq-method-head", "EXACT RATIONAL ROW-SPAN · PROVED_EQUAL", 92, 488, 420, 24, { size: 14, color: C.deepTeal, bold: true });
  text(slide, "trace-eq-equation", "μ = eA − eB     R = span{ μ A_w : w is a finite usage word }", 92, 516, 1085, 34, { size: 20, color: C.ink, bold: true, mono: true });
  text(slide, "trace-eq-method-body", "Every basis row matches stopped and still-live mass. That proves every finite word. A nonzero residual gives a finite witness; a cap returns UNKNOWN.", 92, 558, 1092, 46, { size: 16.5, color: C.slate, bold: true });
  text(slide, "trace-eq-scope", "Output-count pairs shown; contract and input usage also match · finite kernel only · no provider or total-cost claim", 95, 609, 1090, 20, { size: 13, color: C.slate, align: "center" });
}

function drawPriorArtMatrix(slide) {
  const x = [78, 306, 770];
  const widths = [210, 440, 438];
  const headers = ["FOUNDATION / SYSTEM", "ESTABLISHED SCOPE", "PROJECT BOUNDARY"];
  headers.forEach((h, i) => text(slide, `prior-header-${i}`, h, x[i], 235, widths[i], 26, { size: 14, color: C.teal, bold: true }));
  const rows = [
    ["Resource-aware IFC", "Resource observations can enter noninterference guarantees.", "A request-linked usage-event check."],
    ["RelCost / product programs", "Relational cost reasoning and self-composition.", "Resolved contracts and result-register pairing."],
    ["Expected resources / PPDL", "Probabilistic costs and multi-call LLM/tool flows.", "Usage laws under an explicit finite kernel."],
    ["QIF / trace probability", "Information-theoretic leakage and finite trace laws.", "A usage-only observer for model-call flows."],
    ["Weighted automata / APEX", "Established finite-word equivalence algorithms and tools.", "A specialized alphabet and replayable certificate."],
    ["AgentFlow / Agentproof", "Static checks for structured agent workflows.", "Different policies and observation properties."],
    ["Petri-net workflow cost", "Author-reported unary cumulative LLM cost bounds.", "Relational usage equivalence; adjacent unrefereed work."],
  ];
  rows.forEach((row, r) => {
    const y = 264 + r * 46;
    row.forEach((v, c) => text(slide, `prior-${r}-${c}`, v, x[c], y, widths[c], 39, { size: c === 0 ? 14.5 : 13.7, color: c === 0 ? C.paper : C.pale, bold: c === 0 }));
    rect(slide, `prior-row-rule-${r}`, 78, y + 40, 1130, 1, C.border);
  });
  text(slide, "prior-boundary", "Contribution framing: applied workflow software and evidence, not a new general theory.", 100, 601, 1080, 25, { size: 16, color: C.pale, bold: true, align: "center" });
}

function drawClaimScope(slide) {
  const columns = [
    ["RELATIONAL CLAIM", "Equal public-input identities\nExact modeled request match\nShared complete-outcome Ω\nProductive cycles: finite prefixes", C.deepTeal],
    ["ACCOUNTING PREMISES", "Input estimate uses byte divisor\nOutput obeys declared caps\nModel token units align\nRelevant history is included", C.coral],
    ["EXTERNAL FACTS LEFT OPEN", "Full provider serialization\nHidden account/cache/routing state\nReal tokenizer and invoices\nTermination and total cycle cost", C.rust],
  ];
  columns.forEach(([head, body, accent], i) => {
    const x = 82 + i * 382;
    text(slide, `scope-${i}-head`, head, x, 272, 330, 29, { size: 15, color: accent, bold: true });
    rect(slide, `scope-${i}-rule`, x, 313, 328, 3, accent);
    text(slide, `scope-${i}-body`, body, x, 337, 330, 178, { size: 18, color: C.ink });
    if (i < 2) rect(slide, `scope-${i}-divider`, x + 352, 270, 1, 285, C.border);
  });
  text(slide, "scope-close", "The mathematical statement is only as broad as its input model and oracle contract.", 110, 578, 1060, 36, { size: 18, color: C.ink, bold: true, align: "center" });
}

function drawArtifactReview(slide) {
  const rows = [
    ["SOURCE", "C++ compiler · graph checker · source adapters · finite channel analyzer", C.teal],
    ["INDEPENDENT CHECKS", "Source-cost auditor · graph, partition and trace-law replayers · no-merge DFS", C.coral],
    ["EVIDENCE", "Hash-bound reports · pinned runtime · offline fixtures · explicit unknowns", C.teal],
    ["ACCESS", "MIT license · citation metadata · install/build/reproduce instructions", C.coral],
  ];
  rows.forEach(([head, body, accent], i) => {
    const y = 270 + i * 75;
    text(slide, `artifact-${i}-head`, head, 92, y, 220, 25, { size: 15, color: accent, bold: true });
    text(slide, `artifact-${i}-body`, body, 315, y - 2, 870, 36, { size: 18, color: C.paper });
    rect(slide, `artifact-${i}-rule`, 92, y + 45, 1090, 1, C.darkBorder);
  });
  text(slide, "artifact-scope", "Reproducible evidence supports review; it does not replace a soundness proof or venue decision.", 108, 592, 1065, 31, { size: 16, color: C.pale, bold: true, align: "center" });
}

function drawClosingSummary(slide) {
  const items = [
    ["STATIC", "Compare modeled usage traces across secret choices.", C.deepTeal],
    ["CYCLIC", "Close productive graph cycles for every finite prefix.", C.coral],
    ["PROBABILISTIC", "Channels, bisimulation and row-span checks use finite kernels.", C.deepTeal],
  ];
  items.forEach(([tag, body, accent], i) => {
    const y = 270 + i * 91;
    label(slide, `close-tag-${i}`, tag, 100, y + 5, 190, { fill: accent, color: i === 1 ? C.ink : C.paper });
    text(slide, `close-body-${i}`, body, 330, y, 830, 43, { size: 21, color: C.ink, bold: true });
    rect(slide, `close-rule-${i}`, 100, y + 63, 1060, 1, C.border);
  });
  text(slide, "close-next", "Questions · then a local demonstration", 180, 574, 920, 38, { size: 21, color: C.deepTeal, bold: true, align: "center" });
}

function drawReferencesCompact(slide) {
  const refs = [
    "Ngo et al. · resource-aware IFC · IEEE S&P 2017 · DOI 10.1109/SP.2017.53",
    "Çiçek et al. · Relational Cost Analysis · POPL 2017 · DOI 10.1145/3009837.3009858",
    "Ngo et al. · probabilistic resources · PLDI 2018 · Mandel et al. · PPDL · ICML 2026",
    "Smith · QIF foundations · FOSSACS 2009 · Basin & Köpf · adaptive side channels · CCS 2007",
    "Tzeng · probabilistic automata equivalence · SIAM J. Comput. 1992 · DOI 10.1137/0221017",
    "Kiefer et al. · probabilistic automata equivalence · CAV 2011 · APEX · CAV 2012",
    "Kiefer et al. · rational weighted automata · LMCS 2013 · Fijalkow et al. · trace laws · LMCS 2020",
    "Larsen & Skou · probabilistic bisimulation · I&C 1991 · Kamaleson et al. · finite-horizon refinement · SPIN 2016",
    "Weiss et al. · USENIX Security 2024 · Agentproof / AgentFlow · 2026 preprints",
    "Dickerson · LLM workflow Petri-net cost note · May 2026 · author-reported, unrefereed",
  ];
  refs.forEach((r, i) => {
    const y = 242 + i * 36;
    text(slide, `refs-current-${i}`, `[${i + 1}]  ${r}`, 82, y, 1110, 29, { size: 13.3, color: C.ink });
    if (i < refs.length - 1) rect(slide, `refs-current-rule-${i}`, 82, y + 31, 1110, 1, C.border);
  });
  text(slide, "refs-links", "Full citations, stable links and prior-art boundaries: submission/research/current_review_sources.md", 86, 608, 1100, 20, { size: 13.5, color: C.deepTeal, bold: true });
}

function drawLiveDemo(slide, spec) {
  text(slide, "demo-eyebrow", "FINAL SLIDE  ·  LOOPBACK ONLY", 92, 252, 530, 23, { size: 14, color: C.teal, bold: true });
  const link = text(slide, "demo-url", spec.url, 90, 292, 1090, 62, { size: 38, color: C.coral, bold: true, mono: true });
  link.text.get(spec.url).link = { uri: spec.url, isExternal: true };
  rect(slide, "demo-command-rule", 92, 384, 1095, 1, C.darkBorder);
  text(slide, "demo-launch-label", "FROM REPOSITORY ROOT", 94, 410, 300, 22, { size: 13.5, color: C.pale, bold: true });
  text(slide, "demo-launch", spec.launchCommand, 94, 439, 650, 38, { size: 20, color: C.paper, mono: true, bold: true });
  const steps = spec.steps || [];
  steps.forEach((s, i) => {
    const y = 514 + i * 38;
    text(slide, `demo-step-${i}-number`, String(i + 1).padStart(2, "0"), 95, y, 48, 26, { size: 15, color: i === 1 ? C.coral : C.teal, mono: true, bold: true });
    text(slide, `demo-step-${i}-text`, s, 158, y, 810, 27, { size: 17, color: C.paper });
  });
  text(slide, "demo-footnote", "Offline authored kernels · no provider calls · URL works while the local server is running", 96, 621, 1090, 22, { size: 13.5, color: C.pale, align: "center" });
}

function addVisual(pres, slide, spec, index) {
  switch (spec.kind) {
    case "branch": drawBranch(slide); break;
    case "value_flow": drawValueFlow(slide); break;
    case "observation": drawObservation(slide, spec); break;
    case "two_guarantees": drawTwoGuarantees(slide); break;
    case "counterexample": drawCounterexample(slide, deck.evidence.counterexample); break;
    case "cap_actual": drawCapActual(slide, deck.evidence.counterexample); break;
    case "coupling": drawCoupling(slide); break;
    case "signature": drawSignature(slide); break;
    case "accept_reject": drawAcceptReject(slide); break;
    case "chained_calls": drawChained(slide); break;
    case "pipeline": drawPipeline(slide); break;
    case "diagnostic": drawDiagnostic(slide, deck.evidence); break;
    case "protocol": drawProtocol(slide); break;
    case "metrics": drawMetrics(slide, deck.evidence); break;
    case "trace": drawTrace(slide, deck.evidence.witness); break;
    case "literature": drawLiterature(slide); break;
    case "limits": drawLimits(slide); break;
    case "appendix": drawAppendix(slide, spec, index); break;
    case "qa": drawQA(slide, spec); break;
    case "related_systems": drawRelatedSystems(slide); break;
    case "references": drawReferences(slide); break;
    case "graph_architecture": drawGraphArchitecture(slide); break;
    case "graph_counterexample": drawGraphCounterexample(slide); break;
    case "graph_observation": drawGraphObservation(slide); break;
    case "graph_product": drawGraphProduct(slide); break;
    case "graph_rules": drawGraphRules(slide); break;
    case "graph_cycle": drawGraphCycle(slide, deck.evidence); break;
    case "graph_replay": drawGraphReplay(slide, deck.evidence); break;
    case "stale_register": drawStaleRegister(slide, deck.evidence); break;
    case "graph_metrics": drawGraphMetrics(slide, deck.evidence); break;
    case "stress_metrics": drawStressMetrics(slide, deck.evidence); break;
    case "graph_adversarial": drawGraphAdversarial(slide, deck.evidence); break;
    case "contribution_boundary": drawContributionBoundary(slide); break;
    case "graph_limits": drawGraphLimits(slide); break;
    case "graph_references": drawGraphReferences(slide); break;
    case "usage_laws": drawUsageLaws(slide); break;
    case "observer_split": drawObserverSplit(slide); break;
    case "three_questions": drawThreeQuestions(slide); break;
    case "architecture_all": drawArchitectureAll(slide); break;
    case "bounded_rule_metrics": drawBoundedRuleMetrics(slide, deck.evidence); break;
    case "source_bridge_metrics": drawSourceBridgeMetrics(slide, deck.evidence); break;
    case "langgraph_source_metrics": drawLangGraphSourceMetrics(slide, deck.evidence); break;
    case "langgraph_runtime_metrics": drawLangGraphRuntimeMetrics(slide, deck.evidence); break;
    case "probability_model": drawProbabilityModel(slide); break;
    case "probability_dp": drawProbabilityDP(slide); break;
    case "probability_metrics": drawProbabilityMetrics(slide, deck.evidence); break;
    case "stochastic_bisimulation": drawStochasticBisimulation(slide); break;
    case "stochastic_bisim_metrics": drawStochasticBisimMetrics(slide, deck.evidence); break;
    case "trace_equivalence": drawTraceEquivalence(slide); break;
    case "prior_art_matrix": drawPriorArtMatrix(slide); break;
    case "claim_scope": drawClaimScope(slide); break;
    case "artifact_review": drawArtifactReview(slide); break;
    case "closing_summary": drawClosingSummary(slide); break;
    case "references_compact": drawReferencesCompact(slide); break;
    case "live_demo": drawLiveDemo(slide, spec); break;
    default: throw new Error(`Unknown slide kind: ${spec.kind}`);
  }
}

async function loadFinalEvidence() {
  const ordinalReportPath = path.join(ROOT_DIR, "bench/results/sourced.json");
  const requestReportPath = path.join(ROOT_DIR, "bench/results/sourced_request_sensitive.json");
  const manifestPath = path.join(ROOT_DIR, "bench/sourced/manifest.json");
  const compilerPath = path.join(ROOT_DIR, "orchc");
  const sourcePath = path.join(ROOT_DIR, "examples/research/rejected/equal_bounds_different_inputs.orch");
  const [ordinalText, requestText, manifestBytes, compilerBytes, sourceText] = await Promise.all([
    fs.readFile(ordinalReportPath, "utf8"),
    fs.readFile(requestReportPath, "utf8"),
    fs.readFile(manifestPath),
    fs.readFile(compilerPath),
    fs.readFile(sourcePath, "utf8"),
  ]);
  const ordinalReport = JSON.parse(ordinalText);
  const requestReport = JSON.parse(requestText);
  const compilerSha = createHash("sha256").update(compilerBytes).digest("hex");
  const manifestSha = createHash("sha256").update(manifestBytes).digest("hex");
  const ordinalReportSha = createHash("sha256").update(ordinalText).digest("hex");
  const requestReportSha = createHash("sha256").update(requestText).digest("hex");
  const reports = [
    { report: ordinalReport, mode: "ordinal" },
    { report: requestReport, mode: "request-sensitive" },
  ];
  const allowStalePreview = PREVIEW_DIR !== undefined && process.env.PRESENTATION_PREVIEW_ALLOW_STALE_EVIDENCE === "1";
  for (const item of reports) {
    const report = item.report;
    if (report.environment?.compiler_sha256 !== compilerSha && !allowStalePreview) {
      throw new Error(item.mode + " compiler hash does not match sourced report: " + compilerSha);
    }
    if (report.environment?.manifest_sha256 !== manifestSha) {
      throw new Error(item.mode + " manifest hash does not match sourced report: " + manifestSha);
    }
    if (report.failures?.length ||
        report.experiment !== "15 source-derived partial bounded patterns, three authored variants each" ||
        report.oracle_mode !== item.mode) {
      throw new Error(item.mode + " report failed validation or used an unexpected experiment definition.");
    }
  }
  if (allowStalePreview && reports.some(({ report }) => report.environment?.compiler_sha256 !== compilerSha)) {
    console.warn("Layout preview only: saved reports are stale for the current compiler; do not use this build as final evidence.");
  }

  const totals = ordinalReport.totals || {};
  const requestTotals = requestReport.totals || {};
  const required = {
    base_executions: 1500,
    bound_violations: 0,
    source_reports_checked: 30,
    balanced_comparisons: 2250,
    balanced_mismatches: 0,
    unbalanced_comparisons: 2250,
    unbalanced_mismatches: 2250,
    balanced_accepted: 15,
    baseline_balanced_accepted: 8,
    newly_accepted: 7,
    mutations_rejected: 15,
  };
  for (const [key, value] of Object.entries(required)) {
    if (totals[key] !== value) throw new Error("Unexpected ordinal evidence total " + key + ": " + totals[key]);
    if (requestTotals[key] !== value) throw new Error("Unexpected request-sensitive evidence total " + key + ": " + requestTotals[key]);
  }
  for (const key of new Set([...Object.keys(totals), ...Object.keys(requestTotals)])) {
    if (totals[key] !== requestTotals[key]) throw new Error("Oracle reports do not share the same total for " + key);
  }
  const ordinalIds = ordinalReport.patterns.map((item) => item.id).join("\n");
  const requestIds = requestReport.patterns.map((item) => item.id).join("\n");
  if (ordinalReport.patterns.length !== 15 || ordinalIds !== requestIds) {
    throw new Error("Oracle reports do not use the same 15 source-pattern projections.");
  }

  const extractWitness = (report) => {
    const row = report.patterns.find((item) => item.id === "pdl_chaining");
    const witness = row?.unbalanced?.first_witness;
    if (!witness) throw new Error("The " + report.oracle_mode + " PDL chaining case has no witness.");
    const [modelKey, falseVector] = Object.entries(witness.false_billing || {})[0] || [];
    const trueVector = modelKey ? witness.true_billing?.[modelKey] : null;
    if (!modelKey || !Array.isArray(falseVector) || !Array.isArray(trueVector)) {
      throw new Error("The " + report.oracle_mode + " paired witness has no usage vectors.");
    }
    return { witness, modelKey, falseVector, trueVector };
  };
  const ordinal = extractWitness(ordinalReport);
  const requestSensitive = extractWitness(requestReport);
  const witness = ordinal.witness;
  const decodeContract = (key) => {
    const provider = key.match(/^p(\d+)x([0-9a-f]+)_/i);
    const model = key.match(/_m(\d+)x([0-9a-f]+)_cap(\d+)/i);
    if (!provider || !model) return key;
    const decode = (hex) => Buffer.from(hex, "hex").toString("utf8");
    return decode(provider[2]) + " / " + decode(model[2]) + " / cap " + model[3];
  };
  const toObservation = ([calls, input, output]) => ({ calls, input, output });
  const modePair = (item) => ({
    false: toObservation(item.falseVector),
    true: toObservation(item.trueVector),
    modelLabel: decodeContract(item.modelKey),
  });

  const compilerRun = spawnSync(compilerPath, ["check", "examples/research/rejected/equal_bounds_different_inputs.orch"], {
    cwd: ROOT_DIR,
    encoding: "utf8",
  });
  const diagnostic = (compilerRun.stderr || "") + (compilerRun.stdout || "");
  if (compilerRun.status === 0 || !diagnostic.includes("[E236]") ||
      !diagnostic.includes("outer(left_source#") || !diagnostic.includes("outer(right_source#")) {
    throw new Error("Could not capture expected final E236 diagnostic: " + diagnostic);
  }
  const sourceLines = sourceText.split(/\r?\n/);
  const ifLine = sourceLines.findIndex((line) => line.trimStart().startsWith("if choose"));
  if (ifLine < 0) throw new Error("Could not locate the equal-cap branch in its source example.");

  deck.evidence.diagnosticSourceSnippet = sourceLines.slice(ifLine, ifLine + 5).join("\n");
  deck.evidence.diagnosticOutput = diagnostic.trim();
  deck.evidence.witness = {
    ordinal: modePair(ordinal),
    requestSensitive: modePair(requestSensitive),
  };
  deck.evidence.metrics = [
    { label: "Balanced patterns", value: "15 / 15", detail: "both modes · baseline 8 / 15" },
    { label: "Balanced pairs", value: "0 / 2,250", detail: "mismatches in each mode" },
    { label: "Mutations rejected", value: "15 / 15", detail: "2,250 paired witnesses per mode" },
    { label: "Bound violations", value: "0 / 1,500", detail: "across base executions per mode" },
  ];
  deck.evidence.sourceReportsChecked = totals.source_reports_checked;
  deck.evidence.compilerShaShort = compilerSha.slice(0, 12);
  deck.evidence.baselineCommitShort = ordinalReport.environment.baseline_commit.slice(0, 12);

  if (!GRAPH_CANDIDATE) {
    const appendix = deck.slides.find((item) => item.number === 22);
    appendix.details[0] = "compiler SHA-256 " + compilerSha.slice(0, 12) +
      " · baseline " + ordinalReport.environment.baseline_commit.slice(0, 8);
    appendix.details[1] = "make check · 111 C++ regressions · 19 auditor tests";
    appendix.details[2] = "15 examples · 45 variants · 1,500 base runs · 30 audited reports";
    appendix.details[3] = "25 seeds × lengths 0/37/160 × 2 public flags × 2 secrets";
    appendix.details[4] = "Ordinal and request-sensitive modes; same grids, not summed.";
    appendix.notes += "\n\nSaved evidence IDs: compiler SHA-256 " + compilerSha +
      "; manifest SHA-256 " + manifestSha +
      "; baseline commit " + ordinalReport.environment.baseline_commit +
      ". Report SHA-256: sourced.json " + ordinalReportSha +
      "; sourced_request_sensitive.json " + requestReportSha +
      ". Reports: sourced.json (ordinal) and sourced_request_sensitive.json (request-sensitive)." +
      " Each mode repeats the same grid; counts are not added as independent patterns.";

    const caseSlide = deck.slides.find((item) => item.number === 16);
    caseSlide.subtitle = "PDL-derived mutation · seed " + witness.seed +
      " · query=" + witness.query_tokens + " · public tool=" + witness.use_tool;
  }
}

async function loadGraphCandidateEvidence() {
  const paths = {
    graphs: path.join(ROOT_DIR, "bench/results/graphs.json"),
    adversarial: path.join(ROOT_DIR, "bench/results/graph_adversarial.json"),
    stress: path.join(ROOT_DIR, "bench/results/relational_stress.json"),
    producer: path.join(ROOT_DIR, "audit/orchgraph.py"),
    replayer: path.join(ROOT_DIR, "audit/replay_graph_certificate.py"),
    compiler: path.join(ROOT_DIR, "orchc"),
  };
  const [graphsText, adversarialText, stressText, producerBytes, replayerBytes, compilerBytes] = await Promise.all([
    fs.readFile(paths.graphs, "utf8"), fs.readFile(paths.adversarial, "utf8"),
    fs.readFile(paths.stress, "utf8"), fs.readFile(paths.producer),
    fs.readFile(paths.replayer), fs.readFile(paths.compiler),
  ]);
  const graphs = JSON.parse(graphsText);
  const adversarial = JSON.parse(adversarialText);
  const stress = JSON.parse(stressText);
  const producerSha = createHash("sha256").update(producerBytes).digest("hex");
  const replayerSha = createHash("sha256").update(replayerBytes).digest("hex");
  const compilerSha = createHash("sha256").update(compilerBytes).digest("hex");
  const g = graphs.totals || {};
  const s = stress.checks || {};
  const a = adversarial.counts || {};
  if (graphs.environment?.checker_sha256 !== producerSha) throw new Error("Graph fixture results do not match the current producer hash.");
  if (adversarial.producer?.sha256 !== producerSha) throw new Error("Adversarial probe does not match the current producer hash.");
  if (stress.study?.compiler_sha256 !== compilerSha) throw new Error("Relational stress report does not match the current C++ compiler hash.");
  if (g.accepted !== 6 || g.rejected !== 8 || g.invalid !== 3 || g.replayed_certificates !== 6 ||
      g.accepted_reference_runs !== 1400 || g.accepted_secret_comparisons !== 800 ||
      g.accepted_mismatches !== 0 || g.accepted_call_accounting_checks !== 28580 ||
      g.rejections_with_finite_witness !== 8) {
    throw new Error("Graph fixture results do not match the reviewed 17-case evidence totals.");
  }
  if (s.accepted_reference_runs !== 24192 || s.accepted_secret_assignment_comparisons !== 13824 ||
      s.accepted_request_trace_mismatches !== 0 || s.accepted_usage_trace_mismatches !== 0 ||
      s.accepted_per_call_input_accounting_checks !== 66240 ||
      s.rejected_mutation_request_trace_witness_cases !== 117 || s.rejected_mutation_unknown_no_witness_cases !== 3) {
    throw new Error("The full-text relational stress report changed from the reviewed totals.");
  }
  if (a.generated !== 3000 || a.paired_store_comparisons !== 11696 || a.accepted_mismatches !== 0) {
    throw new Error("The supplementary small-graph property probe changed from the reviewed totals.");
  }
  const cyclicFixture = graphs.fixtures.find((item) => item.path.endsWith("/unbounded_productive_cycle.json"));
  const staleFixture = graphs.fixtures.find((item) => item.path.endsWith("/overwritten_result_relation.json"));
  if (!cyclicFixture || !staleFixture?.first_witness) throw new Error("Graph cycle or overwritten-register fixture is missing.");
  deck.evidence.graph = {
    fixtureCount: g.accepted + g.rejected + g.invalid,
    acceptedFixtures: g.accepted,
    rejectedFixtures: g.rejected,
    invalidFixtures: g.invalid,
    replayedCertificates: g.replayed_certificates,
    acceptedCertificates: g.accepted,
    acceptedRuns: g.accepted_reference_runs,
    acceptedComparisons: g.accepted_secret_comparisons,
    accountingChecks: g.accepted_call_accounting_checks,
    finiteWitnessRejects: g.rejections_with_finite_witness,
    productiveCalls: cyclicFixture.calls,
    truncatedCycleRuns: cyclicFixture.truncated_runs,
    producerSha,
    replayerSha,
    reportSha: createHash("sha256").update(graphsText).digest("hex"),
    staleWitness: {
      seed: staleFixture.first_witness.seed,
      eventIndex: staleFixture.first_witness.first_differing_event_index,
      leftInput: staleFixture.first_witness.left_event.input_tokens,
      rightInput: staleFixture.first_witness.right_event.input_tokens,
    },
  };
  deck.evidence.stress = {
    caseCount: stress.study.generated_case_count,
    acceptedCases: stress.study.accepted_case_count,
    rejectedCases: stress.study.expected_rejection_case_count,
    referenceRuns: s.accepted_reference_runs,
    pairComparisons: s.accepted_secret_assignment_comparisons,
    accountingChecks: s.accepted_per_call_input_accounting_checks,
    witnessCases: s.rejected_mutation_usage_trace_witness_cases,
    unknownCases: s.rejected_mutation_unknown_no_witness_cases,
    compilerSha,
    generatorSha: stress.study.generator_sha256,
    reportSha: createHash("sha256").update(stressText).digest("hex"),
  };
  deck.evidence.graphAdversarial = {
    generated: a.generated,
    accepted: a.checker_accepted,
    comparisons: a.paired_store_comparisons,
    distinctSecretComparisons: a.distinct_secret_store_comparisons,
    mismatches: a.accepted_mismatches,
    maxCalls: adversarial.oracle_probe.max_calls_per_run,
    sameProducerReference: adversarial.producer.source.includes("same audit/orchgraph.py"),
  };
  if (!deck.evidence.graphAdversarial.sameProducerReference) throw new Error("Small-graph probe caveat was not preserved.");
}

async function loadCurrentEvidence() {
  const manifestPath = path.join(ROOT_DIR, "audit/final/manifest.json");
  const manifestBytes = await fs.readFile(manifestPath);
  const manifest = JSON.parse(manifestBytes.toString("utf8"));
  const compilerBytes = await fs.readFile(path.join(ROOT_DIR, "orchc"));
  const compilerSha = createHash("sha256").update(compilerBytes).digest("hex");
  if (manifest.quick !== false || manifest.sanitizer_requested !== true || manifest.packaging_requested !== true || manifest.status !== "passed") {
    throw new Error("The final reproduction manifest is not a complete sanitized/package validation run.");
  }
  if (manifest.compiler_sha256 !== compilerSha) throw new Error("The final manifest compiler hash does not match the current binary.");
  if (!Array.isArray(manifest.stages) || manifest.stages.some((stage) => {
    const expectedCode = stage.expected_exit_code ?? (stage.expected ? 1 : undefined);
    if (expectedCode === undefined || stage.exit_code !== expectedCode) return true;
    return typeof stage.expected === "string" && !(stage.diagnostics || []).includes(stage.expected);
  })) {
    throw new Error("A final reproduction stage failed its expected exit code or diagnostic.");
  }

  const reportPaths = [
    "bench/results/graphs.json",
    "bench/results/graph_adversarial.json",
    "bench/results/relational_stress.json",
    "bench/results/sourced.json",
    "bench/results/sourced_request_sensitive.json",
    "bench/results/source_graphs/evaluation.json",
    "bench/results/langgraph_source_study.json",
    "bench/results/langgraph_integration.json",
    "bench/results/probabilistic_channels.json",
    "bench/results/probabilistic_channels/same_mean_distinct_laws.h1.aggregate.json",
    "bench/results/probabilistic_channels/aggregate_hides_order.h2.aggregate.json",
    "bench/results/probabilistic_channels/aggregate_hides_order.h2.trace.json",
    "bench/results/stochastic_bisimulation.json",
    "bench/results/trace_equivalence.json",
  ];
  const reportBytes = new Map();
  for (const relativePath of reportPaths) {
    const bytes = await fs.readFile(path.join(ROOT_DIR, relativePath));
    const actualSha = createHash("sha256").update(bytes).digest("hex");
    const boundSha = manifest.results_sha256?.[relativePath];
    if (!boundSha) throw new Error("The final manifest does not bind " + relativePath + ".");
    if (boundSha !== actualSha) throw new Error("The final manifest hash does not match " + relativePath + ".");
    reportBytes.set(relativePath, bytes);
  }

  const shaFile = async (relativePath) => createHash("sha256").update(await fs.readFile(path.join(ROOT_DIR, relativePath))).digest("hex");
  const parse = (relativePath) => JSON.parse(reportBytes.get(relativePath).toString("utf8"));
  const sourceGraph = parse("bench/results/source_graphs/evaluation.json");
  const langStudy = parse("bench/results/langgraph_source_study.json");
  const langRuntime = parse("bench/results/langgraph_integration.json");
  const channel = parse("bench/results/probabilistic_channels.json");
  const graphReport = parse("bench/results/graphs.json");
  const sourceStress = parse("bench/results/relational_stress.json");
  const stochastic = parse("bench/results/stochastic_bisimulation.json");
  const traceEquivalence = parse("bench/results/trace_equivalence.json");

  const graphSha = await shaFile("audit/orchgraph.py");
  const replayerSha = await shaFile("audit/replay_graph_certificate.py");
  const sourceBridgeSha = await shaFile("audit/source_to_graph.py");
  const langBackendSha = await shaFile("integrations/langgraph/backend.py");
  const channelProducerSha = await shaFile("audit/probabilistic_channels.py");
  const channelReferenceSha = await shaFile("audit/probabilistic_reference.py");
  const channelDriverSha = await shaFile("audit/evaluate_probabilistic_channels.py");
  const stochasticProducerSha = await shaFile("audit/stochastic_bisimulation.py");
  const stochasticReplayerSha = await shaFile("audit/replay_stochastic_certificate.py");
  const stochasticDriverSha = await shaFile("audit/evaluate_stochastic_bisimulation.py");
  const stochasticDpSha = channelProducerSha;
  const traceProducerSha = await shaFile("audit/trace_equivalence.py");
  const traceReplayerSha = await shaFile("audit/replay_trace_equivalence.py");
  const traceDriverSha = await shaFile("audit/evaluate_trace_equivalence.py");
  const traceClosureReplayerSha = stochasticReplayerSha;
  const traceFiniteDpSha = channelProducerSha;
  const traceBisimulationSha = stochasticProducerSha;
  if (sourceGraph.environment?.compiler_sha256 !== compilerSha || sourceStress.study?.compiler_sha256 !== compilerSha) {
    throw new Error("Source bridge or full-text stress results are stale for the current compiler.");
  }
  if (sourceGraph.environment?.graph_checker_sha256 !== graphSha || sourceGraph.environment?.replayer_sha256 !== replayerSha || sourceGraph.environment?.adapter_sha256 !== sourceBridgeSha) {
    throw new Error("Source bridge results do not match the current graph/replay/adapter sources.");
  }
  if (graphReport.environment?.checker_sha256 !== graphSha || graphReport.environment?.replayer_sha256 !== replayerSha) {
    throw new Error("Cyclic graph fixture results do not match current producer and replayer sources.");
  }
  if (langRuntime.environment?.backend_sha256 !== langBackendSha || langRuntime.environment?.reference_producer_sha256 !== graphSha ||
      langRuntime.environment?.independent_replayer_sha256 !== replayerSha || langRuntime.environment?.source_bridge_sha256 !== sourceBridgeSha) {
    throw new Error("LangGraph integration results do not match the current backend, graph, replay, or bridge source.");
  }
  if (langRuntime.environment?.source_graph_evaluation_sha256 !== createHash("sha256").update(reportBytes.get("bench/results/source_graphs/evaluation.json")).digest("hex")) {
    throw new Error("LangGraph integration did not use the bound source-graph evaluation report.");
  }
  if (channel.producer_sha256 !== channelProducerSha || channel.reference_sha256 !== channelReferenceSha || channel.driver_sha256 !== channelDriverSha ||
      channel.failures?.length || channel.status !== "passed") {
    throw new Error("Finite channel results are stale, incomplete, or contain failures.");
  }

  const stochasticSummary = stochastic.summary || {};
  const stochasticSourceHashes = stochastic.source_hashes || {};
  const stochasticFixtures = Array.isArray(stochastic.fixtures) ? stochastic.fixtures : [];
  const stochasticTests = (relativePath) => fs.readFile(path.join(ROOT_DIR, relativePath), "utf8")
    .then((source) => (source.match(/^\s*def test_/gm) || []).length);
  const [stochasticProducerTests, stochasticReplayerTests] = await Promise.all([
    stochasticTests("audit/test_stochastic_bisimulation.py"),
    stochasticTests("audit/test_stochastic_replay.py"),
  ]);
  if (stochastic.status !== "passed" || stochastic.failures?.length ||
      stochasticSourceHashes.producer_sha256 !== stochasticProducerSha ||
      stochasticSourceHashes.replayer_sha256 !== stochasticReplayerSha ||
      stochasticSourceHashes.driver_sha256 !== stochasticDriverSha ||
      stochasticSourceHashes.finite_dp_sha256 !== stochasticDpSha ||
      stochasticSourceHashes.scenario_definition_sha256 !== channelDriverSha ||
      stochasticSummary.fixture_count !== 11 ||
      stochasticSummary.producer_status_counts?.proved_equal !== 5 ||
      stochasticSummary.producer_status_counts?.inconclusive !== 6 ||
      stochasticSummary.producer_status_counts?.unknown !== 0 ||
      stochasticSummary.normal_certificates_independently_verified !== 11 ||
      stochasticSummary.proved_equal_dp_comparisons !== 60 ||
      stochasticSummary.dp_scenario_histograms_compared !== 120 ||
      stochasticSummary.fresh_state_cap_unknown_probes !== 11 ||
      JSON.stringify(stochasticSummary.horizons) !== JSON.stringify([1, 2, 4, 8, 16, 32]) ||
      JSON.stringify(stochasticSummary.observers) !== JSON.stringify(["aggregate", "trace"]) ||
      stochasticFixtures.length !== 11 || stochasticProducerTests !== 17 || stochasticReplayerTests !== 12) {
    throw new Error("All-horizon stochastic-bisimulation evidence is stale or differs from the reviewed report.");
  }
  const verifyStochasticArtifact = async (artifact, label) => {
    if (!artifact?.path || !artifact?.sha256 || path.isAbsolute(artifact.path) || artifact.path.split(/[\\/]/).includes("..")) {
      throw new Error(`Malformed ${label} artifact reference in the stochastic-bisimulation report.`);
    }
    const actual = createHash("sha256").update(await fs.readFile(path.join(ROOT_DIR, artifact.path))).digest("hex");
    if (actual !== artifact.sha256) throw new Error(`${label} does not match its hash in the stochastic-bisimulation report.`);
  };
  for (const fixture of stochasticFixtures) {
    const attestation = fixture.independent_attestation || {};
    const capCertificate = fixture.state_cap_unknown_probe?.certificate || {};
    const capAttestation = fixture.state_cap_unknown_probe?.fresh_independent_attestation || {};
    if (attestation.status !== "verified" || attestation.certificate_status !== fixture.producer_status ||
        (fixture.producer_status === "proved_equal") !== (attestation.equal_laws_claim === true) ||
        capCertificate.status !== "unknown" || capAttestation.status !== "unknown" || capAttestation.equal_laws_claim !== false) {
      throw new Error("A stochastic-bisimulation fixture lacks its expected replay or fresh UNKNOWN attestation.");
    }
    await Promise.all([
      verifyStochasticArtifact(fixture.graph, `${fixture.name} graph`),
      verifyStochasticArtifact(fixture.kernel, `${fixture.name} kernel`),
      verifyStochasticArtifact(fixture.inputs_artifact, `${fixture.name} inputs`),
      verifyStochasticArtifact(fixture.certificate, `${fixture.name} certificate`),
      verifyStochasticArtifact(attestation, `${fixture.name} independent attestation`),
      verifyStochasticArtifact(fixture.state_cap_unknown_probe.certificate, `${fixture.name} cap UNKNOWN certificate`),
      verifyStochasticArtifact(fixture.state_cap_unknown_probe.fresh_independent_attestation, `${fixture.name} cap UNKNOWN attestation`),
      ...(fixture.finite_dp_cross_check ? [verifyStochasticArtifact(fixture.finite_dp_cross_check, `${fixture.name} finite-DP cross-check`)] : []),
    ]);
  }

  // The exact trace-law report is separately manifest-bound and its own
  // artifact references are content-addressed. A producer status alone is
  // never treated as evidence of a proof or counterexample.
  const traceSummary = traceEquivalence.summary || {};
  const traceHashes = traceEquivalence.source_hashes || {};
  const traceFixtures = Array.isArray(traceEquivalence.fixtures) ? traceEquivalence.fixtures : [];
  if (traceEquivalence.status !== "passed" || traceEquivalence.failures?.length ||
      traceHashes.trace_equivalence_producer !== traceProducerSha ||
      traceHashes.independent_trace_replayer !== traceReplayerSha ||
      traceHashes.evaluation_driver !== traceDriverSha ||
      traceHashes.independent_closure_replayer !== traceClosureReplayerSha ||
      traceHashes.finite_channel_dp !== traceFiniteDpSha ||
      traceHashes.stochastic_bisimulation_comparison !== traceBisimulationSha ||
      traceSummary.fixture_count !== traceFixtures.length || traceFixtures.length !== 12) {
    throw new Error("Exact trace-equivalence evidence is stale, incomplete, or differs from the reviewed report.");
  }
  const safeArtifactPath = (relativePath, label) => {
    if (typeof relativePath !== "string" || !relativePath || path.isAbsolute(relativePath) ||
        relativePath.split(/[\\/]/).includes("..")) {
      throw new Error(`Malformed ${label} artifact path in the exact trace-equivalence report.`);
    }
    return path.join(ROOT_DIR, relativePath);
  };
  const verifyTraceArtifact = async (artifact, label) => {
    if (!artifact || typeof artifact.path !== "string" || typeof artifact.sha256 !== "string") {
      throw new Error(`Missing ${label} artifact reference in the exact trace-equivalence report.`);
    }
    const bytes = await fs.readFile(safeArtifactPath(artifact.path, label));
    const actual = createHash("sha256").update(bytes).digest("hex");
    if (actual !== artifact.sha256) throw new Error(`${label} does not match its report SHA-256.`);
    return JSON.parse(bytes.toString("utf8"));
  };
  const traceNames = new Set();
  let traceProofs = 0;
  let traceWitnesses = 0;
  let traceEqualDpChecks = 0;
  let traceEqualHistograms = 0;
  let traceWitnessDpChecks = 0;
  let traceDistinguishingDpChecks = 0;
  let traceUnknownProbes = 0;
  let traceTamperRejections = 0;
  for (const fixture of traceFixtures) {
    if (!fixture.name || traceNames.has(fixture.name)) throw new Error("Duplicate or unnamed exact trace-equivalence fixture.");
    traceNames.add(fixture.name);
    const attestation = fixture.independent_attestation || {};
    const cap = fixture.fresh_unknown_probe || {};
    const capAttestation = cap.independent_attestation || {};
    const tamper = fixture.tamper_probe || {};
    const tamperAttestation = tamper.independent_attestation || {};
    const status = fixture.producer_status;
    if (!(["proved_equal", "unequal"].includes(status)) || attestation.status !== "verified" ||
        attestation.decision !== status || cap.producer_status !== "unknown" ||
        capAttestation.status !== "unknown" || capAttestation.decision !== null ||
        tamperAttestation.status !== "rejected") {
      throw new Error(`Exact trace-equivalence fixture ${fixture.name} lacks its required replay, UNKNOWN, or tamper result.`);
    }
    if (status === "proved_equal") traceProofs += 1;
    else traceWitnesses += 1;
    traceUnknownProbes += 1;
    traceTamperRejections += 1;
    const [certificate, replay, capCertificate, capReplay, tamperedCertificate, tamperReplay] = await Promise.all([
      verifyTraceArtifact(fixture.trace_certificate, `${fixture.name} trace certificate`),
      verifyTraceArtifact(attestation, `${fixture.name} independent attestation`),
      verifyTraceArtifact(cap.certificate, `${fixture.name} cap UNKNOWN certificate`),
      verifyTraceArtifact(capAttestation, `${fixture.name} cap UNKNOWN attestation`),
      verifyTraceArtifact(tamper, `${fixture.name} tampered certificate`),
      verifyTraceArtifact(tamperAttestation, `${fixture.name} tamper rejection attestation`),
      verifyTraceArtifact(fixture.graph, `${fixture.name} graph`),
      verifyTraceArtifact(fixture.kernel, `${fixture.name} kernel`),
    ]);
    if (certificate.status !== status || replay.status !== "verified" || replay.decision !== status ||
        capCertificate.status !== "unknown" || capReplay.status !== "unknown" || capReplay.decision !== null ||
        tamperReplay.status !== "rejected" || !tamperedCertificate.result) {
      throw new Error(`Exact trace-equivalence artifacts disagree with the report for ${fixture.name}.`);
    }
    const pairs = certificate.result?.pairs;
    const certificatePairStatus = status === "proved_equal" ? "equal" : "unequal";
    if (!Array.isArray(pairs) || !pairs.length || pairs.some((pair) => pair.status !== certificatePairStatus)) {
      throw new Error(`Exact trace-equivalence certificate has no complete pair result for ${fixture.name}.`);
    }
    if (status === "proved_equal" && pairs.some((pair) => pair.closed_under_label_matrices !== true ||
        pair.initial_difference_in_span !== true || pair.stop_outputs_zero !== true || pair.nonterminal_outputs_zero !== true)) {
      throw new Error(`Equal fixture ${fixture.name} lacks a complete closed exact span proof.`);
    }
    if (status === "unequal" && pairs.some((pair) => {
      const witness = pair.counterexample;
      return !witness || !Array.isArray(witness.word) || !["stop", "nonterminal"].includes(witness.end_kind) ||
        witness.left_probability === witness.right_probability;
    })) {
      throw new Error(`Unequal fixture ${fixture.name} lacks a finite distinguishing usage word.`);
    }
    if (fixture.finite_dp_cross_check) {
      const finiteDp = await verifyTraceArtifact(fixture.finite_dp_cross_check, `${fixture.name} finite-DP cross-check`);
      if (status === "proved_equal") {
        if (!Array.isArray(finiteDp.checks)) throw new Error(`Finite-DP proof cross-check for ${fixture.name} has no checks.`);
        traceEqualDpChecks += finiteDp.checks.length;
        traceEqualHistograms += finiteDp.checks.reduce((sum, check) => sum + (check.scenario_histogram_sha256?.length || 0), 0);
        if (finiteDp.checks.some((check) => check.equal_exact_histograms !== true)) {
          throw new Error(`Finite-DP cross-check disagrees with the proved-equal result for ${fixture.name}.`);
        }
      } else {
        if (finiteDp.finite_dp_histograms_differ !== true || finiteDp.exact_witness_probabilities_match !== true) {
          throw new Error(`Finite-DP witness check for ${fixture.name} does not validate the reported finite distinction.`);
        }
        traceWitnessDpChecks += 1;
        traceDistinguishingDpChecks += 1;
      }
    }
  }
  const gapFixture = traceFixtures.find((fixture) => fixture.name === "trace_equal_not_bisimilar");
  if (!gapFixture || gapFixture.producer_status !== "proved_equal" ||
      gapFixture.independent_attestation?.status !== "verified" ||
      gapFixture.bisimulation_comparison?.status !== "inconclusive" ||
      traceSummary.equal_not_bisimilar_fixture?.trace_equivalence_status !== "proved_equal" ||
      traceSummary.equal_not_bisimilar_fixture?.strong_bisimulation_status !== "inconclusive" ||
      traceSummary.equal_not_bisimilar_fixture?.independent_replay_status !== "verified" ||
      traceProofs !== traceSummary.producer_decision_counts?.proved_equal ||
      traceWitnesses !== traceSummary.producer_decision_counts?.unequal ||
      traceProofs !== traceSummary.independently_replayed_proofs ||
      traceWitnesses !== traceSummary.independently_replayed_finite_witnesses ||
      traceUnknownProbes !== traceSummary.fresh_producer_and_replay_unknown_probes ||
      traceTamperRejections !== traceSummary.semantically_tampered_reports_rejected ||
      traceEqualDpChecks !== traceSummary.proved_equal_finite_dp_checks ||
      traceEqualHistograms !== traceSummary.proved_equal_scenario_histograms_checked ||
      traceWitnessDpChecks !== traceSummary.finite_witness_dp_checks ||
      traceDistinguishingDpChecks !== traceSummary.finite_witness_dp_distinguishing_checks) {
    throw new Error("The exact trace-equivalence split fixture or proof/witness totals changed.");
  }
  const gapDp = await verifyTraceArtifact(gapFixture.finite_dp_cross_check, "split-fixture finite-DP cross-check");
  if (!Array.isArray(gapDp.checks) || gapDp.checks.length !== 8 ||
      !gapDp.checks.some((check) => check.horizon === 2 && check.observer === "trace" && check.equal_exact_histograms === true)) {
    throw new Error("The split-fixture H=2 ordered-trace DP cross-check is missing or changed.");
  }

  const summary = channel.summary || {};
  if (summary.fixtures !== 11 || summary.channel_analyses !== 130 || summary.histogram_comparisons !== 260 ||
      summary.exact_unit_mass_rows !== 260 || summary.different_histograms !== 0 ||
      summary.mean_equal_but_positive_tv_analyses !== 17 || summary.unknown_resource_probes !== 11) {
    throw new Error("Finite channel study totals differ from the reviewed evidence.");
  }
  const sameMean = parse("bench/results/probabilistic_channels/same_mean_distinct_laws.h1.aggregate.json");
  const aggregate = parse("bench/results/probabilistic_channels/aggregate_hides_order.h2.aggregate.json");
  const trace = parse("bench/results/probabilistic_channels/aggregate_hides_order.h2.trace.json");
  const pairTV = (r) => r.metrics?.pairwise?.[0]?.total_variation;
  if (sameMean.status !== "complete" || sameMean.horizon !== 1 || pairTV(sameMean) !== "1" || sameMean.metrics?.mutual_information_bits_approx !== 1 ||
      aggregate.status !== "complete" || aggregate.observer !== "aggregate" || aggregate.horizon !== 2 || pairTV(aggregate) !== "0" ||
      trace.status !== "complete" || trace.observer !== "trace" || trace.horizon !== 2 || pairTV(trace) !== "1") {
    throw new Error("The two finite-channel hook reports changed from the reviewed exact results.");
  }

  const bridgeTotals = sourceGraph.totals || {};
  const langTotals = langStudy.totals || {};
  const runtimeTotals = langRuntime.totals || {};
  const frontendTests = (await fs.readFile(path.join(ROOT_DIR, "integrations/langgraph/source_frontend/test_extract.py"), "utf8").then((s) => s.match(/^\s*def test_/gm) || [])).length;
  if (bridgeTotals.attempted_sources !== 20 || bridgeTotals.bridge_status_counts?.exported !== 17 ||
      bridgeTotals.bridge_status_counts?.unsupported_subset !== 3 || bridgeTotals.source_graph_run_pairs !== 720 ||
      bridgeTotals.secret_trace_pairs !== 360 || bridgeTotals.secret_trace_pairs_different !== 0 ||
      langTotals.source_execution_runs !== 36 || langTotals.source_graph_equal !== 30 || langTotals.source_value_probe_equal !== 6 ||
      runtimeTotals.executions !== 888 || runtimeTotals.trace_call_events_compared !== 4528 || runtimeTotals.different_executions !== 0 ||
      runtimeTotals.stopped_executions !== 864 || runtimeTotals.truncated_executions !== 24 || frontendTests !== 20) {
    throw new Error("Source bridge or LangGraph evidence changed from the reviewed denominators.");
  }

  deck.evidence.sourceBridge = {
    attempted: bridgeTotals.attempted_sources,
    exported: bridgeTotals.bridge_status_counts.exported,
    excluded: bridgeTotals.bridge_status_counts.unsupported_subset,
    runPairs: bridgeTotals.source_graph_run_pairs,
    secretPairs: bridgeTotals.secret_trace_pairs,
    traceDifferences: bridgeTotals.secret_trace_pairs_different,
  };
  deck.evidence.langgraphSource = {
    frontendTests,
    sourceRuns: langTotals.source_execution_runs,
    tracePairs: langTotals.source_graph_pairs,
    valuePairs: langTotals.source_value_probe_pairs,
    traceDifferences: langTotals.source_graph_pairs - langTotals.source_graph_equal,
    valueDifferences: langTotals.source_value_probe_pairs - langTotals.source_value_probe_equal,
  };
  deck.evidence.langgraph = {
    version: langRuntime.environment.langgraph.version,
    executions: runtimeTotals.executions,
    stopped: runtimeTotals.stopped_executions,
    truncated: runtimeTotals.truncated_executions,
    events: runtimeTotals.trace_call_events_compared,
    differences: runtimeTotals.different_executions,
  };
  deck.evidence.probability = {
    fixtures: summary.fixtures,
    accepted: summary.accepted_structurally,
    rejected: summary.rejected_structurally,
    analyses: summary.channel_analyses,
    histogramComparisons: summary.histogram_comparisons,
    equalMeanPositiveTV: summary.mean_equal_but_positive_tv_analyses,
    unknownProbes: summary.unknown_resource_probes,
  };
  deck.evidence.stochasticBisim = {
    fixtureCount: stochasticSummary.fixture_count,
    acceptedCases: stochasticSummary.producer_status_counts.proved_equal,
    inconclusiveCases: stochasticSummary.producer_status_counts.inconclusive,
    replayed: stochasticSummary.normal_certificates_independently_verified,
    certificates: stochasticFixtures.length,
    dpComparisons: stochasticSummary.proved_equal_dp_comparisons,
    histograms: stochasticSummary.dp_scenario_histograms_compared,
    capUnknown: stochasticSummary.fresh_state_cap_unknown_probes,
    producerTests: stochasticProducerTests,
    replayerTests: stochasticReplayerTests,
  };
  deck.evidence.traceEquivalence = {
    fixtureCount: traceFixtures.length,
    provedEqual: traceProofs,
    unequal: traceWitnesses,
    replayedProofs: traceProofs,
    replayedWitnesses: traceWitnesses,
    capUnknown: traceUnknownProbes,
    tamperRejected: traceTamperRejections,
    dpChecks: traceEqualDpChecks,
    histograms: traceEqualHistograms,
    witnessDpChecks: traceWitnessDpChecks,
    distinguishingDpChecks: traceDistinguishingDpChecks,
    producerSha: traceProducerSha,
    replayerSha: traceReplayerSha,
    reportSha: createHash("sha256").update(reportBytes.get("bench/results/trace_equivalence.json")).digest("hex"),
  };
  const evidenceLedger = deck.slides.find((item) => item.number === 29);
  if (!evidenceLedger || evidenceLedger.details.length !== 6) throw new Error("The evidence ledger appendix is missing its exact trace-law row.");
  const t = deck.evidence.traceEquivalence;
  evidenceLedger.details[5] = `${t.fixtureCount} cases · ${t.provedEqual} equal / ${t.unequal} unequal · ${t.replayedProofs + t.replayedWitnesses} replayed`;
  evidenceLedger.notes += `\n\nExact trace-law report: ${t.fixtureCount} authored fixtures; ${t.provedEqual} proved equal and ${t.unequal} finite-witness unequal; ${t.replayedProofs} proof certificates and ${t.replayedWitnesses} witnesses independently replayed; ${t.capUnknown} fresh resource-cap probes returned UNKNOWN; ${t.tamperRejected} semantic tamper reports were rejected. Exact DP cross-checks: ${t.dpChecks} equal-case checks across ${t.histograms} scenario histograms; ${t.witnessDpChecks} witness-case checks with ${t.distinguishingDpChecks} distinguishing. These counts belong only to this finite-kernel study.`;
  deck.evidence.currentManifestSha = createHash("sha256").update(manifestBytes).digest("hex");
  deck.evidence.currentCompilerSha = compilerSha;
  deck.evidence.currentReportSha = Object.fromEntries(reportPaths.map((relativePath) => [relativePath, createHash("sha256").update(reportBytes.get(relativePath)).digest("hex")]));
}

function assertComplete() {
  const serialized = JSON.stringify(deck);
  if (/\[\[INSERT|\[\[final|Fill from final/i.test(serialized)) {
    throw new Error("Deck data still contains unfinished presentation placeholders.");
  }
  if (!deck.evidence.diagnosticOutput.includes("[E236]") || deck.evidence.metrics.length !== 4 || !deck.evidence.witness) {
    throw new Error("The hash-checked final compiler evidence was not loaded.");
  }
  if (GRAPH_CANDIDATE && (!deck.evidence.graph || !deck.evidence.stress || !deck.evidence.graphAdversarial)) {
    throw new Error("The graph and independent stress reports were not loaded.");
  }
  if (CURRENT_CANDIDATE && (!deck.evidence.sourceBridge || !deck.evidence.langgraphSource || !deck.evidence.langgraph || !deck.evidence.probability || !deck.evidence.stochasticBisim || !deck.evidence.traceEquivalence)) {
    throw new Error("Current source-bridge, LangGraph, finite-channel, stochastic-bisimulation, or exact trace-equivalence reports were not loaded.");
  }
  if (deck.slides.length !== EXPECTED_SLIDE_COUNT) throw new Error(`Expected ${EXPECTED_SLIDE_COUNT} slides; found ${deck.slides.length}`);
  for (const spec of deck.slides) {
    if (spec.kind === "appendix" && (!spec.details || spec.details.length !== spec.blocks.length)) {
      throw new Error(`Appendix slide ${spec.number} has incomplete detail blocks`);
    }
  }
}

async function renderPngs(presentation, directory) {
  await fs.mkdir(directory, { recursive: true });
  for (const [i, slide] of presentation.slides.items.entries()) {
    const stem = `slide-${String(i + 1).padStart(2, "0")}`;
    await fs.writeFile(path.join(directory, `${stem}.png`), new Uint8Array(await (await presentation.export({ slide, format: "png", scale: 1 })).arrayBuffer()));
  }
}

async function main() {
  await loadFinalEvidence();
  if (GRAPH_CANDIDATE) await loadGraphCandidateEvidence();
  if (CURRENT_CANDIDATE) await loadCurrentEvidence();
  assertComplete();
  await fs.mkdir(BUILD_DIR, { recursive: true });
  await fs.mkdir(OUTPUT_DIR, { recursive: true });
  const pres = Presentation.create({ slideSize: { width: W, height: H } });

  deck.slides.forEach((spec, i) => {
    const index = i + 1;
    const slide = spec.kind === "cover" ? drawCover(pres, spec) : baseSlide(pres, spec, index);
    if (spec.kind !== "cover") addVisual(pres, slide, spec, index);
    if (spec.kind === "cover") {
      // Cover is intentionally unnumbered in the visual reference; its notes remain part of the deck.
    }
  });

  const candidatePath = path.join(BUILD_DIR, "candidate.pptx");
  await (await PresentationFile.exportPptx(pres)).save(candidatePath);
  if (PREVIEW_DIR) {
    const previewPresentation = await PresentationFile.importPptx(await FileBlob.load(candidatePath));
    await renderPngs(previewPresentation, PREVIEW_DIR);
    console.log(JSON.stringify({ candidate: candidatePath, previewPngDir: PREVIEW_DIR, slideCount: previewPresentation.slides.items.length }, null, 2));
    return;
  }
  const { finalizePresentation } = await import(pathToFileURL(path.join(SKILL_DIR, "container_tools/artifact_tool_utils.mjs")).href);
  const requirements = {
    explicitTotalSlideCount: EXPECTED_SLIDE_COUNT,
    requiredNativeChartOwnerSlides: [],
    requiredNativeTableOwnerSlides: [],
    fontPolicy: { basis: "design", families: [FONT.body, FONT.mono] },
    expectedSlideSizeEmu: "12192000,6858000",
    workspaceDir: RESEARCH_DIR,
    candidatePath,
    finalPath: FINAL_PPTX,
    pythonExecutable: RUNTIME_PYTHON,
    integrityValidatorPath: path.join(SKILL_DIR, "container_tools/inspect_presentation_package_integrity.py"),
    layoutValidatorPath: path.join(SKILL_DIR, "container_tools/inspect_presentation_layout_geometry.py"),
    layoutArgs: ["--expected-slide-size-emu", "12192000,6858000", "--validate-bullet-geometry", "--validate-heading-fit"],
    verifyArtifactToolImport: true,
    receiptPath: path.join(BUILD_DIR, `${path.basename(FINAL_NAME, ".pptx")}.${Date.now()}.validation.json`),
  };
  const validation = await finalizePresentation(requirements);
  if (validation?.finalPath !== FINAL_PPTX) throw new Error(`Finalizer did not publish the expected PPTX: ${JSON.stringify(validation)}`);
  const finalPresentation = await PresentationFile.importPptx(await FileBlob.load(FINAL_PPTX));
  if (!SKIP_FINAL_PNGS) await renderPngs(finalPresentation, PNG_DIR);
  console.log(JSON.stringify({ pptx: FINAL_PPTX, pngDir: SKIP_FINAL_PNGS ? null : PNG_DIR, slideCount: finalPresentation.slides.items.length, validation }, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
