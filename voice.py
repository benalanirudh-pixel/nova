"""
Nova Voice System
=================

Features:
- Local Faster-Whisper STT
- Adaptive microphone noise detection
- Natural speech start/end detection
- Wake phrase activation
- Persistent active conversation session
- No wake word required while active
- "Bye Nova" / "See you Nova" deactivation
- CPU-friendly Faster-Whisper configuration
- No temporary audio files required for transcription

Session flow:

    INACTIVE
        |
        | "Hi Nova"
        v
    ACTIVE
        |
        | normal commands
        | normal commands
        | normal commands
        v
    "Bye Nova"
        |
        v
    INACTIVE
"""

from __future__ import annotations

import re
import wave
from collections import deque
from pathlib import Path

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel


# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

STT_DIR = BASE_DIR / "stt_models"

LOCAL_MODEL_ROOT = (
    STT_DIR / "models--systran--faster-whisper-small"
)

# ------------------------------------------------------------
# Audio
# ------------------------------------------------------------

SAMPLE_RATE = 48000
WHISPER_SAMPLE_RATE = 16000

CHANNELS = 1
DTYPE = "float32"

MICROPHONE_NAME = "Microphone Array"

# About 42.7 ms at 48 kHz.
BLOCK_SIZE = 2048

# Silence required before an utterance is considered finished.
SILENCE_SECONDS = 1.0

# Minimum real speech duration.
MIN_SPEECH_SECONDS = 0.30

# How long Nova waits for speech.
WAKE_WAIT_SECONDS = 30.0
COMMAND_WAIT_SECONDS = 30.0

# Safety limits.
WAKE_MAX_SECONDS = 20.0
SAFETY_MAX_SECONDS = 120.0

# Audio immediately before speech begins.
PRE_ROLL_SECONDS = 0.35

# ------------------------------------------------------------
# Speech detection
# ------------------------------------------------------------

START_THRESHOLD = 0.003
END_THRESHOLD = 0.002

START_MULT = 3.0
END_MULT = 1.8

START_BLOCKS = 2

# ------------------------------------------------------------
# Whisper
# ------------------------------------------------------------

WHISPER_DEVICE = "cpu"
COMPUTE_TYPE = "int8"
LANGUAGE = "en"

BEAM_SIZE = 5
WAKE_BEAM_SIZE = 3

INITIAL_PROMPT = (
    "Nova. Anirudh. "
    "Open Chrome. Open YouTube. "
    "Search the web. Go to TradingView. "
    "Hi Nova. Hey Nova. Hello Nova. "
    "Bye Nova. Goodbye Nova. "
    "See you Nova. See ya Nova."
)

# ------------------------------------------------------------
# Activation
# ------------------------------------------------------------

WAKE_ALIASES = {
    "nova",
}

WAKE_WORD = "nova"

# ------------------------------------------------------------
# Deactivation
# ------------------------------------------------------------

DEACTIVATION_PHRASES = {
    "bye nova",
    "goodbye nova",
    "good bye nova",
    "see you nova",
    "see ya nova",
    "talk to you later nova",
}

# Debug
DEBUG_IGNORED = True


# ============================================================
# GLOBALS
# ============================================================

_whisper_model: WhisperModel | None = None

_mic_config: tuple[int, int] | None = None

_noise = 0.002


# ============================================================
# ERRORS
# ============================================================

class VoiceError(Exception):
    """User-readable voice-system error."""
    pass


# ============================================================
# WHISPER
# ============================================================

