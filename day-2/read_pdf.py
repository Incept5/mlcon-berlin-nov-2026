"""Read one page of the Berlin Senate's investor presentation with a vision model, then ask about its chart.

    python read_pdf.py               # page 8, German edition; the class Spark if it answers, else your laptop
    python read_pdf.py 12 en         # page 12 of the English edition
    python read_pdf.py --spark       # always the class Spark (qwen3.6-35b, fast)
    python read_pdf.py --local       # always your laptop (qwen3.5:4b via Ollama)
"""
import base64
import os
import re
import sys
from pathlib import Path

import fitz          # PyMuPDF: turns a PDF page into an image
import ollama
from openai import OpenAI

HERE = Path(__file__).parent
# The Berlin Senate publishes the same report in German and English, page for page.
# The German one is the default: the model reads German and you ask in English (or any language).
EDITIONS = {"de": "land-berlin-2026.pdf",      # "Land Berlin – Investorenpräsentation, August 2026"
            "en": "state-of-berlin-2026.pdf"}  # "State of Berlin – Investor Presentation, August 2026"
FRONT_MATTER = 0   # printed page numbers match the file (a report with front matter numbered i-iv would need 4 here)
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
PAGE = int(ARGS[0]) if len(ARGS) > 0 else 8   # page 8: a line chart of real GDP growth, Berlin vs Germany, 2007-2025
EDITION = ARGS[1] if len(ARGS) > 1 else "de"   # python read_pdf.py 8 en  -> the English edition
PDF = HERE / "data" / EDITIONS[EDITION]
MODEL = "qwen3.5:4b"   # laptop model (Ollama), vision-capable; try qwen3.6 or gemma4:26b for sharper reading

# ============================================================================
#  WHERE DOES IT RUN?  "auto" = the class Spark if it answers, otherwise your laptop
#  (or run with --spark / --local)
# ============================================================================
MODE = "auto"
SPARK_MODEL = "qwen3.6-35b"   # vision-capable too, and much faster than a laptop
spark = OpenAI(base_url=os.getenv("SPARK_BASE_URL", "http://192.168.8.246:8000/v1"),
               api_key=(os.getenv("SPARK_API_KEY") or "sk-GMHXy89Nrhku0BfnA6FrYR6F_sOYJeJ4"),
               timeout=120, max_retries=0)


def pick_mode():
    if "--local" in sys.argv:
        return "local"
    if "--spark" in sys.argv:
        return "spark"
    if MODE != "auto":
        return MODE
    try:
        spark.with_options(timeout=3).models.list()
        return "spark"
    except Exception as e:
        print(f"(The class Spark doesn't answer: {type(e).__name__}. Running on this laptop.)")
        return "local"


mode = pick_mode()
print(f"Reading with {SPARK_MODEL + ' on the class Spark' if mode == 'spark' else MODEL + ' on this laptop'}\n")
TRANSCRIBE = ("Transcribe this page as Markdown. Keep headings, paragraphs and lists. Turn any table into a "
              "Markdown table, and describe any chart or picture in one short paragraph of text (never an image link). "
              "Output only the Markdown.")

# 1. Render just one page: reading all 33 pages would take minutes
page = fitz.open(PDF)[PAGE - 1 + FRONT_MATTER]   # printed page number -> position in the file
png = page.get_pixmap(dpi=150).tobytes("png")


def ask(prompt):
    if mode == "spark":       # OpenAI-style: the image travels as a base64 data URL
        reply = spark.chat.completions.create(
            model=SPARK_MODEL, temperature=0, max_tokens=2000,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}}]}])
        text = reply.choices[0].message.content
        return text.strip().removeprefix("```markdown").removesuffix("```").strip()
    reply = ollama.chat(model=MODEL, think=False, options={"temperature": 0, "num_ctx": 8192},
                        messages=[{"role": "user", "content": prompt, "images": [png]}])
    return reply.message.content.strip().removeprefix("```markdown").removesuffix("```").strip()


# 2. The page as Markdown, saved next to this script
markdown = re.sub(r"!\[[^\]]*\]\([^)]*\)\n*", "", ask(TRANSCRIBE))   # small models like to invent image links
out = HERE / f"berlin-{EDITION}-page-{PAGE}.md"
out.write_text(markdown + "\n")
print(markdown, f"\n\n(saved to {out.name})\n")

# 3. Ask questions about the chart or pictures on the page (Enter on its own to finish)
while question := input("Ask about this page (Enter to finish): ").strip():
    print(ask(f"Look at the chart or picture on this page. {question} Answer briefly."), "\n")
