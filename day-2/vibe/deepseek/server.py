#!/usr/bin/env python3
"""Serve the GDPR article explorer on http://127.0.0.1:7004.

    python3 server.py                 # port 7004
    python3 server.py --port 8000 --host 0.0.0.0
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).parent
STATIC = HERE / "static"
DATA = HERE / "data" / "gdpr_articles.json"

app = FastAPI(title="GDPR Article Explorer", docs_url=None, redoc_url=None)


@app.get("/api/articles")
def articles():
    """The scraped corpus: article, title, summary, full_article."""
    if not DATA.exists():
        raise HTTPException(503, f"{DATA.name} not found — run scrape_gdpr.py first")
    try:
        payload = json.loads(DATA.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(500, f"{DATA.name} is not valid JSON: {exc}") from exc

    items = payload.get("GDPR", [])
    return JSONResponse(
        {
            "count": len(items),
            "source": "https://gdpr-info.eu/",
            "model": "qwen3.5:4b (Ollama, local)",
            "articles": items,
        }
    )


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")


def main() -> None:
    ap = argparse.ArgumentParser(description="GDPR article explorer server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7004)
    ap.add_argument("--reload", action="store_true")
    args = ap.parse_args()
    if args.reload:
        # reload needs an import string, so make the script directory importable
        sys.path.insert(0, str(HERE))
        uvicorn.run("server:app", host=args.host, port=args.port,
                    reload=True, log_level="info")
    else:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
