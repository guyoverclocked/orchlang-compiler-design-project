"""Fetch primary metadata for references actually cited in the active manuscript.

Stores metadata and access failures, not article full text. Human comparison of
the cited claim to the paper remains necessary. Output is never overwritten.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


class CitationMeta(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and attrs.get("name", "").startswith("citation_"):
            self.meta.setdefault(attrs["name"], []).append(attrs.get("content", ""))


def fetch(item):
    key, entry = item
    doi = re.search(r"doi\s*=\s*\{([^}]+)", entry, re.I)
    arxiv = re.search(r"arXiv:(\d{4}\.\d{4,5}(?:v\d+)?)", entry, re.I)
    url = "https://api.crossref.org/works/" + doi[1] if doi else "https://arxiv.org/abs/" + arxiv[1] if arxiv else None
    if not url:
        return dict(key=key, status="manual-check-required", reason="repository or author-hosted source")
    try:
        req = Request(url, headers={"User-Agent": "OrchLang-reference-audit/1.0"})
        with urlopen(req, timeout=25) as response:
            raw = response.read().decode("utf-8")
        if doi:
            message = json.loads(raw)["message"]
            metadata = {k: message.get(k) for k in ("DOI", "title", "container-title", "type", "volume", "issue", "page", "article-number", "published", "author")}
        else:
            parser = CitationMeta()
            parser.feed(raw)
            metadata = parser.meta
        return dict(key=key, status="metadata-retrieved" if metadata else "no-metadata", source=url, metadata=metadata)
    except Exception as error:
        return dict(key=key, status="access-failed", source=url, error=repr(error))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    cited = {key.strip() for match in re.findall(r"\\cite\{([^}]+)\}", (ROOT / "paper/main.tex").read_text()) for key in match.split(",")}
    bibliography = (ROOT / "paper/refs.bib").read_text()
    entries = {match[1]: match[2] for match in re.finditer(r"@\w+\{([^,]+),(.*?)(?=\n@|\Z)", bibliography, re.S)}
    missing = sorted(cited - entries.keys())
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(fetch, [(key, entries[key]) for key in sorted(cited) if key in entries]))
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(dict(date="2026-10-25", missing_keys=missing, references=results,
                       limitation="Metadata retrieval is not full-text claim validation or proof of peer review."), stream, indent=2)
        stream.write("\n")
    print(json.dumps(dict(cited=len(cited), missing_keys=missing, status_counts={status: sum(r["status"] == status for r in results) for status in sorted({r["status"] for r in results})})))
