#!/usr/bin/env python3
"""
Scrape GDPR articles from gdpr-info.eu, summarise each with a local LLM
(qwen3.5:4b on Ollama), and write site/gdpr.json for the article explorer.

Saved copies of the pages are read from ../data/gdpr-info/ when they exist
(the room's internet is assumed unusable — same convention as
day-2/scrape_gdpr_article.py). --live fetches fresh copies and saves them
back there for next time.

Usage:
    python3 scrape_gdpr.py               # articles 20-25 (smoke test)
    python3 scrape_gdpr.py 1 99          # full run (do after the smoke test)
    python3 scrape_gdpr.py 22 --live     # refetch one article from the site
    python3 scrape_gdpr.py --model qwen3.5:9b

Output JSON shape (per article):
    {"GDPR": [{"article": "Art. 20", "title": "...", "chapter": "Chapter III — ...",
               "summary": "<from the LLM>", "full_article": "1. ..."}, ...]}
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent          # day-2/vibe/glm
SAVED_DIR = HERE.parent.parent / "data" / "gdpr-info"  # day-2/data/gdpr-info (class convention)
OUT_PATH = HERE / "site" / "gdpr.json"

URL_TEMPLATE = "https://gdpr-info.eu/art-{n}-gdpr/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}

# Chapter boundaries of the GDPR itself (Regulation (EU) 2016/679).
CHAPTERS = [
    (1, 4, "Chapter I", "General provisions"),
    (5, 11, "Chapter II", "Principles"),
    (12, 22, "Chapter III", "Rights of the data subject"),
    (23, 43, "Chapter IV", "Controller and processor"),
    (44, 50, "Chapter V", "Transfer of personal data to third countries"),
    (51, 59, "Chapter VI", "Independent supervisory authorities"),
    (60, 76, "Chapter VII", "Cooperation and consistency"),
    (77, 84, "Chapter VIII", "Remedies, liability and penalties"),
    (85, 91, "Chapter IX", "Provisions relating to specific processing situations"),
    (92, 93, "Chapter X", "Delegated acts and implementing acts"),
    (94, 99, "Chapter XI", "Final provisions"),
]


def chapter_for(n: int) -> str:
    for lo, hi, roman, name in CHAPTERS:
        if lo <= n <= hi:
            return f"{roman} — {name}"
    return "GDPR"


def load_page(n: int, live: bool) -> str:
    """Read the saved copy of the article page; fetch and save it only with --live."""
    url = URL_TEMPLATE.format(n=n)
    saved = SAVED_DIR / f"art-{n}-gdpr.html"
    if saved.exists() and not live:
        print(f"  page: saved copy {saved.name}")
        return saved.read_text(encoding="utf-8")

    print(f"  page: fetching {url}")
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    SAVED_DIR.mkdir(parents=True, exist_ok=True)
    saved.write_text(resp.text, encoding="utf-8")
    time.sleep(1.0)  # be polite to gdpr-info.eu
    return resp.text


def clean_text(s: str) -> str:
    s = " ".join(s.split())
    # bs4's get_text(" ") puts a space at every inline tag boundary; undo the
    # ones that land inside "Article 6 (1)" or before punctuation "Article 17 ."
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+([)\].,;:!])", r"\1", s)
    return s


def render_list(ol, depth: int = 0) -> list[str]:
    """Turn the article's <ol> into text: '1. …' paragraphs with '(a) …' sub-points."""
    lines: list[str] = []
    for i, li in enumerate(ol.find_all("li", recursive=False)):
        nested = li.find_all("ol", recursive=False)
        for nol in nested:
            nol.extract()
        text = clean_text(li.get_text(" ", strip=True))
        if depth == 0:
            lines.append(f"{i + 1}. {text}")
        else:
            letter = "abcdefghijklmnopqrstuvwxyz"[i % 26]
            lines.append(f"({letter}) {text}")
        for nol in nested:
            lines.extend(render_list(nol, depth + 1))
    return lines


