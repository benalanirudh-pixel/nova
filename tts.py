"""Nova/JARVIS text-to-speech engine using Piper TTS.

Windows-only playback is intentional for this project.
Piper generates a WAV file and winsound plays it synchronously.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import winsound


BASE_DIR = Path(__file__).resolve().parent
VOICE_DIR = BASE_DIR / "voices"
VOICE_NAME = "en_US-lessac-high"

# Protect audio playback from overlapping calls.
_AUDIO_LOCK = threading.Lock()


class TTSError(Exception):
    """A user-readable text-to-speech error."""


def _validate_voice() -> Path:
    """Confirm that the downloaded Piper voice exists."""
    model = VOICE_DIR / f"{VOICE_NAME}.onnx"
    config = VOICE_DIR / f"{VOICE_NAME}.onnx.json"

    if not model.exists():
        raise TTSError(
            f"Piper voice model is missing: {model}. "
            f"Download it with: "
            f"python -m piper.download_voices {VOICE_NAME} "
            f"--data-dir voices"
        )

    if not config.exists():
        raise TTSError(f"Piper voice configuration is missing: {config}")

    return model


def speak(text: str) -> None:
    """Generate speech with Piper and play it synchronously."""
    text = str(text or "").strip()

    if not text:
        return

    _validate_voice()

    # Only one speech output at a time.
    with _AUDIO_LOCK:
        wav_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                prefix="nova_tts_",
                suffix=".wav",
                dir=BASE_DIR,
                delete=False,
            ) as temp:
                wav_path = Path(temp.name)

            # Use the exact Python interpreter running this project.
            # This prevents the global-Python / venv mismatch we just fixed.
            command = [
                sys.executable,
                "-m",
                "piper",
                "-m",
                VOICE_NAME,
                "--data-dir",
                str(VOICE_DIR),
                "-f",
                str(wav_path),
                "--",
                text,
            ]

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                error = result.stderr.strip() or result.stdout.strip()
                raise TTSError(
                    f"Piper failed with exit code {result.returncode}: {error}"
                )

            if not wav_path.exists() or wav_path.stat().st_size == 0:
                raise TTSError("Piper produced no audio output.")

            # Synchronous playback.
            # JARVIS won't start listening while it is still speaking.
            winsound.PlaySound(
                str(wav_path),
                winsound.SND_FILENAME,
            )

        except subprocess.TimeoutExpired:
            raise TTSError("Piper took too long to generate the response.")

        except OSError as exc:
            raise TTSError(f"Audio playback failed: {exc}")

        finally:
            if wav_path is not None:
                try:
                    if wav_path.exists():
                        wav_path.unlink()
                except OSError:
                    # Windows may briefly hold the file after playback.
                    pass


def test_voice() -> None:
    """Standalone voice test."""
    speak(
        "Hello Anirudh. I am Jarvis. "
        "My voice system is operational."
    )


if __name__ == "__main__":
    try:
        print("Testing Nova voice...")
        speak(
            "Hello Anirudh. I am Jarvis. "
            "My voice system is operational."
        )
        print("Voice test completed.")
    except TTSError as exc:
        print(f"TTS ERROR: {exc}")