def find_local_model() -> Path:
    if not LOCAL_MODEL_ROOT.exists():
        raise VoiceError(
            f"Local Whisper model not found:\n"
            f"{LOCAL_MODEL_ROOT}"
        )

    snapshots = LOCAL_MODEL_ROOT / "snapshots"

    if not snapshots.exists():
        raise VoiceError(
            "Whisper snapshots directory is missing."
        )

    folders = [
        p for p in snapshots.iterdir()
        if p.is_dir()
    ]

    if not folders:
        raise VoiceError(
            "No Whisper model snapshot found."
        )

    folders.sort(
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    model = folders[0]

    if not (model / "model.bin").exists():
        raise VoiceError(
            f"Whisper model.bin not found:\n{model}"
        )

    return model


def load_whisper() -> WhisperModel:
    global _whisper_model

    if _whisper_model is not None:
        return _whisper_model

    model_path = find_local_model()

    print("[VOICE] Loading Whisper...")

    try:
        _whisper_model = WhisperModel(
            str(model_path),
            device=WHISPER_DEVICE,
            compute_type=COMPUTE_TYPE,
        )
    except Exception as exc:
        raise VoiceError(
            f"Whisper failed to load: {exc}"
        ) from exc

    print("[VOICE] Whisper ready.")

    return _whisper_model


# ============================================================
# MICROPHONE
# ============================================================

def _candidate_devices() -> list[int]:
    """Return input devices with preferred microphone first."""

    preferred: list[int] = []
    others: list[int] = []

    for index, device in enumerate(sd.query_devices()):

        if int(device.get("max_input_channels", 0)) <= 0:
            continue

        name = str(device.get("name", ""))

        if MICROPHONE_NAME.lower() in name.lower():
            preferred.append(index)
        else:
            others.append(index)

    return preferred + others


def find_microphone() -> int:
    devices = _candidate_devices()

    if not devices:
        raise VoiceError(
            "No microphone input device found."
        )

    return devices[0]


def get_microphone() -> int:
    if _mic_config is not None:
        return _mic_config[0]

    return find_microphone()


def _all_attempts() -> list[tuple[int, int]]:
    attempts: list[tuple[int, int]] = []

    for device in _candidate_devices():

        rates = [SAMPLE_RATE]

        try:
            default_rate = int(
                sd.query_devices(device)["default_samplerate"]
            )

            if default_rate not in rates:
                rates.append(default_rate)

        except Exception:
            pass

        attempts.extend(
            (device, rate)
            for rate in rates
        )

    return attempts


def _try_open(attempts):
    """
    Return:

        stream,
        rate,
        config,
        last_error
    """

    last_error = None

    for device, rate in attempts:

        stream = None

        try:
            stream = sd.InputStream(
                samplerate=rate,
                channels=CHANNELS,
                dtype=DTYPE,
                device=device,
                blocksize=BLOCK_SIZE,
            )

            stream.start()

            return (
                stream,
                rate,
                (device, rate),
                None,
            )

        except Exception as exc:

            last_error = exc

            if stream is not None:

                try:
                    stream.close()
                except Exception:
                    pass

    return None, 0, None, last_error


def _open_stream():
    """
    Open microphone and remember a configuration that works.
    """

    global _mic_config

    if _mic_config is not None:

        stream, rate, cfg, _ = _try_open(
            [_mic_config]
        )

        if stream is not None:
            return stream, rate

        _mic_config = None

    stream, rate, cfg, error = _try_open(
        _all_attempts()
    )

    if stream is None:
        raise VoiceError(
            f"Could not open microphone: {error}\n"
            "Check Windows Settings > Privacy & security > "
            "Microphone and allow desktop apps."
        )

    _mic_config = cfg

    return stream, rate


def _close_stream(stream) -> None:

    for action in (
        stream.stop,
        stream.close,
    ):

        try:
            action()

        except Exception:
            pass


# ============================================================
# AUDIO HELPERS
# ============================================================

def rms(audio: np.ndarray) -> float:

    if audio.size == 0:
        return 0.0

    audio = np.asarray(
        audio,
        dtype=np.float32,
    )

    return float(
        np.sqrt(np.mean(audio * audio))
    )


def _resample(
    audio: np.ndarray,
    src: int,
    dst: int,
) -> np.ndarray:

    audio = np.asarray(
        audio,
        dtype=np.float32,
    )

    if src == dst or audio.size == 0:
        return audio

    # Efficient path for 48 kHz -> 16 kHz.
    if src % dst == 0:

        k = src // dst

        n = (
            audio.size // k
        ) * k

        return (
            audio[:n]
            .reshape(-1, k)
            .mean(axis=1)
            .astype(np.float32)
        )

    n = int(
        audio.size * dst / src
    )

    old = np.linspace(
        0,
        1,
        audio.size,
        endpoint=False,
    )

    new = np.linspace(
        0,
        1,
        n,
        endpoint=False,
    )

    return np.interp(
        new,
        old,
        audio,
    ).astype(np.float32)


def _adapt_noise(level: float) -> None:
    """
    Follow room noise.

    Noise decreases quickly and increases slowly so normal
    speech doesn't accidentally raise the threshold too much.
    """

    global _noise

    if level < _noise:
        _noise = (
            0.8 * _noise
            + 0.2 * level
        )

    else:
        _noise = (
            0.995 * _noise
            + 0.005 * level
        )

    _noise = max(
        _noise,
        0.0003,
    )


def calibrate_noise(
    seconds: float = 1.0,
) -> float:

    global _noise

    stream, rate = _open_stream()

    levels: list[float] = []

    peak = 0.0

    try:

        blocks = max(
            1,
            int(
                seconds * rate / BLOCK_SIZE
            ),
        )

        for _ in range(blocks):

            try:
                data, _overflow = stream.read(
                    BLOCK_SIZE
                )

            except Exception as exc:

                raise VoiceError(
                    f"Microphone read failed: {exc}"
                ) from exc

            block = np.asarray(
                data[:, 0],
                dtype=np.float32,
            )

            level = rms(block)

            levels.append(level)

            peak = max(
                peak,
                float(np.max(np.abs(block))),
            )

    finally:
        _close_stream(stream)

    if peak == 0.0:

        raise VoiceError(
            "The microphone returns pure silence. "
            "Check Windows microphone permissions "
            "and the selected input device."
        )

    _noise = float(
        np.clip(
            np.percentile(levels, 25),
            0.0003,
            0.02,
        )
    )

    return _noise


# ============================================================
# NATURAL UTTERANCE CAPTURE
# ============================================================

def _capture(
    read_block,
    rate: int,
    wait_seconds: float,
    max_seconds: float,
):
    """
    Detect one complete natural utterance.

    Starts when speech rises above adaptive room noise.

    Ends after SILENCE_SECONDS.

    Returns:
        float32 audio
        or None
    """

    global _noise

    block_s = BLOCK_SIZE / rate

    pre = deque(
        maxlen=max(
            1,
            int(
                PRE_ROLL_SECONDS / block_s
            ),
        )
    )

    captured: list[np.ndarray] = []

    silence_limit = max(
        1,
        round(
            SILENCE_SECONDS / block_s
        ),
    )

    max_blocks = int(
        max_seconds / block_s
    )

    started = False

    start_run = 0
    silent_blocks = 0
    speech_blocks = 0
    waited_blocks = 0

    while True:

        audio = read_block()

        level = rms(audio)

        start_thr = max(
            _noise * START_MULT,
            START_THRESHOLD,
        )

        end_thr = max(
            _noise * END_MULT,
            END_THRESHOLD,
        )

        # ----------------------------------------------------
        # Waiting for speech
        # ----------------------------------------------------

        if not started:

            pre.append(audio)

            waited_blocks += 1

            if level >= start_thr:

                start_run += 1

                if start_run >= START_BLOCKS:

                    started = True

                    captured = list(pre)

                    pre.clear()

                    speech_blocks = start_run

                    silent_blocks = 0

            else:

                start_run = 0

                _adapt_noise(level)

            if (
                not started
                and waited_blocks * block_s
                >= wait_seconds
            ):
                return None

            continue

        # ----------------------------------------------------
        # Inside utterance
        # ----------------------------------------------------

        captured.append(audio)

        if level >= end_thr:

            silent_blocks = 0

            speech_blocks += 1

        else:

            silent_blocks += 1

            if silent_blocks >= silence_limit:
                break

        # ----------------------------------------------------
        # Safety limit
        # ----------------------------------------------------

        if len(captured) >= max_blocks:

            _noise = max(
                _noise,
                rms(
                    np.concatenate(
                        captured[-10:]
                    )
                ),
            )

            return None

    if (
        speech_blocks * block_s
        < MIN_SPEECH_SECONDS
    ):
        return None

    return np.concatenate(captured)


def record_utterance(
    wait_seconds: float,
    max_seconds: float = SAFETY_MAX_SECONDS,
) -> np.ndarray | None:
    """
    Capture one natural utterance.

    Returned audio is always at SAMPLE_RATE.
    """

    stream, rate = _open_stream()

    def read_block() -> np.ndarray:

        try:

            data, _overflow = stream.read(
                BLOCK_SIZE
            )

        except Exception as exc:

            raise VoiceError(
                f"Microphone read failed: {exc}"
            ) from exc

        return np.asarray(
            data[:, 0],
            dtype=np.float32,
        ).copy()

    try:

        audio = _capture(
            read_block,
            rate,
            wait_seconds,
            max_seconds,
        )

    finally:

        _close_stream(stream)

    if audio is None:
        return None

    return _resample(
        audio,
        rate,
        SAMPLE_RATE,
    )


# ============================================================
# WAV
# ============================================================

def write_wav(
    audio: np.ndarray,
    path: Path,
) -> None:

    audio = np.clip(
        np.asarray(
            audio,
            dtype=np.float32,
        ),
        -1.0,
        1.0,
    )

    pcm = (
        audio * 32767
    ).astype(np.int16)

    with wave.open(
        str(path),
        "wb",
    ) as wav:

        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)

        wav.writeframes(
            pcm.tobytes()
        )


