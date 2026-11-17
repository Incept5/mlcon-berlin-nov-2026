import re
import sys
from pathlib import Path

import fitz          # PyMuPDF: turns a PDF page into an image
import ollama

HERE = Path(__file__).parent
# The Berlin Senate publishes the same report in German and English, page for page.
# The German one is the default: the model reads German and you ask in English (or any language).
EDITIONS = {"de": "land-berlin-2026.pdf",      # "Land Berlin – Investorenpräsentation, August 2026"
            "en": "state-of-berlin-2026.pdf"}  # "State of Berlin – Investor Presentation, August 2026"
FRONT_MATTER = 0   # printed page numbers match the file (a report with front matter numbered i-iv would need 4 here)
PAGE = int(sys.argv[1]) if len(sys.argv) > 1 else 8   # page 8: a line chart of real GDP growth, Berlin vs Germany, 2007-2025
EDITION = sys.argv[2] if len(sys.argv) > 2 else "de"   # python read_pdf.py 8 en  -> the English edition
PDF = HERE / "data" / EDITIONS[EDITION]
MODEL = "qwen3.5:4b"   # vision-capable; try qwen3.6 or gemma4:26b for sharper reading
TRANSCRIBE = ("Transcribe this page as Markdown. Keep headings, paragraphs and lists. Turn any table into a "
              "Markdown table, and describe any chart or picture in one short paragraph of text (never an image link). "
              "Output only the Markdown.")

# 1. Render just one page: reading all 33 pages would take minutes
page = fitz.open(PDF)[PAGE - 1 + FRONT_MATTER]   # printed page number -> position in the file
png = page.get_pixmap(dpi=150).tobytes("png")


def ask(prompt):
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
