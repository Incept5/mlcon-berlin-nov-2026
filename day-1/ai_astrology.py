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

    stream = ollama.chat(
        model=LLM, stream=True,   # stream=True: tokens arrive as they are generated
        think=THINK,  # ← thinking on/off: see THINK at the top
        messages=[{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': instruction}],
        options=Options(temperature=0.8, num_ctx=4096, top_p=0.95, top_k=40, num_predict=-1),
    )
    show(stream, "🤔 Maude's Thinking Process:", "✨ Your Horoscope:")


def show(stream, thinking_title, answer_title):
    """Print the thinking live (grey), then the answer live (rendered as Markdown)."""
    console = Console()
    thinking, answer, live = False, "", None
    for chunk in stream:
        if chunk.message.thinking:                  # reasoning tokens come first
            if not thinking:
                console.print(f"[bold blue]{thinking_title}[/bold blue]")
                thinking = True
            console.print(chunk.message.thinking, style="dim", end="", markup=False, highlight=False)
        if chunk.message.content:                   # then the answer itself
            if live is None:
                if thinking:
                    console.print("\n\n" + "=" * 50 + "\n")
                console.print(f"[bold magenta]{answer_title}[/bold magenta]")
                live = Live(Markdown(""), console=console, refresh_per_second=12, vertical_overflow="visible")
                live.start()
            answer += chunk.message.content
            live.update(Markdown(answer))
    if live:
        live.stop()

if __name__ == "__main__":
    main()