# ============================================================
# TEXT HELPERS
# ============================================================

def normalize_words(
    text: str,
) -> list[str]:

    return re.findall(
        r"[a-zA-Z]+",
        str(text or "").lower(),
    )


_WAKE_RE = re.compile(
    r"\b(?:"
    + "|".join(
        re.escape(w)
        for w in sorted(
            WAKE_ALIASES
        )
    )
    + r")\b",
    re.I,
)

_PUNCT = (
    " \t\r\n,.;:!?-"
    "\u2013"
    "\u2014"
    "\"'"
)

_FILLERS = re.compile(
    r"\b(?:hey|hi|hello|ok|okay|yo)\b",
    re.I,
)


def contains_exact_wake_word(
    text: str,
) -> bool:

    return bool(
        _WAKE_RE.search(
            str(text or "")
        )
    )


def remove_wake_word(
    text: str,
) -> str:
    """
    Remove Nova from an activation phrase.

    Examples:

        "Nova, what's the weather?"
            -> "what's the weather"

        "Open Chrome, Nova."
            -> "Open Chrome"

        "Hey Nova"
            -> ""
    """

    text = str(text or "")

    match = _WAKE_RE.search(text)

    if not match:
        return ""

    after = text[
        match.end():
    ].strip(_PUNCT)

    if after:
        return after

    before = _FILLERS.sub(
        " ",
        text[:match.start()],
    )

    return " ".join(
        before
        .strip(_PUNCT)
        .split()
    )


