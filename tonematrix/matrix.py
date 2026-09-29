"""Part 3: the tone matrix.

A grid_size x grid_size grid of cells, stored as a *flat* list in row-major
order, plus one StringInstrument per row.

Rules for this file:
  * self.grid is a flat list of bools of length grid_size ** 2. Do not use a
    list of lists, a dict, a set, or numpy.
  * The list is fixed-length: no append/pop/insert/remove. resize() is the
    one place you build a new list, and even there you copy element by
    element.
"""

from tonematrix.audio import SAMPLE_RATE, SAMPLES_PER_COLUMN
from tonematrix.scales import frequency_for_row
from tonematrix.string_instrument import StringInstrument

ON = "#"
OFF = "."


class ToneMatrix:
    def __init__(self, grid_size, sample_rate=SAMPLE_RATE,
                 samples_per_column=SAMPLES_PER_COLUMN):
        """Build an all-off grid_size x grid_size matrix.

        Set up:
          * self.grid          - flat list of grid_size ** 2 False values
          * self.instruments   - one StringInstrument per row, tuned with
                                  frequency_for_row(row, grid_size)
          * self.column        - the column the playhead is about to pluck
          * whatever bookkeeping you need for next_sample() and drag()

        Raise ValueError if grid_size < 1.
        """
        # TODO (Milestone 5)

        if grid_size < 1:
            raise ValueError("The grid size must be greater than 1.")

        self.grid_size = grid_size
        self.grid = [False] * (grid_size ** 2)
        self.instruments = [None] * grid_size
        self.sample_rate = sample_rate
        self.samples_per_column = samples_per_column
        for row in range(grid_size):
            self.instruments[row] = StringInstrument(
                frequency_for_row(row, grid_size), sample_rate)
        self.column = 0
        self.drag_value = None #should drag paint or erase
        self.sample_counter = 0 #tracks the audio ticks for column timing

    ### indexing

    def index_of(self, row, col):
        """Map a (row, col) pair to its index in the flat list.

        Raise IndexError if the position is off the grid.
        """
         # TODO (Milestone 5)
        if row < 0 or row >= self.grid_size or col < 0 or col >= self.grid_size:
            raise IndexError("Keep the position on the grid.")
        return self.grid_size * row + col

    def is_on(self, row, col):
        """Provided, once index_of works."""
        return self.grid[self.index_of(row, col)]

    def set_cell(self, row, col, value):
        """Provided, once index_of works."""
        self.grid[self.index_of(row, col)] = bool(value)

    ### editing

    def press(self, row, col):
        """The user clicked this cell: toggle it.

        Also remember what the cell became, so that drag() can copy it.
        """
        current = self.is_on(row, col)
        if current:
            new_val = False
        else:
            new_val = True
        self.set_cell(row, col, new_val)
        self.drag_value = new_val

    def drag(self, row, col):
        """The user dragged across this cell after a press().

        The cell takes on the same value the pressed cell ended up with: a
        drag that started by switching a cell on paints cells on, and a drag
        that started by switching one off erases.
        """
        if self.drag_value != None:
            self.set_cell(row, col, self.drag_value)

    def clear(self):
        """Switch every cell off, without replacing the list."""
        for i in range(len(self.grid)):
            self.grid[i] = False

    ### playback

    def next_sample(self):
        """Return the next sample of audio, advancing time by one step.

        On the very first call, and on every samples_per_column-th call after
        that: pluck every lit cell in the current column, then move the
        playhead one column right, wrapping around.

        Every call, including those ones, returns the sum of next_sample()
        over all the instruments.
        """
        if self.sample_counter == 0:
            self.pluck_column(self.column)
            self.column = (self.column + 1) % self.grid_size

        self.sample_counter = (self.sample_counter + 1) % self.samples_per_column

        sum = 0.0
        for i in self.instruments:
            sum += i.next_sample()
        return sum

    def pluck_column(self, col):
        """Pluck the string of every lit row in this column."""
        for row in range(self.grid_size):
            if self.grid[self.index_of(row, col)]:
                self.instruments[row].pluck()

    ### resizing

    def resize(self, new_size):
        """Change the grid to new_size x new_size.

        Cells present in both the old and new grid keep their values; new
        cells start off. Instruments for rows that survive are reused as-is,
        rows beyond the old size get fresh instruments. The playhead resets
        to column 0 and the next call to next_sample() plucks immediately.

        Raise ValueError if new_size < 1.
        """
        if new_size < 1:
            raise ValueError("New size must be greater than 1.")

        old_size = self.grid_size
        old_grid = self.grid

        keep = min(old_size, new_size)
        new_grid = [False] * (new_size ** 2)
        for row in range(keep):
            for col in range(keep):
                new_grid[new_size * row + col] = self.grid[self.index_of(row, col)]

        fresh_instruments = [None] * new_size
        for row in range(new_size):
            if row < old_size:
                fresh_instruments[row] = self.instruments[row]
            else:
                fresh_instruments[row] = StringInstrument(
                    frequency_for_row(row, new_size), self.sample_rate)
                
        self.grid = new_grid
        self.instruments = fresh_instruments
        self.grid_size = new_size
        self.column = 0
        self.sample_counter = 0

    ### serialization

    def to_text(self):
        """Render the grid as grid_size lines of '#' and '.'."""
        result = ""

        for i in range(self.grid_size):
            line = ""
            for j in range(self.grid_size):
                if self.is_on(i, j):
                    line = line + ON
                else:
                    line = line + OFF

            if i > 0:
                result +="\n"

            result += line
        
        return result

    @classmethod
    def from_text(cls, text, **kwargs):
        """Build a matrix from the format to_text() produces. Provided."""
        rows = [line.strip() for line in text.strip().splitlines() if line.strip()]
        size = len(rows)
        if any(len(line) != size for line in rows):
            raise ValueError("pattern must be square")

        matrix = cls(size, **kwargs)
        for r, line in enumerate(rows):
            for c, ch in enumerate(line):
                matrix.set_cell(r, c, ch == ON)
        return matrix

    def __str__(self):
        return self.to_text()