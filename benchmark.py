"""Starting point for the Part 4 measurements.

    python benchmark.py
    python benchmark.py --impl optimized

It reports how long it takes to render one full pass of the playhead, at
several grid sizes and pattern densities, against how long that audio would
take to play. A ratio below 1.0 means your sequencer cannot keep up with the
speakers.

Extend this. The numbers it prints out of the box are a baseline, not an
answer: you will want to isolate the operation your extension actually
changes (mixing, or pluck_column, or editing) rather than timing everything
at once.
"""

import argparse
import random
import time

from tonematrix.audio import SAMPLE_RATE, SAMPLES_PER_COLUMN


def load(name):
    if name == "optimized":
        from tonematrix.optimized import ToneMatrix
    else:
        from tonematrix.matrix import ToneMatrix
    return ToneMatrix


def fill(matrix, density, seed=6767):
    rng = random.Random(seed)
    n = matrix.grid_size
    for row in range(n):
        for col in range(n):
            if rng.random() < density:
                matrix.set_cell(row, col, True)


def time_one_pass(ToneMatrix, size, density):
    matrix = ToneMatrix(size)
    fill(matrix, density)

    total = size * SAMPLES_PER_COLUMN
    start = time.perf_counter()
    for _ in range(total):
        matrix.next_sample()
    elapsed = time.perf_counter() - start

    audio_seconds = total / SAMPLE_RATE
    return elapsed, audio_seconds, total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--impl", default="matrix", choices=["matrix", "optimized"])
    parser.add_argument("--sizes", type=int, nargs="+", default=[8, 16, 32, 64])
    parser.add_argument("--densities", type=float, nargs="+", default=[0.05, 0.25])
    args = parser.parse_args()

    ToneMatrix = load(args.impl)

    print(f"{'size':>6} {'density':>8} {'samples':>10} {'seconds':>9} "
          f"{'μs/sample':>10} {'x realtime':>11}")
    for size in args.sizes:
        for density in args.densities:
            elapsed, audio, total = time_one_pass(ToneMatrix, size, density)
            print(f"{size:>6} {density:>8.2f} {total:>10} {elapsed:>9.3f} "
                  f"{1e6 * elapsed / total:>10.3f} {audio / elapsed:>11.2f}")


if __name__ == "__main__":
    main()
