"""Slide "Text to Speech (TTS)" (Day 1): the smallest possible TTS call, with Chatterbox-Turbo (~3 GB) on MLX.
Writes day-1/output/output_000.wav and plays it. stt_transcribe.py turns it back into text.

    pip install mlx-audio       # Apple Silicon only
    python day-1/tts_hello.py ["Some other text"]
"""
import sys
from pathlib import Path
from mlx_audio.tts.generate import generate_audio

HERE = Path(__file__).parent

if __name__ == "__main__":
    generate_audio(
        text=sys.argv[1] if len(sys.argv) > 1 else "Hello World",
        model="mlx-community/chatterbox-turbo-fp16",
        output_path=str(HERE / "output"),
        file_prefix="output",
        audio_format="wav",
        play=True,
    )
