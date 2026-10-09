"""Slide "Speech to Text (STT)" (Day 1): transcribe a recording with Whisper large-v3-turbo on MLX.
By default it reads the file tts_hello.py wrote. Tip: pass language="en" when you know it,
and don't send silence (Whisper hears it as "Thank you.").

    pip install mlx-audio       # Apple Silicon only
    python day-1/stt_transcribe.py [some.wav]
"""
import sys
from pathlib import Path
from mlx_audio.stt.generate import generate_transcription

HERE = Path(__file__).parent

if __name__ == "__main__":
    result = generate_transcription(
        model="mlx-community/whisper-large-v3-turbo-asr-fp16",
        audio=sys.argv[1] if len(sys.argv) > 1 else str(HERE / "output" / "output_000.wav"),
    )
    print(result.text)
