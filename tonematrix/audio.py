"""Audio plumbing. Provided, do not modify.

The only things you need to understand here are:

  * SAMPLE_RATE - how many samples per second the "speakers" expect.
  * write_wav() - dumps a list of samples to a .wav file you can play.

"""

import wave

# Number of samples per second of audio.
SAMPLE_RATE = 44100

# How many samples elapse between column plucks. 8192 = 2**13, which at
# 44.1kHz works out to about 5.4 columns per second.
SAMPLES_PER_COLUMN = 8192


def clip(sample):
    """Clamp a sample into the range [-1.0, +1.0]."""
    if sample > 1.0:
        return 1.0
    if sample < -1.0:
        return -1.0
    return sample


def write_wav(path, samples, sample_rate=SAMPLE_RATE):
    """Write an iterable of floats in [-1, 1] to a 16-bit mono WAV file."""
    frames = bytearray()
    for sample in samples:
        value = int(clip(sample) * 32767)
        frames += value.to_bytes(2, "little", signed=True)

    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(bytes(frames))


def read_wav(path):
    """Read a 16-bit mono WAV file back into a list of floats."""
    with wave.open(str(path), "rb") as src:
        raw = src.readframes(src.getnframes())
    return [
        int.from_bytes(raw[i:i + 2], "little", signed=True) / 32767.0
        for i in range(0, len(raw), 2)
    ]
