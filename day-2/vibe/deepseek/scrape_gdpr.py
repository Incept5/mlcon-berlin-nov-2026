#!/usr/bin/env python3
"""Scrape GDPR articles from gdpr-info.eu and summarise each one with a local
LLM (Ollama, qwen3.5:4b).

Writes JSON shaped like:

    {"GDPR": [{"article": "Art. 20",
               "title": "Right to data portability",
               "summary": "...",
               "full_article": "1. ...\\n\\n2. ..."}]}

Usage
-----
    python3 scrape_gdpr.py                  # default smoke test: articles 20-25
    python3 scrape_gdpr.py --start 1 --end 99
    python3 scrape_gdpr.py --offline        # use cached HTML only, no network
    python3 scrape_gdpr.py --no-llm         # scrape only, skip summaries

Fetched pages are cached in ./cache/ so repeated runs never hit the network
(the room's internet is assumed to be unusable).  Existing saved copies in
../data/gdpr-info/ are picked up automatically.
"""

from __future__ import annotations

import argparse
import json
import re
import string
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

HERE = Path(__file__).parent
CACHE_DIR = HERE / "cache"
LEGACY_CACHE = HERE.parent / "data" / "gdpr-info"
OUT_PATH = HERE / "data" / "gdpr_articles.json"

URL = "https://gdpr-info.eu/art-{n}-gdpr/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.5:4b"

# gdpr-info.eu publishes 99 articles (Art. 1 - Art. 99).
MAX_ARTICLE = 99


# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #
def cache_path(n: int) -> Path:
    return CACHE_DIR / f"art-{n}-gdpr.html"


def fetch_html(n: int, offline: bool = False) -> str:
    """Return the article page HTML, preferring the on-disk cache."""
    for src in (cache_path(n), LEGACY_CACHE / f"art-{n}-gdpr.html"):
        if src.exists():
            return src.read_text(encoding="utf-8")

    if offline:
        raise FileNotFoundError(f"Art. {n} is not cached and --offline was given")

    url = URL.format(n=n)
    print(f"  fetching {url} …", end=" ", flush=True)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path(n).write_text(resp.text, encoding="utf-8")
    print("ok")
    return resp.text


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def norm(text: str) -> str:
    """Collapse whitespace and close the gaps left by removed <sup>/links."""
    text = text.replace(" ", " ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:)\]])", r"\1", text)
    text = re.sub(r"\(\s+", "(", text)
    return text.strip()


def clean_text(tag) -> str:
    """Text of a tag with nested lists and the editorial <sup> markers removed."""
    frag = BeautifulSoup(str(tag), "html.parser")
    for node in frag.find_all(["ol", "ul", "sup"]):
        node.decompose()
    return norm(frag.get_text(""))


def render_list(lst, depth: int = 0) -> list[str]:
    """Render an <ol>/<ul> as numbered / lettered / bulleted plain-text lines."""
    lines: list[str] = []
    is_ordered = lst.name == "ol"
    for i, li in enumerate(lst.find_all("li", recursive=False)):
        if not is_ordered:
            marker = "•"
        elif depth == 0:
            marker = f"{i + 1}."
        else:
            marker = f"({string.ascii_lowercase[i % 26]})"
        body = clean_text(li)
        if body:
            lines.append(f"{marker} {body}")
        for sub in li.find_all(["ol", "ul"], recursive=False):
            lines.extend(render_list(sub, depth + 1))
    return lines


def parse_article(html: str, n: int) -> dict | None:
    """Extract (title, article label, full text) from an article page."""
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1")
    if not h1:
        return None
    # h1 = "Art. 20 GDPR" + "Right to data portability"
    heading = h1.get_text(" ", strip=True)
    m = re.match(r"(Art\.\s*\d+)\s*GDPR\s*(.*)$", heading)
    label = m.group(1) if m else f"Art. {n}"
    title = m.group(2).strip() if m else ""

    entry = soup.select_one("div.entry-content")
    if not entry:
        entry = soup.find("article")
    if not entry:
        return None

    # The article body is the run of <ol>/<p> before the "Suitable Recitals"
    # block, the page navigation and the feedback widget.
    body_tags = []
    for child in entry.children:
        name = getattr(child, "name", None)
        if name is None:
            continue
        if name in ("ol", "ul", "p", "blockquote"):
            body_tags.append(child)
        else:
            break  # first <div> is the recitals/nav furniture

    lines: list[str] = []
    para_no = 0
    for tag in body_tags:
        if tag.name in ("ol", "ul"):
            lines.extend(render_list(tag))
        else:
            para_no += 1
            body = clean_text(tag)
            if body:
                lines.append(f"{para_no}. {body}" if len(body_tags) > 1 else body)

    full_text = "\n\n".join(lines).strip()
    if not full_text:
        return None
    return {"article": label, "title": title, "full_article": full_text}


