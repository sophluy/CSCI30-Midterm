"""Provided tests for Part Three."""

import pytest

from impl import ToneMatrix

RATE = 8000
PER_COLUMN = 16     # tiny so tests can step through several columns


def make(size=4, rate=RATE, per_column=PER_COLUMN):
    return ToneMatrix(size, sample_rate=rate, samples_per_column=per_column)


def lit(matrix):
    """The set of (row, col) cells that are on. Test helper only."""
    n = matrix.grid_size
    return {(r, c) for r in range(n) for c in range(n) if matrix.grid[n * r + c]}


# --------------------------------------------------------------------------
# Milestone 6: construction and indexing
# --------------------------------------------------------------------------

@pytest.mark.m6
def test_grid_is_a_flat_list_of_the_right_length():
    matrix = make(6)
    assert isinstance(matrix.grid, list)
    assert len(matrix.grid) == 36
    assert all(cell is False for cell in matrix.grid)


@pytest.mark.m6
def test_grid_is_not_nested():
    matrix = make(4)
    assert not isinstance(matrix.grid[0], (list, tuple)), \
        "store the grid as one flat list, not a list of lists"


@pytest.mark.m6
def test_one_instrument_per_row_with_descending_pitch():
    matrix = make(5)
    assert len(matrix.instruments) == 5
    freqs = [inst.frequency for inst in matrix.instruments]
    assert freqs == sorted(freqs, reverse=True), "row 0 is the top and highest row"


@pytest.mark.m6
def test_lower_rows_have_longer_delay_lines():
    matrix = make(5)
    lengths = [len(inst) for inst in matrix.instruments]
    assert lengths == sorted(lengths)


@pytest.mark.m6
@pytest.mark.parametrize("size", [0, -1, -8])
def test_rejects_bad_grid_size(size):
    with pytest.raises(ValueError):
        make(size)


@pytest.mark.m6
def test_index_of_is_row_major():
    matrix = make(4)
    assert matrix.index_of(0, 0) == 0
    assert matrix.index_of(0, 3) == 3
    assert matrix.index_of(1, 0) == 4
    assert matrix.index_of(2, 3) == 11
    assert matrix.index_of(3, 3) == 15


@pytest.mark.m6
def test_index_of_is_a_bijection():
    n = 7
    matrix = make(n)
    seen = {matrix.index_of(r, c) for r in range(n) for c in range(n)}
    assert seen == set(range(n * n))


@pytest.mark.m6
@pytest.mark.parametrize("row,col", [(-1, 0), (0, -1), (4, 0), (0, 4), (9, 9)])
def test_index_of_rejects_out_of_bounds(row, col):
    with pytest.raises(IndexError):
        make(4).index_of(row, col)


@pytest.mark.m6
def test_starts_on_column_zero():
    assert make().column == 0


# --------------------------------------------------------------------------
# Milestone 7: editing and text
# --------------------------------------------------------------------------

@pytest.mark.m7
def test_press_toggles_a_single_cell():
    matrix = make(4)
    matrix.press(2, 1)
    assert lit(matrix) == {(2, 1)}
    matrix.press(2, 1)
    assert lit(matrix) == set()


@pytest.mark.m7
def test_press_does_not_confuse_row_and_column():
    matrix = make(4)
    matrix.press(0, 3)
    assert matrix.is_on(0, 3)
    assert not matrix.is_on(3, 0)


@pytest.mark.m7
def test_drag_paints_when_the_press_switched_a_cell_on():
    matrix = make(4)
    matrix.press(1, 1)
    matrix.drag(1, 2)
    matrix.drag(1, 3)
    assert lit(matrix) == {(1, 1), (1, 2), (1, 3)}


@pytest.mark.m7
def test_drag_erases_when_the_press_switched_a_cell_off():
    matrix = make(4)
    for col in range(4):
        matrix.press(0, col)
    matrix.press(0, 0)          # turns (0, 0) back off
    matrix.drag(0, 1)
    matrix.drag(0, 2)
    assert lit(matrix) == {(0, 3)}


@pytest.mark.m7
def test_drag_over_a_cell_that_already_matches_is_harmless():
    matrix = make(4)
    matrix.press(0, 0)
    matrix.drag(0, 1)
    matrix.drag(0, 1)
    assert lit(matrix) == {(0, 0), (0, 1)}


@pytest.mark.m7
def test_only_the_most_recent_press_governs_the_drag():
    matrix = make(4)
    matrix.press(0, 0)          # on
    matrix.press(0, 0)          # off again
    matrix.drag(2, 2)
    assert lit(matrix) == set()


@pytest.mark.m7
def test_clear_switches_everything_off_in_place():
    matrix = make(4)
    grid = matrix.grid
    matrix.press(1, 1)
    matrix.press(3, 2)
    matrix.clear()
    assert lit(matrix) == set()
    assert matrix.grid is grid, "clear() should reuse the existing list"


@pytest.mark.m7
def test_to_text_round_trips():
    pattern = "#..#\n.##.\n....\n#...\n"
    matrix = ToneMatrix.from_text(pattern, sample_rate=RATE,
                                  samples_per_column=PER_COLUMN)
    assert matrix.to_text() == pattern.strip()


@pytest.mark.m7
def test_to_text_orientation():
    matrix = make(3)
    matrix.press(0, 2)
    assert matrix.to_text().splitlines()[0] == "..#"


# --------------------------------------------------------------------------
# Milestone 8: playback
# --------------------------------------------------------------------------

@pytest.mark.m8
def test_silent_matrix_produces_silence():
    matrix = make(4)
    assert [matrix.next_sample() for _ in range(200)] == [0.0] * 200