def contains_deactivation_phrase(
    text: str,
) -> bool:
    """
    Detect session-ending phrases.

    Examples:

        Bye Nova
        Goodbye Nova
        See you Nova
        See ya Nova
    """

    words = normalize_words(text)

    if not words:
        return False

    normalized = " ".join(words)

    return normalized in DEACTIVATION_PHRASES


def is_deactivation_command(
    text: str,
) -> bool:

    return contains_deactivation_phrase(text)


# ============================================================
# WHISPER PROMPT PROTECTION
# ============================================================

_PROMPT_WORDS = normalize_words(
    INITIAL_PROMPT
)


def _is_prompt_echo(
    text: str,
) -> bool:

    words = normalize_words(text)

    n = len(words)

    if n < 2:
        return False

    # Whisper starts repeating the initial prompt.
    if words == _PROMPT_WORDS[:n]:
        return True

    # Long slice of prompt.
    if n >= 4:

        return any(
            _PROMPT_WORDS[i:i + n]
            == words

            for i in range(
                len(_PROMPT_WORDS) - n + 1
            )
        )

    return False


# ============================================================
# TRANSCRIPTION
# ============================================================

def transcribe(
    audio: np.ndarray,
    beam_size: int | None = None,
) -> str:
    """
    Audio at 48 kHz -> Whisper -> text.
    """

    if audio.size == 0:
        return ""

    model = load_whisper()

    audio16 = _resample(
        audio,
        SAMPLE_RATE,
        WHISPER_SAMPLE_RATE,
    )

    peak = float(
        np.max(
            np.abs(audio16)
        )
    )

    # Quiet laptop microphone normalization.
    if 0 < peak < 0.5:

        audio16 = (
            audio16
            * (0.5 / peak)
        )

    try:

        segments, _ = model.transcribe(
            audio16,
            language=LANGUAGE,
            beam_size=(
                beam_size
                or BEAM_SIZE
            ),
            vad_filter=True,
            condition_on_previous_text=False,
            temperature=0.0,
            initial_prompt=INITIAL_PROMPT,
        )

        parts = []

        for segment in segments:

            if (
                segment.no_speech_prob > 0.6
                and segment.avg_logprob < -1.0
            ):
                continue

            text = segment.text.strip()

            if text:
                parts.append(text)

    except Exception as exc:

        raise VoiceError(
            f"Transcription failed: {exc}"
        ) from exc

    result = " ".join(parts).strip()

    if _is_prompt_echo(result):
        return ""

    return result