# --------------------------------------------------------------------------- #
# Summarising
# --------------------------------------------------------------------------- #
SUMMARY_PROMPT = """You are a careful legal editor writing for a general audience.

Below is the full text of {label} of the EU General Data Protection Regulation.

Title: {title}
\"\"\"
{body}
\"\"\"

Write a summary of this article in TWO or THREE sentences, at most 65 words, in
plain English.

- Lead with the right or obligation it creates and who it protects or binds.
- Cover every main obligation the article names: if it sets out two duties, or a
  right and its default rule, say both. Do not drop half of the article.
- Be exact about legal grounds and conditions. If the article ties a right to
  specific points of Article 6 or 9, cite the point numbers instead of naming a
  legal ground in your own words; never swap one ground for another.
- If the article contains a long list, summarise the kinds of items in a few
  words rather than enumerating them.
- Preserve negations and qualifiers exactly: never turn "must not" into "must",
  or "not accessible" into "accessible".
- Do not state an obligation as unconditional if the article qualifies it, and
  do not invent details.

No markdown, no labels, no article number. Return only the summary."""


def summarise(article: dict, model: str = MODEL, timeout: int = 180) -> str:
    """Ask the local model for a plain-English summary."""
    prompt = SUMMARY_PROMPT.format(
        label=article["article"],
        title=article["title"],
        body=article["full_article"][:12000],
    )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,  # qwen3.5 defaults to thinking; a summary does not need it
        "options": {"temperature": 0.2, "top_p": 0.9, "num_predict": 220},
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
    resp.raise_for_status()
    text = resp.json()["message"]["content"].strip()

    # The small model occasionally still fences or labels its answer.
    text = re.sub(r"^```[a-z]*\s*|\s*```$", "", text).strip()
    text = re.sub(r"^(summary|answer)\s*[:\-]\s*", "", text, flags=re.I)
    text = re.sub(r'^["“\']+|["”\']+$', "", text).strip()
    return norm(text)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def load_existing(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {a["article"]: a for a in data.get("GDPR", [])}
    except (json.JSONDecodeError, KeyError, TypeError):
        return {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", type=int, default=20, help="first article (default 20)")
    ap.add_argument("--end", type=int, default=25, help="last article, inclusive (default 25)")
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--offline", action="store_true", help="never use the network")
    ap.add_argument("--no-llm", action="store_true", help="scrape text only, no summaries")
    ap.add_argument("--force", action="store_true", help="re-summarise even if cached")
    args = ap.parse_args()

    if not (1 <= args.start <= args.end <= MAX_ARTICLE):
        ap.error(f"need 1 <= start <= end <= {MAX_ARTICLE}")

    existing = load_existing(args.out)
    results: list[dict] = []
    failures: list[int] = []

    for n in range(args.start, args.end + 1):
        print(f"Art. {n}:", end=" ")
        try:
            html = fetch_html(n, offline=args.offline)
        except (requests.RequestException, FileNotFoundError) as exc:
            print(f"SKIP ({exc})")
            failures.append(n)
            continue

        parsed = parse_article(html, n)
        if not parsed:
            print("SKIP (could not parse)")
            failures.append(n)
            continue

        prev = existing.get(parsed["article"])
        if prev and not args.force and prev.get("summary"):
            parsed["summary"] = prev["summary"]
            print(f"cached summary ({len(parsed['full_article']):,} chars)")
        elif args.no_llm:
            parsed["summary"] = ""
            print(f"no summary requested ({len(parsed['full_article']):,} chars)")
        else:
            print(f"summarising {len(parsed['full_article']):,} chars …",
                  end=" ", flush=True)
            t0 = time.time()
            try:
                parsed["summary"] = summarise(parsed, model=args.model)
                print(f"{time.time() - t0:.1f}s")
            except Exception as exc:  # noqa: BLE001 - keep the run going
                print(f"LLM FAILED ({exc})")
                parsed["summary"] = ""
                failures.append(n)

        results.append(parsed)

    # Keep anything already in the output file that this run did not cover.
    for label, art in existing.items():
        if art["article"] not in {r["article"] for r in results}:
            results.append(art)
    results.sort(key=lambda a: int(re.search(r"\d+", a["article"]).group()))

    # Fixed key order: article, title, summary, full_article.
    ordered = [
        {k: art.get(k, "") for k in ("article", "title", "summary", "full_article")}
        for art in results
    ]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"GDPR": ordered}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"\nWrote {len(results)} article(s) to {args.out}")
    if failures:
        print(f"⚠️  problems with: {', '.join(f'Art. {n}' for n in failures)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
