"""Render a pattern to a .wav file you can play in anything.

    python -m tonematrix.render patterns/pulse.txt out.wav --seconds 8

This is the "output device" for the project: it just calls next_sample()
over and over and writes the results to disk. Provided, do not modify.
"""

import argparse
import sys

from tonematrix.audio import SAMPLE_RATE, write_wav
from tonematrix.matrix import ToneMatrix


def render(matrix, seconds, sample_rate=SAMPLE_RATE):
    """Collect `seconds` worth of samples from a matrix."""
    return [matrix.next_sample() for _ in range(int(seconds * sample_rate))]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Render a tone matrix pattern to WAV.")
    parser.add_argument("pattern", help="text file of '#' and '.', one line per row")
    parser.add_argument("output", nargs="?", default="tonematrix.wav")
    parser.add_argument("--seconds", type=float, default=8.0)
    args = parser.parse_args(argv)

    with open(args.pattern) as src:
        matrix = ToneMatrix.from_text(src.read())

    print(f"{matrix.grid_size}x{matrix.grid_size} matrix, {args.seconds}s:")
    print(matrix.to_text())

    write_wav(args.output, render(matrix, args.seconds))
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
