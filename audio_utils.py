"""
audio_utils.py
Handles the audio side of the pipeline:

    AAC/MP3/M4A  --(ffmpeg)-->  WAV  --(Whisper)-->  Text

Whisper is loaded lazily (once) and cached so the Streamlit app doesn't
reload the model on every interaction.
"""

import subprocess
import tempfile
import os

import imageio_ffmpeg
from faster_whisper import WhisperModel

_MODEL_CACHE = {}


def convert_to_wav(input_path: str) -> str:
    """Converts any audio file ffmpeg supports into a 16kHz mono WAV file.
    Returns the path to the new WAV file (in a temp directory).

    Uses imageio-ffmpeg's bundled FFmpeg binary, so this works even if
    FFmpeg isn't installed system-wide or isn't on the PATH.
    """
    output_path = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    command = [
        ffmpeg_exe,
        "-y",  # overwrite output if it exists
        "-i", input_path,
        "-ar", "16000",  # 16kHz sample rate, what Whisper expects
        "-ac", "1",  # mono
        output_path,
    ]

    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg failed to convert audio.\n"
            f"stderr:\n{result.stderr}"
        )

    return output_path


def get_whisper_model(model_size: str = "base"):
    """Loads (and caches) a faster-whisper model. Model sizes: tiny, base, small, medium, large-v3.
    'base' is a good speed/accuracy tradeoff for a first working version.
    Runs on CPU with int8 quantization by default, which needs no GPU/CUDA setup.
    """
    if model_size not in _MODEL_CACHE:
        _MODEL_CACHE[model_size] = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _MODEL_CACHE[model_size]


def transcribe_audio(wav_path: str, model_size: str = "base") -> str:
    """Transcribes a WAV file to text using faster-whisper.

    vad_filter=True trims silence/near-silence before transcribing, which
    avoids Whisper hallucinating filler words (like "You" or "Thank you.")
    on quiet recordings. The threshold is lowered from the default (0.5)
    to be more lenient, since different browsers (e.g. Chrome vs Edge)
    encode microphone audio at different gain/loudness levels — a stricter
    threshold was incorrectly treating quieter Chrome recordings as
    silence. language="en" skips language auto-detection, which is
    faster and more reliable for short clips.
    """
    model = get_whisper_model(model_size)
    segments, _info = model.transcribe(
        wav_path,
        language="en",
        vad_filter=True,
        vad_parameters=dict(
            threshold=0.25,              # lower = more lenient (default is 0.5)
            min_silence_duration_ms=700,
            speech_pad_ms=300,
        ),
    )
    return " ".join(segment.text.strip() for segment in segments).strip()


def process_audio_file(input_path: str, model_size: str = "base") -> str:
    """Full pipeline: any audio format -> WAV -> transcribed text.
    Cleans up the intermediate WAV file afterward.
    """
    wav_path = convert_to_wav(input_path)
    try:
        text = transcribe_audio(wav_path, model_size=model_size)
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)
    return text