# ============================================================
# STARTUP
# ============================================================

def prepare() -> None:
    """
    Call once when Nova starts.
    """

    load_whisper()

    level = calibrate_noise()

    threshold = max(
        level * START_MULT,
        START_THRESHOLD,
    )

    print(
        f"[VOICE] Room noise {level:.4f}, "
        f"speech threshold {threshold:.4f}"
    )


# ============================================================
# INACTIVE MODE
# ============================================================

def listen_for_wake_word() -> str:
    """
    INACTIVE MODE.

    Nova listens for one utterance and only returns it
    when the wake word is present.
    """

    audio = record_utterance(
        WAKE_WAIT_SECONDS,
        WAKE_MAX_SECONDS,
    )

    if audio is None:
        return ""

    text = transcribe(
        audio,
        beam_size=WAKE_BEAM_SIZE,
    )

    if not text:
        return ""

    if not contains_exact_wake_word(text):

        if DEBUG_IGNORED:
            print(
                f"[VOICE] ignored (no wake word): {text}"
            )

        return ""

    return text


# ============================================================
# ACTIVE MODE
# ============================================================

def listen_for_active_command() -> str:
    """
    ACTIVE MODE.

    Listen for a normal command.

    NO wake word required.
    """

    audio = record_utterance(
        COMMAND_WAIT_SECONDS,
        SAFETY_MAX_SECONDS,
    )

    if audio is None:
        return ""

    text = transcribe(audio)

    if not text:
        return ""

    return text.strip()


def listen_for_command() -> str:
    """
    Backward-compatible alias.

    While Nova is active, this is equivalent to
    listen_for_active_command().
    """

    return listen_for_active_command()


# ============================================================
# SESSION LISTENER
# ============================================================

def listen_for_session_event() -> tuple[str, str]:
    """
    One step of Nova's voice session.

    Returns:

        ("activate", text)
        ("command", text)
        ("deactivate", text)
        ("none", "")

    State is stored internally between calls.
    """

    global _session_active

    if not _session_active:

        text = listen_for_wake_word()

        if not text:
            return "none", ""

        command = remove_wake_word(text)

        _session_active = True

        if command:
            return "command", command

        return "activate", text

    text = listen_for_active_command()

    if not text:
        return "none", ""

    if is_deactivation_command(text):

        _session_active = False

        return "deactivate", text

    return "command", text


# ============================================================
# SESSION STATE
# ============================================================

_session_active = False


def is_active() -> bool:
    """Return whether Nova is currently in active session mode."""

    return _session_active


def activate() -> None:
    """Force Nova into active mode."""

    global _session_active

    _session_active = True


def deactivate() -> None:
    """Force Nova into inactive mode."""

    global _session_active

    _session_active = False


# ============================================================
# LEGACY COMPATIBILITY
# ============================================================

def listen_once(
    seconds: float | None = None,
) -> str:
    """
    Compatibility with older code.

    This listens as an active command.
    """

    _ = seconds

    return listen_for_active_command()


# ============================================================
# DIRECT TEST
# ============================================================

if __name__ == "__main__":

    try:

        print()
        print("=" * 60)
        print("NOVA VOICE SESSION TEST")
        print("=" * 60)
        print()
        print("Say: Hi Nova")
        print()
        print("Once active:")
        print("  - Speak normally")
        print("  - No wake word required")
        print()
        print("To deactivate:")
        print("  - Bye Nova")
        print("  - See you Nova")
        print("  - Goodbye Nova")
        print()

        prepare()

        while True:

            event, text = listen_for_session_event()

            if event == "none":
                continue

            if event == "activate":

                print()
                print("[NOVA] ACTIVATED")
                print("[NOVA] Listening continuously.")

            elif event == "command":

                print(
                    f"[COMMAND] {text}"
                )

            elif event == "deactivate":

                print()
                print("[NOVA] DEACTIVATED")
                print("[NOVA] Waiting for 'Nova'.")

    except KeyboardInterrupt:

        deactivate()

        print()
        print("Voice system stopped.")

    except VoiceError as exc:

        print()
        print(f"VOICE ERROR: {exc}")