"""Your write-up must contain all four of the following. A large speedup with a superficial write-
up scores below a modest speedup with a thorough one.

1. The running time of the original operation and of yours, in big-O notation, with every
parameter named: grid size n, lit cells k, ringing strings a, and so on. Simply saying “It’s
faster” does not count.
2. An argument for each bound. Say why the loop runs the number of times you claim it
does.
3. Measurements at a minimum of three grid sizes, before and after, produced by benchmark.py
or an extension of it.
"""

from tonematrix.audio import SAMPLE_RATE, SAMPLES_PER_COLUMN
from tonematrix.matrix import ToneMatrix as OGToneMatrix
 
 
class ToneMatrix(OGToneMatrix):
    """A ToneMatrix pluck_column runs in O(k) instead of O(n)."""
 
    def __init__(self, grid_size, sample_rate=SAMPLE_RATE,
                 samples_per_column=SAMPLES_PER_COLUMN):
        
        super().__init__(grid_size, sample_rate=sample_rate,
                         samples_per_column=samples_per_column)
        self._rebuild()
 
    def _rebuild(self):
        size = self.grid_size
        self.lit = [None] * size
        for col in range(size):
            self.lit[col] = set()
            for row in range(size):
                if self.grid[self.index_of(row, col)]:
                    self.lit[col].add(row)
 
    def sync(self, row, col):
        if self.grid[self.index_of(row, col)]:
            self.lit[col].add(row)
        else:
            self.lit[col].discard(row)

    def set_cell(self, row, col, value):
        super().set_cell(row, col, value)
        self.sync(row, col)
 
    def press(self, row, col):
        super().press(row, col)
        self.sync(row, col)
 
    def drag(self, row, col):
        super().drag(row, col)
        self.sync(row, col)
 
    def clear(self):
        super().clear()
        self._rebuild()
 
    def resize(self, new_size):
        super().resize(new_size)
        self._rebuild()

    """pluck_column scans all n rows looking for the lit ones, but a typical pattern has only a handful
    lit per column. Keep an auxiliary data structure mapping each column to its lit rows, and keep
    it consistent as press, drag, clear, and resize modify the grid.
    Things to consider: Which operations get slower in exchange? What is the space overhead
    compared to the flat list of Booleans, and above what density does the flat list simply win?"""

    def pluck_column(self, col):
        self.index_of(0, col)  
        for row in self.lit[col]:
            self.instruments[row].pluck()