import ollama
import sys
from datetime import date
from ollama import Options
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

# ============================================================================
#  THINKING (REASONING) ON / OFF  <-- change this one line
#
#    THINK = True    the model reasons first: you see its thinking, then the
#                    answer (slower, often better)
#    THINK = False   straight to the answer (much faster)
#
#  Or leave it and switch it off from the command line:
#    python ai_astrology.py --no-think
# ============================================================================
THINK = True
if "--no-think" in sys.argv:
    THINK = False


def main():
    today = date.today().strftime('%A, %d-%m-%Y')
    LLM = "qwen3.5:4b"

    print(f"Thinking is {'ON' if THINK else 'OFF'} (change THINK at the top of ai_astrology.py, or run with --no-think)\n")
    name = input("Enter your name: ")
    star_sign = input("Enter your star sign: ")

    system_prompt = """You are an AI astrology assistant called Maude. Provide a short but interesting, positive and
        optimistic horoscope for tomorrow. Provide the response in Markdown format.
        Remember, the user is looking for a positive and optimistic outlook on their future.
        Use British English, metric and EU date formats where applicable."""

    instruction = f"Please provide a horoscope for {name} whose star sign is {star_sign}. Today's date is {today}."

    response = ollama.chat(
        model=LLM, stream=False,
        think=THINK,  # ← thinking on/off: see THINK at the top
        messages=[{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': instruction}],
        options=Options(temperature=0.8, num_ctx=4096, top_p=0.95, top_k=40, num_predict=-1),
    )

    console = Console()

    if not isinstance(response, ollama.ChatResponse):   # stream=True: a generator of chunks
        console.print("[bold magenta]✨ Your Horoscope:[/bold magenta]")
        text = ""
        with Live(Markdown(text), console=console, refresh_per_second=10) as live:
            for chunk in response:
                text += chunk.message.content or ""
                live.update(Markdown(text))
        return

    if hasattr(response.message, 'thinking') and response.message.thinking:
        console.print(f"[bold blue]🤔 Maude's Thinking Process:[/bold blue]\n[dim]{response.message.thinking}[/dim]")
        console.print("\n" + "=" * 50 + "\n")

    console.print("[bold magenta]✨ Your Horoscope:[/bold magenta]")
    console.print(Markdown(response.message.content))

if __name__ == "__main__":
    main()
