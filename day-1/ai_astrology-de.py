"""Das lustige deutsche Horoskop: ai_astrology.py auf Deutsch, mit Berliner Schnauze.

    python ai_astrology-de.py

Same app as ai_astrology.py (qwen3.5:4b via Ollama, thinking on, rendered with rich);
only the prompts change. Try changing Oma Gerda's personality in SYSTEM_PROMPT, or
turn the temperature up for wilder predictions. Needs `pip install ollama rich`.
"""
from datetime import date

import ollama
from ollama import Options
from rich.console import Console
from rich.markdown import Markdown

LLM = "qwen3.5:4b"
WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

SYSTEM_PROMPT = """Du bist Oma Gerda, eine KI-Astrologin aus Berlin-Neukölln mit echter Berliner Schnauze.
Du schreibst ein kurzes, lustiges und trotzdem positives Horoskop für morgen, auf Deutsch.

Dein Stil:
- Herzlich, aber frech: ein bisschen Berliner Dialekt ("wa?", "Icke", "Keene Panik", "dit"),
  aber so, dass alle es verstehen.
- Die Sterne sagen Alltägliches mit großem kosmischem Ernst voraus: die S-Bahn kommt pünktlich
  (ein Wunder!), ein Parkplatz in Kreuzberg, die perfekte Currywurst, ein Termin beim Bürgeramt,
  ein Pfandbon, der Nachbar, der endlich die Musik leiser macht.
- Gern ein Seitenhieb auf den Flughafen BER oder auf Excel-Tabellen, nie gemein gegen Menschen.
- Am Ende eine Markdown-Liste mit drei Punkten: **Glückszahl**, **Glücksfarbe** und **Kosmischer Tipp**.
- Maximal 150 Wörter. Antworte in Markdown, mit einer Überschrift.
- Immer optimistisch: der Mensch soll lachen und sich auf morgen freuen."""


def main():
    heute = date.today()
    datum = f"{WOCHENTAGE[heute.weekday()]}, {heute.strftime('%d.%m.%Y')}"

    name = input("Wie heißt du? ")
    sternzeichen = input("Dein Sternzeichen? ")

    anweisung = (f"Bitte schreib ein Horoskop für {name}, Sternzeichen {sternzeichen}. "
                 f"Heute ist {datum}.")

    console = Console()
    with console.status("[magenta]Oma Gerda befragt die Sterne …[/magenta]"):
        response = ollama.chat(
            model=LLM, think=True, stream=False,
            messages=[{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": anweisung}],
            options=Options(temperature=0.9, num_ctx=4096, top_p=0.95, top_k=40, num_predict=-1),
        )

    if getattr(response.message, "thinking", None):
        console.print(f"[bold blue]🤔 Oma Gerdas Gedanken:[/bold blue]\n[dim]{response.message.thinking}[/dim]")
        console.print("\n" + "=" * 50 + "\n")

    console.print("[bold magenta]🔮 Dein Horoskop:[/bold magenta]")
    console.print(Markdown(response.message.content))


if __name__ == "__main__":
    main()
