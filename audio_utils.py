"""Converts any audio format to 16 kHz mono WAV using ffmpeg or afconvert."""

import shutil
import subprocess
import tempfile
from pathlib import Path


def to_wav_16k(input_path: Path) -> Path:
    """Convert *input_path* to a 16 kHz mono WAV and return the temp file path.

    Tries ffmpeg first; falls back to macOS afconvert if ffmpeg is absent.
    The caller is responsible for deleting the returned file when done.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    output = Path(tmp.name)

    if shutil.which("ffmpeg"):
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(input_path),
             "-ar", "16000", "-ac", "1", "-f", "wav", str(output)],
            capture_output=True,
        )
        if result.returncode == 0:
            return output
        output.unlink(missing_ok=True)
        raise RuntimeError(
            f"ffmpeg failed to convert {input_path}:\n"
            + result.stderr.decode(errors="replace")
        )

    if shutil.which("afconvert"):
        # macOS built-in audio converter
        result = subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1",
             str(input_path), str(output)],
            capture_output=True,
        )
        if result.returncode == 0:
            return output
        output.unlink(missing_ok=True)
        raise RuntimeError(
            f"afconvert failed to convert {input_path}:\n"
            + result.stderr.decode(errors="replace")
        )

    output.unlink(missing_ok=True)
    raise RuntimeError(
        "No audio converter found. Install ffmpeg:\n"
        "  brew install ffmpeg        # macOS\n"
        "  sudo apt install ffmpeg    # Ubuntu/Debian"
    )
