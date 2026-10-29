"""Check protected content in the final prose pass and prepare PDF contact sheets."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def citations(text):
    return Counter(key.strip() for group in re.findall(r"\\cite\{([^}]+)\}", text)
                   for key in group.split(","))


def equations(text):
    parts = re.findall(r"\\\[(.*?)\\\]", text, re.S)
    parts += re.findall(r"(?<!\\)\$(.*?)(?<!\\)\$", text, re.S)
    parts += [body for _, body in re.findall(r"\\begin\{(align\*?|equation\*?)\}(.*?)\\end\{\1\}", text, re.S)]
    def canonical(value):
        value = re.sub(r"\\(?:begin|end)\{gathered\}", "", value)
        return re.sub(r"\s+", "", value.replace("\\\\", ""))
    return Counter(map(canonical, parts))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--render-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    before = json.loads(args.baseline.read_text(encoding="utf-8"))
    protected = {}
    for name, old in before.items():
        new = (ROOT / name.replace("\\", "/")).read_text(encoding="utf-8")
        result = dict(numbers_equal=Counter(re.findall(r"\d+(?:\.\d+)?", old)) == Counter(re.findall(r"\d+(?:\.\d+)?", new)),
                      citations_equal=citations(old) == citations(new), equations_equal=equations(old) == equations(new))
        assert all(result.values()), (name, result)
        protected[name] = result
    source = (ROOT / "paper/main.tex").read_text(encoding="utf-8")
    original = subprocess.check_output(["git", "show", "0daad41:paper/main.tex"], cwd=ROOT).decode("utf-8")
    assert not (citations(original) - citations(source)), "an existing citation occurrence was dropped"
    bibliography = (ROOT / "paper/refs.bib").read_text(encoding="utf-8")
    keys = re.findall(r"@\w+\{([^,]+),", bibliography)
    assert len(keys) == len(set(keys)), "duplicate bibliography key"
    included_source = "\n".join((ROOT / name.replace("\\", "/")).read_text(encoding="utf-8")
                                for name in before if name.endswith(".tex"))
    assert set(citations(included_source)) <= set(keys), "missing bibliography entry"
    assert not re.search(r"Codex|awaits human|Consent to this revision|companion C\+\+", source)
    assert "—" not in source and "---" not in source
    latex = (ROOT / "paper/main.log").read_text(encoding="utf-8", errors="replace")
    assert not re.search(r"Overfull|undefined|LaTeX Warning", latex)
    from PIL import Image, ImageDraw, ImageOps
    from pypdf import PdfReader
    pdf = ROOT / "paper/main.pdf"
    pages = list(PdfReader(pdf).pages)
    images = sorted(args.render_directory.glob("page-*.png"))
    assert len(images) == len(pages)
    contacts = []
    for start in range(0, len(images), 4):
        sheet = Image.new("RGB", (1300, 1880), "#dddfe2")
        draw = ImageDraw.Draw(sheet)
        for offset, path in enumerate(images[start:start+4]):
            image = Image.open(path).convert("RGB")
            image.thumbnail((630, 900))
            x, y = (offset % 2) * 650 + 10, (offset // 2) * 940 + 28
            sheet.paste(image, (x, y))
            draw.text((x, y-20), f"Page {start+offset+1}", fill="black")
        target = args.render_directory / f"contact-{start//4+1:02d}.jpg"
        sheet.save(target, quality=90)
        contacts.append(str(target.resolve()))
    figure_pages = {str(i+1): [phrase for phrase in ("Complete core grammar", "Operational semantics", "Label propagation", "One frozen implementation", "Actual source-derived admission", "Native-prefill prototype")
                             if phrase in page.extract_text()] for i, page in enumerate(pages)}
    result = dict(schema="orchlang-final-manuscript-qa-v1", protected_content=protected,
                  original_citations_preserved=True, bibliography_keys_unique=True,
                  undefined_references=False, overfull_boxes=False, pages=len(pages),
                  pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
                  figure_pages={key: value for key, value in figure_pages.items() if value},
                  contact_sheets=contacts, visual_review="pending")
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key not in ("protected_content", "contact_sheets")}, indent=2))


if __name__ == "__main__":
    main()
