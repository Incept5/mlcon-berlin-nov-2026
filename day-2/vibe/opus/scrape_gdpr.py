"""Scrape GDPR articles from gdpr-info.eu and summarise each one with qwen3.5:4b on Ollama.

    python scrape_gdpr.py              # smoke test: articles 20-25
    python scrape_gdpr.py 1-99         # all of them (or e.g. 5,17,30-35)
    python scrape_gdpr.py --refresh    # re-summarise even if already in gdpr.json

Pages are cached in cache/ so a re-run needs no internet; summaries already in
gdpr.json are kept, so a full run can be stopped and resumed.
"""
import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
import ollama

HERE = Path(__file__).parent
CACHE = HERE / "cache"
OUT = HERE / "gdpr.json"
SAVED = HERE.parent.parent / "data" / "gdpr-info"   # copies shipped with day-2
BASE = "https://gdpr-info.eu"
MODEL = "qwen3.5:4b"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def fetch(slug):
    """Return the HTML for e.g. 'art-22-gdpr' ('' = index), from cache if we have it."""
    CACHE.mkdir(exist_ok=True)
    name = (slug or "index") + ".html"
    for p in (CACHE / name, SAVED / name):
        if p.exists():
            return p.read_text(encoding="utf-8")
    r = requests.get(f"{BASE}/{slug}/" if slug else BASE + "/", headers=HEADERS, timeout=30)
    r.raise_for_status()
    (CACHE / name).write_text(r.text, encoding="utf-8")
    time.sleep(0.5)  # be polite to the site
    return r.text


def chapters():
    """Map article number -> {'chapter': 'Chapter 3', 'chapter_title': ..., 'section': ...}."""
    soup = BeautifulSoup(fetch(""), "html.parser")
    out = {}
    for a in soup.select('nav a[href*="/art-"]'):
        m = re.search(r"/art-(\d+)-gdpr/", a["href"])
        if not m:
            continue
        info = {}
        for li in a.find_parents("li"):
            label = li.find("a").get_text(" ", strip=True)
            if label.startswith("Chapter"):
                cm = re.match(r"(Chapter \d+)\s*\(.*?\)\s*(.*)", label)
                info["chapter"], info["chapter_title"] = (cm.group(1), cm.group(2)) if cm else (label, "")
            elif label.startswith("Section"):
                info["section"] = label
        out[int(m.group(1))] = info
    return out


def render_list(ol, depth=0):
    """Flatten an <ol> into numbered lines: 1. / (a) / (i)."""
    # gdpr-info.eu sometimes nests <ol><ol><li>…, so unwrap lists that sit directly in a list
    items = []
    for child in ol.find_all(["li", "ol", "ul"], recursive=False):
        items.extend([child] if child.name == "li" else child.find_all("li", recursive=False))
    lines = []
    for i, li in enumerate(items):
        marker = f"{i + 1}." if depth == 0 else f"({chr(97 + i)})" if depth == 1 else f"({roman(i + 1)})"
        buf, first = [], True

        def flush():
            nonlocal buf, first
            text = clean(" ".join(buf))
            if text:
                # text after a sub-list continues the same paragraph, unnumbered
                lines.append("    " * depth + (f"{marker} " if first else "    ") + text)
                first = False
            buf = []

        for node in li.children:
            if getattr(node, "name", None) in ("ol", "ul"):
                flush()
                if first:  # list with no lead-in text still needs its number
                    lines.append("    " * depth + marker)
                    first = False
                lines.extend(render_list(node, depth + 1))
            else:
                buf.append(node.get_text(" ") if hasattr(node, "get_text") else str(node))
        flush()
    return lines


def clean(text):
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r" ([,.;:)])", r"\1", text).replace("( ", "(")


def roman(n):
    return ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii"][n - 1]


def scrape(n):
    soup = BeautifulSoup(fetch(f"art-{n}-gdpr"), "html.parser")
    title = soup.select_one(".dsgvo-title").get_text(" ", strip=True)
    body = soup.select_one(".entry-content")
    recitals = []
    rec = body.select_one(".empfehlung-erwaegungsgruende")
    if rec:
        recitals = [a.get_text(" ", strip=True) for a in rec.select("a") if a.get_text(strip=True)]
    for junk in body.select(".empfehlung-erwaegungsgruende, .page-navigation, .link-to-overview, .feedback, script, style"):
        junk.decompose()
    lines = []
    for el in body.find_all(["ol", "ul", "p"], recursive=False):
        if el.name == "p":
            t = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
            if t:
                lines.append(t)
        else:
            lines.extend(render_list(el))
    full = "\n".join(lines).strip()
    return {"article": f"Art. {n}", "number": n, "title": title, "full_article": full,
            "recitals": recitals, "url": f"{BASE}/art-{n}-gdpr/"}


PROMPT = """You are an expert EU data-protection lawyer writing for busy professionals.
Summarise GDPR {article} "{title}" in 2-3 plain-English sentences (max 70 words).
Say what it requires or grants and who it applies to. No preamble, no bullet points,
do not start with "This article".

{text}"""


def summarise(art):
    resp = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT.format(article=art["article"], title=art["title"],
                                                            text=art["full_article"][:12000])}],
        think=False,
        options={"temperature": 0.7, "top_p": 0.8, "top_k": 20, "num_ctx": 8192},
    )
    return resp.message.content.strip().strip('"')


def parse_range(spec):
    nums = set()
    for part in spec.split(","):
        a, _, b = part.partition("-")
        nums.update(range(int(a), int(b or a) + 1))
    return sorted(nums)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    wanted = parse_range(args[0] if args else "20-25")
    refresh = "--refresh" in sys.argv

    existing = {}
    if OUT.exists():
        existing = {a["number"]: a for a in json.loads(OUT.read_text())["GDPR"]}
    chap = chapters()

    for n in wanted:
        old = existing.get(n)
        t0 = time.time()
        art = scrape(n)
        art.update(chap.get(n, {}))
        if old and old.get("summary") and not refresh:
            art["summary"] = old["summary"]
            print(f"{art['article']:>8}  kept summary")
        else:
            art["summary"] = summarise(art)
            print(f"{art['article']:>8}  {time.time() - t0:5.1f}s  {art['summary'][:90]}…")
        # key order matches the requested JSON shape
        existing[n] = {"article": art.pop("article"), "summary": art.pop("summary"),
                       "full_article": art.pop("full_article"), **art}
        OUT.write_text(json.dumps({"GDPR": [existing[k] for k in sorted(existing)]},
                                  indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n{len(existing)} articles in {OUT}")


if __name__ == "__main__":
    main()