def parse_article(html: str, n: int) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.select_one("h1.entry-title")
    if h1 is None:
        raise ValueError("no h1.entry-title — page layout not recognised")
    number = clean_text(h1.select_one(".dsgvo-number").get_text())  # "Art. 20 GDPR"
    title = clean_text(h1.select_one(".dsgvo-title").get_text())    # "Right to data portability"
    label = number.replace("GDPR", "").strip()                       # "Art. 20"

    content = soup.select_one(".entry-content")
    if content is None:
        raise ValueError("no .entry-content — page layout not recognised")

    # Drop everything that is not the article text itself.
    for junk in content.select(
        ".empfehlung-erwaegungsgruende, .page-navigation, .link-to-overview, .feedback, "
        ".hidden-print, .adsbygoogle, script, style, table"
    ):
        junk.decompose()
    for sup in content.find_all("sup"):  # official-text sentence numbers
        sup.decompose()

    preamble = [
        clean_text(p.get_text(" ", strip=True))
        for p in content.find_all("p", recursive=False)
        if clean_text(p.get_text(" ", strip=True))
    ]

    lines: list[str] = []
    for ol in content.find_all("ol", recursive=False):
        lines.extend(render_list(ol))
    if not lines:
        raise ValueError("no numbered paragraphs found")
    full_text = "\n".join(preamble + lines)

    return {"article": label, "title": title, "chapter": chapter_for(n), "full_article": full_text}


def summarise(model: str, label: str, title: str, full_text: str) -> str:
    import ollama

    messages = [
        {
            "role": "system",
            "content": (
                "You summarise GDPR articles for a compliance web app. You write plain "
                "English a product manager understands: no legal jargon, no preamble, no "
                "markdown. Answer with the summary text only."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Summarise GDPR {label} — {title} in one or two sentences, at most 45 "
                f"words. State the right or obligation it creates, who holds it, and any "
                f"key limit or exception.\n\nOfficial text:\n{full_text}"
            ),
        },
    ]
    r = ollama.chat(
        model=model,
        messages=messages,
        think=False,  # summaries don't need the reasoning trace
        options={"temperature": 0.7, "top_p": 0.8, "top_k": 20},  # house Qwen non-thinking params
    )
    s = r.message.content.strip()
    s = re.sub(r"^[\"'“”]+|[\"'“”]+$", "", s.strip())  # stray wrapping quotes
    s = s.replace("**", "")                                            # stray markdown bold
    s = re.sub(r"(?im)^(summary|zusammenfassung)\s*[:\-]\s*", "", s)    # stray labels
    return clean_text(s)


def load_existing() -> dict:
    if OUT_PATH.exists():
        try:
            return json.loads(OUT_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("first", nargs="?", type=int, default=20)
    ap.add_argument("last", nargs="?", type=int, default=25)
    ap.add_argument("--live", action="store_true", help="fetch pages from gdpr-info.eu instead of saved copies")
    ap.add_argument("--model", default="qwen3.5:4b", help="Ollama model for the summaries")
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    args = ap.parse_args()

    numbers = list(range(args.first, args.last + 1))
    print(f"Articles {numbers[0]}–{numbers[-1]} | model {args.model} | live={args.live}\n")

    data = load_existing()
    items = {a["article"]: a for a in data.get("GDPR", [])}

    for n in numbers:
        print(f"Art. {n}:")
        try:
            art = parse_article(load_page(n, args.live), n)
        except Exception as e:  # noqa: BLE001 — one bad page must not kill the run
            print(f"  FAILED to parse: {e}")
            continue
        print(f"  {art['article']} — {art['title']} ({art['chapter']})")
        print(f"  {len(art['full_article'])} chars of article text")

        print(f"  summarising with {args.model} …")
        try:
            art["summary"] = summarise(args.model, art["article"], art["title"], art["full_article"])
        except Exception as e:  # noqa: BLE001
            print(f"  FAILED to summarise (is Ollama running on :11434?): {e}")
            continue
        print(f"  summary: {art['summary']}\n")

        items[art["article"]] = art

    ordered = sorted(items.values(), key=lambda a: int(re.search(r"\d+", a["article"]).group()))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"GDPR": ordered}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {len(ordered)} articles to {args.out}")


if __name__ == "__main__":
    main()
