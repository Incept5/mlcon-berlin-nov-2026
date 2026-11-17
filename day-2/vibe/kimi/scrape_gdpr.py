#!/usr/bin/env python3
"""Build gdpr.json from gdpr-info.eu, using a local Ollama model for summaries.

Smoke test (the default):
    python3 scrape_gdpr.py

All 99 GDPR articles:
    python3 scrape_gdpr.py --start 1 --end 99

Existing entries are reused. Add --force to scrape and summarise them again.
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

HERE = Path(__file__).parent
DEFAULT_OUTPUT = HERE / "gdpr.json"
DEFAULT_MODEL = "qwen3.5:4b"
SOURCE_URL = "https://gdpr-info.eu/art-{number}-gdpr/"


def clean_text(value):
    """Normalise whitespace without adding spaces before punctuation."""
    value = re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()
    value = re.sub(r"\s+([.,;:!?)\]])", r"\1", value)
    value = re.sub(r"([(\[])\s+", r"\1", value)
    return value


def alphabetic_marker(number):
    letters = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(97 + remainder) + letters
    return letters


def roman_marker(number):
    values = (
        (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"),
        (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
        (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
    )
    result = ""
    for value, numeral in values:
        while number >= value:
            result += numeral
            number -= value
    return result


def direct_inline_text(element):
    """Read a list item without duplicating the text in its nested lists."""
    parts = []
    for child in element.children:
        if isinstance(child, NavigableString):
            parts.append(str(child))
        elif isinstance(child, Tag) and child.name not in ("ol", "ul"):
            parts.append(child.get_text("", strip=False))
    return clean_text("".join(parts))


def render_list(list_element, depth=0):
    """Turn the site's nested HTML lists into readable, numbered plain text."""
    lines = []
    items = list_element.find_all("li", recursive=False)
    start = int(list_element.get("start", 1))

    for offset, item in enumerate(items):
        number = start + offset
        if list_element.name == "ul":
            marker = "•"
        elif depth == 0:
            marker = f"{number}."
        elif depth == 1:
            marker = f"({alphabetic_marker(number)})"
        else:
            marker = f"({roman_marker(number)})"

        text = direct_inline_text(item)
        if text:
            lines.append(f"{'   ' * depth}{marker} {text}")

        for nested in item.find_all(["ol", "ul"], recursive=False):
            lines.extend(render_list(nested, depth + 1))

        if depth == 0:
            lines.append("")

    return lines


def scrape_article(session, number):
    url = SOURCE_URL.format(number=number)
    response = session.get(url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    heading = soup.select_one("h1.entry-title")
    content = soup.select_one(".entry-content")
    if not heading or not content:
        raise ValueError(f"Article {number}: expected heading/content not found")

    heading_text = clean_text(heading.get_text(" ", strip=True))
    match = re.match(r"Art\.\s*(\d+)\s+GDPR\b", heading_text, re.IGNORECASE)
    if not match or int(match.group(1)) != number:
        raise ValueError(f"Article {number}: unexpected heading {heading_text!r}")

    # gdpr-info.eu uses superscripts for amendment markers, not article text.
    for superscript in content.select("sup"):
        superscript.decompose()

    blocks = []
    for element in content.find_all(["p", "ol", "ul"], recursive=False):
        if element.name in ("ol", "ul"):
            blocks.extend(render_list(element))
        else:
            text = clean_text(element.get_text("", strip=False))
            if text:
                blocks.extend([text, ""])

    full_article = "\n".join(blocks).strip()
    if len(full_article) < 100:
        raise ValueError(f"Article {number}: extracted text is unexpectedly short")

    return full_article


def summarise_article(session, number, full_article, model, ollama_url):
    prompt = f"""Summarise Article {number} of the GDPR for a practical article browser.

Write one clear, accurate summary of at most 45 words. Mention the main right or
obligation and any essential scope or exception. Use plain English, do not add
legal advice, and do not invent details. Base the summary only on this text:

{full_article}"""
    payload = {
        "model": model,
        "stream": False,
        "think": False,
        "messages": [
            {
                "role": "system",
                "content": "You are a precise legal summariser. Return only the requested JSON object.",
            },
            {"role": "user", "content": prompt},
        ],
        "format": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
            "additionalProperties": False,
        },
        "options": {
            "temperature": 0.7,
            "top_p": 0.8,
            "top_k": 20,
            "num_predict": 240,
        },
    }

    last_error = None
    for attempt in range(2):
        try:
            response = session.post(
                f"{ollama_url}/api/chat", json=payload, timeout=(5, 180)
            )
            response.raise_for_status()
            content = response.json()["message"]["content"]
            summary = clean_text(json.loads(content)["summary"])
            if not 30 <= len(summary) <= 600:
                raise ValueError(f"summary length was {len(summary)} characters")
            return summary
        except (requests.RequestException, KeyError, ValueError, json.JSONDecodeError) as error:
            last_error = error
            if attempt == 0:
                print(f"  Retrying summary after: {error}", file=sys.stderr)

    raise RuntimeError(f"Ollama could not summarise Article {number}: {last_error}")


def article_number(entry):
    match = re.search(r"\d+", entry.get("article", ""))
    if not match:
        raise ValueError(f"Invalid article identifier: {entry.get('article')!r}")
    return int(match.group(0))


def write_json(output, entries):
    entries.sort(key=article_number)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps({"GDPR": entries}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=int, default=20, help="first article (default: 20)")
    parser.add_argument("--end", type=int, default=25, help="last article (default: 25)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model (default: {DEFAULT_MODEL})")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="JSON output path")
    parser.add_argument("--force", action="store_true", help="replace existing article entries")
    args = parser.parse_args()

    if not 1 <= args.start <= args.end <= 99:
        parser.error("article range must be within 1–99 and start must not exceed end")

    ollama_url = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    if not ollama_url.startswith(("http://", "https://")):
        ollama_url = "http://" + ollama_url

    entries_by_number = {}
    if args.output.exists():
        try:
            saved = json.loads(args.output.read_text(encoding="utf-8"))
            for entry in saved["GDPR"]:
                if all(entry.get(key) for key in ("article", "summary", "full_article")):
                    entries_by_number[article_number(entry)] = entry
        except (OSError, ValueError, KeyError, TypeError) as error:
            print(f"Ignoring unreadable existing output: {error}", file=sys.stderr)

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 GDPR local-LLM teaching demo"})
    failures = []

    for number in range(args.start, args.end + 1):
        if number in entries_by_number and not args.force:
            print(f"Article {number}: already in {args.output.name}; skipping")
            continue

        try:
            print(f"Article {number}: scraping gdpr-info.eu …", flush=True)
            full_article = scrape_article(session, number)
            print(f"Article {number}: summarising locally with {args.model} …", flush=True)
            summary = summarise_article(session, number, full_article, args.model, ollama_url)
            entries_by_number[number] = {
                "article": f"Art. {number}",
                "summary": summary,
                "full_article": full_article,
            }
            write_json(args.output, list(entries_by_number.values()))
            print(f"  {summary}\n", flush=True)
            time.sleep(0.25)
        except (requests.RequestException, ValueError, RuntimeError) as error:
            failures.append(number)
            print(f"Article {number} failed: {error}", file=sys.stderr)

    print(f"Wrote {len(entries_by_number)} articles to {args.output}")
    if failures:
        raise SystemExit(f"Failed articles: {', '.join(map(str, failures))}")


if __name__ == "__main__":
    main()
