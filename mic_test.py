import time
import numpy as np
import sounddevice as sd


SAMPLE_RATE = 48000
CHANNELS = 1
BLOCKSIZE = 2048


def rms(audio):
    audio = np.asarray(audio, dtype=np.float32)

    if audio.size == 0:
        return 0.0

    return float(
        np.sqrt(np.mean(np.square(audio)))
    )


print()
print("=" * 70)
print("             NOVA MICROPHONE DIAGNOSTIC")
print("=" * 70)
print()

print("INPUT DEVICES:")
print()

devices = sd.query_devices()

input_devices = []

for index, device in enumerate(devices):

    inputs = int(
        device.get(
            "max_input_channels",
            0
        )
    )

    if inputs > 0:

        input_devices.append(index)

        print(
            f"[{index}] "
            f"{device['name']} "
            f"| inputs={inputs} "
            f"| default_rate={device['default_samplerate']}"
        )

print()
print("=" * 70)
print()

default_input = sd.default.device[0]

print(
    f"Windows/Python default input device: "
    f"{default_input}"
)

if default_input is not None:
    try:
        print(
            "Default input name:",
            sd.query_devices(
                default_input
            )["name"]
        )
    except Exception:
        pass

print()
print("=" * 70)
print()

print(
    "Speak normally for about 5 seconds."
)

print(
    "Say: "
    "'Nova, this is a microphone test.'"
)

print()

input(
    "Press ENTER when you are ready..."
)

print()
print(
    "RECORDING..."
)
print()

levels = []

try:

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        blocksize=BLOCKSIZE,
        device=default_input,
    ) as stream:

        start = time.monotonic()

        while (
            time.monotonic() - start
            < 5.0
        ):

            data, overflowed = (
                stream.read(BLOCKSIZE)
            )

            audio = data[:, 0]

            level = rms(audio)

            levels.append(level)

            print(
                f"\rRMS: {level:.6f}",
                end="",
                flush=True
            )

            if overflowed:
                print(
                    "\nWARNING: input overflow"
                )

except Exception as exc:

    print()
    print()
    print(
        "MICROPHONE ERROR:"
    )
    print(exc)
    raise SystemExit(1)

print()
print()
print("=" * 70)
print(
    "MICROPHONE TEST COMPLETE"
)
print("=" * 70)
print()

if levels:

    minimum = min(levels)
    maximum = max(levels)
    average = sum(levels) / len(levels)

    print(
        f"Minimum RMS : {minimum:.6f}"
    )

    print(
        f"Average RMS : {average:.6f}"
    )

    print(
        f"Maximum RMS : {maximum:.6f}"
    )

    print()

    if maximum < 0.0005:

        print(
            "RESULT: VERY LOW / NO MICROPHONE SIGNAL"
        )

    elif maximum < 0.002:

        print(
            "RESULT: VERY QUIET MICROPHONE SIGNAL"
        )

    elif maximum < 0.01:

        print(
            "RESULT: NORMAL-LOW MICROPHONE SIGNAL"
        )

    else:

        print(
            "RESULT: STRONG MICROPHONE SIGNAL"
        )

print()