@pytest.mark.m8
def test_playhead_advances_once_per_period():
    matrix = make(4)
    assert matrix.column == 0
    matrix.next_sample()            # the first call plucks column 0
    assert matrix.column == 1
    for _ in range(PER_COLUMN - 1):
        matrix.next_sample()
    assert matrix.column == 1
    matrix.next_sample()
    assert matrix.column == 2


@pytest.mark.m8
def test_playhead_wraps_around():
    matrix = make(4)
    for _ in range(4 * PER_COLUMN):
        matrix.next_sample()
    assert matrix.column == 0


@pytest.mark.m8
def test_first_call_plucks_the_first_column():
    matrix = make(4)
    matrix.press(2, 0)
    matrix.next_sample()
    assert matrix.instruments[2].energy() > 0
    assert matrix.instruments[0].energy() == 0


@pytest.mark.m8
def test_a_cell_in_a_later_column_stays_quiet_until_the_playhead_arrives():
    matrix = make(4)
    matrix.press(1, 2)
    for _ in range(2 * PER_COLUMN):
        matrix.next_sample()
    assert matrix.instruments[1].energy() == 0
    matrix.next_sample()
    assert matrix.instruments[1].energy() > 0


@pytest.mark.m8
def test_whole_column_is_plucked_at_once():
    matrix = make(4)
    matrix.press(0, 0)
    matrix.press(3, 0)
    matrix.next_sample()
    assert matrix.instruments[0].energy() > 0
    assert matrix.instruments[3].energy() > 0
    assert matrix.instruments[1].energy() == 0


@pytest.mark.m8
def test_output_is_the_sum_over_all_rows():
    matrix = make(4)
    matrix.press(0, 0)
    matrix.press(3, 0)
    first = matrix.next_sample()
    # Two strings, each contributing +0.05 on their first sample.
    assert first == pytest.approx(0.1)


@pytest.mark.m8
def test_pluck_column_only_touches_lit_rows():
    matrix = make(4)
    matrix.press(1, 2)
    matrix.pluck_column(2)
    assert matrix.instruments[1].energy() > 0
    assert all(matrix.instruments[r].energy() == 0 for r in (0, 2, 3))


@pytest.mark.m8
def test_editing_mid_playback_is_picked_up_on_the_next_pass():
    matrix = make(4)
    for _ in range(2 * PER_COLUMN):
        matrix.next_sample()
    matrix.press(0, 3)
    for _ in range(4 * PER_COLUMN):     # one full loop of the playhead
        matrix.next_sample()
    assert matrix.instruments[0].energy() > 0


# --------------------------------------------------------------------------
# Milestone 9: resize
# --------------------------------------------------------------------------

@pytest.mark.m9
def test_growing_keeps_the_old_pattern_in_the_top_left():
    matrix = ToneMatrix.from_text("#..#\n.#..\n..#.\n#...",
                                  sample_rate=RATE, samples_per_column=PER_COLUMN)
    before = lit(matrix)
    matrix.resize(6)
    assert matrix.grid_size == 6
    assert len(matrix.grid) == 36
    assert lit(matrix) == before


@pytest.mark.m9
def test_shrinking_discards_the_far_rows_and_columns():
    matrix = ToneMatrix.from_text("#..#\n.#..\n..#.\n#...",
                                  sample_rate=RATE, samples_per_column=PER_COLUMN)
    matrix.resize(2)
    assert matrix.grid_size == 2
    assert lit(matrix) == {(0, 0), (1, 1)}


@pytest.mark.m9
def test_resize_to_the_same_size_changes_nothing():
    matrix = ToneMatrix.from_text("#..#\n.#..\n..#.\n#...",
                                  sample_rate=RATE, samples_per_column=PER_COLUMN)
    before = matrix.to_text()
    matrix.resize(4)
    assert matrix.to_text() == before


@pytest.mark.m9
def test_surviving_rows_keep_their_instrument_objects():
    matrix = make(4)
    keep = matrix.instruments[:4]
    matrix.resize(8)
    assert matrix.instruments[:4] == keep
    assert len(matrix.instruments) == 8


@pytest.mark.m9
def test_a_ringing_string_keeps_ringing_across_a_resize():
    matrix = make(4)
    matrix.press(2, 0)
    matrix.next_sample()
    energy = matrix.instruments[2].energy()
    matrix.resize(8)
    assert matrix.instruments[2].energy() == pytest.approx(energy)


@pytest.mark.m9
def test_new_rows_get_instruments_tuned_for_the_new_size():
    matrix = make(4)
    matrix.resize(8)
    freqs = [inst.frequency for inst in matrix.instruments[4:]]
    assert freqs == sorted(freqs, reverse=True)
    assert all(f > 0 for f in freqs)


@pytest.mark.m9
def test_resize_resets_the_playhead():
    matrix = make(4)
    for _ in range(2 * PER_COLUMN + 3):
        matrix.next_sample()
    matrix.resize(6)
    assert matrix.column == 0

    matrix.press(1, 0)
    matrix.next_sample()            # must pluck immediately, not 13 samples later
    assert matrix.instruments[1].energy() > 0
    assert matrix.column == 1


@pytest.mark.m9
@pytest.mark.parametrize("size", [0, -3])
def test_resize_rejects_bad_sizes(size):
    with pytest.raises(ValueError):
        make(4).resize(size)


@pytest.mark.m9
def test_grid_stays_flat_after_resize():
    matrix = make(4)
    matrix.resize(5)
    assert isinstance(matrix.grid, list) and len(matrix.grid) == 25
    assert not isinstance(matrix.grid[0], (list, tuple))
