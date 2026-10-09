"""Slide "Simple Code (presenter’s MLX version)" (Day 1): eight quick questions, in six languages,
to LiquidAI's LFM2.5-1.2B on Apple Silicon. Greedy decoding, so the answers are the same every run.

    pip install mlx-lm          # Apple Silicon only
    python day-1/mlx_quick_test.py
"""
import os
import time
from mlx_lm import load, stream_generate
from mlx_lm.sample_utils import make_sampler

# LM Studio's copy if you have it, otherwise downloaded from Hugging Face (~1.3 GB)
LOCAL = os.path.expanduser("~/.lmstudio/models/LiquidAI/LFM2.5-1.2B-Instruct-MLX-8bit")
MODEL = LOCAL if os.path.isdir(LOCAL) else "LiquidAI/LFM2.5-1.2B-Instruct-MLX-8bit"
SYSTEM = "Answer in English only. Give just the short, final answer with no explanation."

model, tok = load(MODEL)
greedy = make_sampler(temp=0.0)  # deterministic: same answers every run


def ask(question):
    prompt = tok.apply_chat_template(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}],
        add_generation_prompt=True, tokenize=False)
    start, answer = time.time(), ""
    for r in stream_generate(model, tok, prompt, max_tokens=128, sampler=greedy):
        answer += r.text
    return answer.strip().split("\n")[0], (time.time() - start) * 1000  # first line only


questions = [
    "Which British king abdicated in 1936?",
    "Wann war das erste Oktoberfest?",
    "¿Dónde nació Salvador Dalí?",
    "Lequel des deux est le plus ancien, la Tour Eiffel ou le Sacré-Cœur ?",
    "什么是爱因斯坦最著名的方程式？",
    "ما هي عاصمة مصر؟",
    "Write one line of Java code that prints Hello World to the console.",
    "What is the derivative of 6x^2-5x+12?",
]

if __name__ == "__main__":
    ask("Hi")  # warm up so the first timing is fair
    for q in questions:
        answer, ms = ask(q)
        print(f"{q}\n  -> {answer}  ({ms:.0f} ms)\n")
