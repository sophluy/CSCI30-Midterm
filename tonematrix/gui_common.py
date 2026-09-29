"""Colors and playhead tracking shared by both GUIs. Provided, do not modify."""

import time

from tonematrix.audio import SAMPLE_RATE, SAMPLES_PER_COLUMN

BG = "#f4f4f6"
GRID_LINE = "#ffffff"

# Chrome around the grid. These are spelled out rather than left to the
# system theme because a widget toolkit running under a dark desktop theme
# will happily paint light text on the light background set above.
TEXT = "#1f2430"
PANEL = "#ffffff"
BORDER = "#c2c2d0"
MUTED = "#9a9aa8"

CELL_OFF = "#dcdce4"        # unlit cell
CELL_OFF_BEAT = "#c2c2d0"   # unlit cell under the playhead
CELL_ON = "#4c6ef5"         # lit cell, string at rest
CELL_HIT = "#ffffff"        # lit cell, just plucked

COLUMN_SECONDS = SAMPLES_PER_COLUMN / SAMPLE_RATE

# How long a cell takes to fade from CELL_HIT back to CELL_ON.
RING_SECONDS = 0.9

TICK_MS = 33


def blend(start, end, t):
    """Interpolate between two "#rrggbb" strings."""
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
    parts = []
    for i in (1, 3, 5):
        a = int(start[i:i + 2], 16)
        b = int(end[i:i + 2], 16)
        parts.append(f"{round(a + (b - a) * t):02x}")
    return "#" + "".join(parts)


# Precomputed fade ramp, so the animation loop does no color math.
GLOW = [blend(CELL_HIT, CELL_ON, i / 15.0) for i in range(16)]


class Highlighter:
    """Which column is sounding, and which cells are still ringing.

    Front-ends call advance() on a timer with the audio position, then ask
    color_for() about whichever cells they are about to repaint.
    """

    def __init__(self, matrix):
        self.matrix = matrix
        self.ringing = {}       # flat index -> time it was plucked
        self.column = None      # column currently sounding, or None

    def advance(self, position_samples):
        """Move the playhead and age the fades. Returns the cells that changed."""
        now = time.perf_counter()
        n = self.matrix.grid_size
        column = int(position_samples // SAMPLES_PER_COLUMN) % n

        dirty = set()
        if column != self.column:
            previous, self.column = self.column, column
            for row in range(n):
                index = n * row + column
                dirty.add(index)
                if self.matrix.grid[index]:
                    self.ringing[index] = now
                if previous is not None:
                    dirty.add(n * row + previous)

        for index in [i for i, t in self.ringing.items() if now - t > RING_SECONDS]:
            del self.ringing[index]
            dirty.add(index)
        dirty.update(self.ringing)
        return dirty

    def color_for(self, index, now=None):
        """What color cell `index` should be right now."""
        if self.matrix.grid[index]:
            plucked_at = self.ringing.get(index)
            if plucked_at is not None:
                progress = ((now or time.perf_counter()) - plucked_at) / RING_SECONDS
                if progress < 1.0:
                    return GLOW[int(progress * (len(GLOW) - 1))]
            return CELL_ON

        if self.column is not None and index % self.matrix.grid_size == self.column:
            return CELL_OFF_BEAT
        return CELL_OFF

    def reset(self):
        self.ringing.clear()
        self.column = None
