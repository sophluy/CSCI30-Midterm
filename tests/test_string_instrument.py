"""Provided tests for Part Two.

These use the ring buffer's public interface only, so they describe the
string in terms of a queue: `contents()` below reads the buffer front to
rear, exactly the order next_sample() will hand the samples back to you.
"""

import pytest

from impl import StringInstrument

A = 0.05    # PLUCK_AMPLITUDE
D = 0.995   # DECAY


def make(freq=1000.0, rate=8000):
    """A string with a conveniently short buffer: 8000 // 1000 == 8 samples."""
    return StringInstrument(freq, rate)


def contents(string):
    """The buffer's samples, front to rear, without disturbing it."""
    values = []
    for _ in range(string.buffer.size()):
        value = string.buffer.dequeue()
        values.append(value)
        string.buffer.enqueue(value)
    return values


# --------------------------------------------------------------------------
# Milestone 3: the constructor
# --------------------------------------------------------------------------

@pytest.mark.m3
def test_buffer_length_is_rate_over_frequency():
    assert make(1000.0, 8000).buffer.capacity() == 8
    assert make(400.0, 8000).buffer.capacity() == 20
    assert make(440.0, 44100).buffer.capacity() == 100


@pytest.mark.m3
def test_buffer_length_rounds_down():
    assert make(1500.0, 8000).buffer.capacity() == 5      # 8000 / 1500 = 5.33...


@pytest.mark.m3
def test_buffer_starts_full_of_zeros():
    string = make()
    assert string.buffer.is_full(), "a string at rest is a full buffer of zeros"
    assert contents(string) == [0.0] * 8


@pytest.mark.m3
def test_higher_frequency_means_shorter_buffer():
    assert len(make(2000.0, 8000)) < len(make(500.0, 8000))


@pytest.mark.m3
@pytest.mark.parametrize("freq", [0.0, -1.0, -440.0])
def test_rejects_non_positive_frequency(freq):
    with pytest.raises(ValueError):
        make(freq)


@pytest.mark.m3
def test_rejects_frequency_that_would_give_a_degenerate_buffer():
    with pytest.raises(ValueError):     # length would be 1
        make(5000.0, 8000)
    with pytest.raises(ValueError):     # length would be 0
        make(9000.0, 8000)


# --------------------------------------------------------------------------
# Milestone 4: pluck
# --------------------------------------------------------------------------

@pytest.mark.m4
def test_pluck_writes_a_square_wave():
    string = make()
    string.pluck()
    assert contents(string) == [A] * 4 + [-A] * 4


@pytest.mark.m4
def test_pluck_leaves_the_buffer_full():
    string = make()
    string.pluck()
    assert string.buffer.is_full()
    assert string.buffer.size() == 8


@pytest.mark.m4
def test_pluck_starts_the_wave_at_the_front():
    string = make()
    string.pluck()
    assert string.buffer.peek() == A


@pytest.mark.m4
def test_pluck_handles_odd_length_buffers():
    string = make(1500.0, 8000)         # length 5
    string.pluck()
    values = contents(string)
    assert values[:2] == [A, A]
    assert values[3:] == [-A, -A]
    assert values[2] in (A, -A)


@pytest.mark.m4
def test_pluck_reuses_the_same_buffer_object():
    string = make()
    before = string.buffer
    string.pluck()
    assert string.buffer is before, "pluck() must not build a new buffer"


@pytest.mark.m4
def test_repluck_restores_the_square_wave():
    string = StringInstrument.make_from_array([0.017] * 8, frequency=1000.0)
    string.pluck()
    assert contents(string) == [A] * 4 + [-A] * 4


# --------------------------------------------------------------------------
# Milestone 5: next_sample
# --------------------------------------------------------------------------

@pytest.mark.m5
def test_unplucked_string_is_silent():
    string = make()
    assert [string.next_sample() for _ in range(50)] == [0.0] * 50


@pytest.mark.m5
def test_buffer_stays_exactly_full():
    string = make()
    string.pluck()
    for _ in range(25):
        string.next_sample()
        assert string.buffer.is_full(), "one dequeue, one enqueue, every step"


@pytest.mark.m5
def test_first_four_samples_after_a_pluck():
    string = make()
    string.pluck()
    assert [string.next_sample() for _ in range(4)] == pytest.approx([A, A, A, A])


@pytest.mark.m5
def test_buffer_state_after_four_samples():
    string = make()
    string.pluck()
    for _ in range(4):
        string.next_sample()
    # Front to rear: the untouched second half, then the four averages that
    # were enqueued behind it. The last one is D * (A + -A) / 2 == 0.
    expected = [-A, -A, -A, -A, D * A, D * A, D * A, 0.0]
    assert contents(string) == pytest.approx(expected)


@pytest.mark.m5
def test_new_sample_is_the_decayed_average_of_the_first_two():
    string = StringInstrument.make_from_array([0.2, 0.4, 0.5, 0.3], frequency=1000.0)
    assert string.next_sample() == pytest.approx(0.2)
    assert contents(string) == pytest.approx([0.4, 0.5, 0.3, D * (0.2 + 0.4) / 2])


@pytest.mark.m5
def test_averaging_reaches_across_the_wrap():
    """The last sample of a lap averages with the first value enqueued in it."""
    string = make()
    string.pluck()
    for _ in range(7):
        string.next_sample()
    assert string.next_sample() == pytest.approx(-A)
    assert contents(string)[-1] == pytest.approx(D * (-A + D * A) / 2.0)


@pytest.mark.m5
def test_next_sample_reuses_the_same_buffer_object():
    string = make()
    string.pluck()
    before = string.buffer
    string.next_sample()
    assert string.buffer is before, "next_sample() must not build a new buffer"


@pytest.mark.m5
def test_string_decays_towards_silence():
    """The decay applies once per trip around the buffer, so a low string
    rings for a good few seconds before it fades."""
    string = make(441.0, 44100)
    string.pluck()
    early = max(abs(string.next_sample()) for _ in range(1000))
    for _ in range(199000):
        string.next_sample()
    late = max(abs(string.next_sample()) for _ in range(1000))
    assert late < early / 100


@pytest.mark.m5
def test_pitch_matches_the_requested_frequency():
    """A 441Hz string should cross zero about 882 times per second."""
    rate, freq = 44100, 441.0
    string = StringInstrument(freq, rate)
    string.pluck()
    samples = [string.next_sample() for _ in range(rate // 10)]   # 0.1 seconds

    crossings = sum(
        1 for i in range(1, len(samples))
        if (samples[i - 1] < 0) != (samples[i] < 0)
    )
    assert 80 <= crossings <= 96
