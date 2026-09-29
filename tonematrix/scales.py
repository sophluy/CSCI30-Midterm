"""Which pitch belongs to which row. Provided, do not modify.

Row 0 is the *top* row of the matrix and has the highest pitch; row
grid_size-1 is the bottom row and has the lowest pitch. Pitches walk up
an A minor pentatonic scale, which is why almost any pattern you draw
sounds vaguely pleasant: there are no semitone clashes in the scale.
"""

# Semitone offsets of the A minor pentatonic scale, relative to the root.
_PENTATONIC = (0, 3, 5, 7, 10)

# Frequency of the lowest note we use (A2).
_ROOT_HZ = 110.0

# How many octaves the scale spans before it wraps back to the bottom. A
# 16-row matrix uses 20 scale degrees at most, so the wrap only shows up on
# unusually tall grids, where it keeps every string inside the audible range.
_OCTAVES = 4


def frequency_for_row(row, grid_size):
    """Return the frequency in hertz of the string on the given row.

    Rows are numbered from the top, so we flip the index before walking up
    the scale.
    """
    if not 0 <= row < grid_size:
        raise ValueError(f"row {row} out of range for a {grid_size}-row matrix")

    step = grid_size - 1 - row                     # 0 at the bottom row
    octave = (step // len(_PENTATONIC)) % _OCTAVES  # wrap so huge grids stay audible
    semitones = 12 * octave + _PENTATONIC[step % len(_PENTATONIC)]
    return _ROOT_HZ * 2.0 ** (semitones / 12.0)
