"""Slide "TTS in true style" (Day 1): clone a voice from a short recording with Chatterbox-Turbo on MLX.
The reference is day-1/data/morgan-freeman-voice-sample.wav; pass any 5-15 s WAV to clone another voice
(day-1/data/roosevelt-voice-sample.wav is Theodore Roosevelt in 1912, public domain).
Only clone a voice with its owner's consent. Writes day-1/output/morgan_000.wav and plays it.

    pip install mlx-audio       # Apple Silicon only
    python day-1/tts_clone.py [reference.wav]
"""
import sys
from pathlib import Path
from mlx_audio.tts.generate import generate_audio

HERE = Path(__file__).parent

if __name__ == "__main__":
    generate_audio(
        text="""Hello, fellow travellers.
        You're here to learn how machines find their voice,
        and how they listen. It's a curious thing, teaching
        silicon to speak. But every great journey begins
        with a single, well-chosen word. Welcome.""",
        model="mlx-community/chatterbox-turbo-fp16",
        ref_audio=sys.argv[1] if len(sys.argv) > 1 else str(HERE / "data" / "morgan-freeman-voice-sample.wav"),
        output_path=str(HERE / "output"),
        file_prefix="morgan",
        audio_format="wav",
        play=True,
    )
