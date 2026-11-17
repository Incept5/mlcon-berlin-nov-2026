# GDPR Article Explorer — DeepSeek Flash

Scrape the GDPR articles from [gdpr-info.eu](https://gdpr-info.eu/), summarise each
one with a **local** model (`qwen3.5:4b` on Ollama), and browse them in a
two-pane web app: pick an article by its plain-English summary, read the full
text on the right.

Currently loaded: **Articles 20–25** (the smoke test). The scraper and the UI both
cope with the full set of 99.

---

## Run it

```bash
# 1. summarise + scrape (writes data/gdpr_articles.json; uses ./cache for HTML)
python3 scrape_gdpr.py                  # default: articles 20–25

# 2. serve the site
python3 server.py                       # http://127.0.0.1:7004
```

Requires `requests`, `beautifulsoup4`, `fastapi`, `uvicorn`, and Ollama running on
`localhost:11434` with `qwen3.5:4b` pulled.

## Commands

| Command | What it does |
| --- | --- |
| `python3 scrape_gdpr.py` | Articles 20–25 (default smoke test) |
| `python3 scrape_gdpr.py --start 1 --end 99` | The whole regulation |
| `python3 scrape_gdpr.py --no-llm` | Scrape text only, skip summaries |
| `python3 scrape_gdpr.py --offline` | Parse cached HTML, never hit the network |
| `python3 scrape_gdpr.py --force` | Re-summarise even if summaries are cached |
| `python3 server.py --host 0.0.0.0 --port 8000` | Serve elsewhere |

`scrape_gdpr.py` is resumable: summaries already in `data/gdpr_articles.json` are
reused, and articles outside the requested range are kept.

## Output

```json
{"GDPR": [
  {
    "article": "Art. 20",
    "title": "Right to data portability",
    "summary": "Individuals can request that companies provide their personal data …",
    "full_article": "1. The data subject shall have the right to receive …\n\n(a) the processing is based on consent …"
  }
]}
```

`full_article` is plain text with the regulation's own structure preserved:
numbered paragraphs (`1.`, `2.`), lettered points (`(a)`, `(b)`), bullets, and
the editorial `<sup>` cross-reference markers stripped.

## How it works

- **Scrape** — gdpr-info's article body is the run of `<ol>`/`<p>` at the start of
  `div.entry-content`; everything after it is recitals, page navigation and a
  feedback widget. The parser walks those children and renders nested lists as
  lettered points, rather than flattening the page text.
- **Cache** — every page is stored in `cache/art-<n>-gdpr.html`. Existing saved
  copies in `../data/gdpr-info/` are read automatically. `--offline` makes the
  network optional, which matters when the room's Wi-Fi is not available.
- **Summarise** — one non-streaming Ollama chat call per article with
  `"think": false` (qwen3.5 thinks by default and a summary does not need it),
  `temperature: 0.2`, and a 70-word limit. The reply is stripped of code fences,
  labels and quotes before it is stored.
- **Serve** — FastAPI serves `static/` plus `/api/articles`; the front end is one
  HTML file, one stylesheet and one script, with no build step and no CDN — it
  works with the network unplugged.

## The site

- Left: summary cards, searchable by keyword (matches title, article number or
  summary; matches are highlighted). Right: the full article, set in a serif face
  with hanging paragraph numbers.
- Keyboard: `/` focuses search, `↓`/`↑` move and open, `Esc` returns to the list
  on narrow screens.
- Deep links: every article has `#art-20`-style URL, and back/forward work.
- Copy button puts `Art. N GDPR — Title` + the full text on the clipboard.
- Responsive: below 880 px the list and reader become two screens with an
  "All articles" back button.

## Adding the rest

```bash
python3 scrape_gdpr.py --start 1 --end 99
```

The site needs no changes: the badge count, the list, the search and the deep
links all read from the JSON. Re-summarising an article only requires removing
its entry from the JSON or passing `--force`.
