"""Provided tests for Part One.

Run one milestone at a time:

    pytest -m m1

Everything after the milestone you are working on is expected to fail.
"""

from array import array

import pytest

from impl import RingBuffer


def filled(values, capacity=None):
    """A buffer holding `values`, front first. Test helper."""
    buffer = RingBuffer(capacity if capacity is not None else len(values))
    for value in values:
        buffer.enqueue(value)
    return buffer


def drain(buffer):
    """Everything in the buffer, front to rear. Empties it."""
    return [buffer.dequeue() for _ in range(buffer.size())]


# --------------------------------------------------------------------------
# Milestone 1: construction and the size predicates
# --------------------------------------------------------------------------

@pytest.mark.m1
def test_new_buffer_is_empty():
    buffer = RingBuffer(7)
    assert buffer.size() == 0
    assert buffer.is_empty()
    assert not buffer.is_full()


@pytest.mark.m1
def test_capacity_is_what_was_asked_for():
    assert RingBuffer(7).capacity() == 7
    assert RingBuffer(1).capacity() == 1


@pytest.mark.m1
def test_storage_is_a_fixed_array_of_doubles():
    buffer = RingBuffer(7)
    assert isinstance(buffer._data, array), "use array('d'), not a list"
    assert buffer._data.typecode == "d"
    assert len(buffer._data) == 7, "allocate the whole capacity up front"


@pytest.mark.m1
def test_front_and_rear_start_together():
    buffer = RingBuffer(7)
    assert buffer._front == buffer._rear


@pytest.mark.m1
@pytest.mark.parametrize("capacity", [0, -1, -7])
def test_rejects_bad_capacity(capacity):
    with pytest.raises(ValueError):
        RingBuffer(capacity)


@pytest.mark.m1
def test_len_matches_size():
    buffer = RingBuffer(4)
    assert len(buffer) == 0


# --------------------------------------------------------------------------
# Milestone 2: enqueue, dequeue, peek
# --------------------------------------------------------------------------

@pytest.mark.m2
def test_enqueue_then_dequeue_preserves_order():
    buffer = filled([1.0, 2.0, 3.0], capacity=7)
    assert buffer.size() == 3
    assert drain(buffer) == [1.0, 2.0, 3.0]


@pytest.mark.m2
def test_peek_does_not_remove():
    buffer = filled([1.0, 2.0], capacity=7)
    assert buffer.peek() == 1.0
    assert buffer.peek() == 1.0
    assert buffer.size() == 2


@pytest.mark.m2
def test_size_tracks_both_operations():
    buffer = RingBuffer(4)
    for expected, value in enumerate([1.0, 2.0, 3.0], start=1):
        buffer.enqueue(value)
        assert buffer.size() == expected
    for expected in (2, 1, 0):
        buffer.dequeue()
        assert buffer.size() == expected


@pytest.mark.m2
def test_is_full_at_capacity():
    buffer = filled([1.0, 2.0, 3.0])
    assert buffer.is_full()
    buffer.dequeue()
    assert not buffer.is_full()


@pytest.mark.m2
def test_the_walkthrough_from_the_handout():
    """The 7-element example: enqueue 1,2,3, remove two, then enqueue 4..9."""
    buffer = filled([1.0, 2.0, 3.0], capacity=7)
    assert buffer.dequeue() == 1.0
    assert buffer.dequeue() == 2.0
    for value in (4.0, 5.0, 6.0, 7.0, 8.0, 9.0):
        buffer.enqueue(value)
    assert buffer.is_full()
    assert drain(buffer) == [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]


@pytest.mark.m2
def test_indices_wrap_instead_of_running_off_the_end():
    buffer = filled([1.0, 2.0, 3.0], capacity=3)
    buffer.dequeue()
    buffer.enqueue(4.0)         # must land at index 0
    assert buffer._rear == 1
    assert drain(buffer) == [2.0, 3.0, 4.0]


@pytest.mark.m2
def test_survives_many_laps():
    buffer = filled([0.0, 0.0, 0.0, 0.0, 0.0])
    for i in range(1000):
        assert buffer.dequeue() == pytest.approx(i - 5.0 if i >= 5 else 0.0)
        buffer.enqueue(float(i))
    assert buffer.size() == 5
    assert drain(buffer) == [995.0, 996.0, 997.0, 998.0, 999.0]


@pytest.mark.m2
def test_dequeue_does_not_shift_the_array():
    """Constant time means the stored bytes stay where they are."""
    buffer = filled([1.0, 2.0, 3.0], capacity=3)
    buffer.dequeue()
    assert list(buffer._data)[1:] == [2.0, 3.0], \
        "dequeue() must move an index, not shuffle the items down"


@pytest.mark.m2
def test_storage_is_never_reallocated():
    buffer = RingBuffer(3)
    original = buffer._data
    for i in range(20):
        buffer.enqueue(float(i))
        buffer.dequeue()
    assert buffer._data is original


@pytest.mark.m2
def test_dequeue_from_empty_raises():
    with pytest.raises(IndexError):
        RingBuffer(3).dequeue()


@pytest.mark.m2
def test_peek_into_empty_raises():
    with pytest.raises(IndexError):
        RingBuffer(3).peek()


@pytest.mark.m2
def test_enqueue_into_full_raises():
    buffer = filled([1.0, 2.0, 3.0])
    with pytest.raises(IndexError):
        buffer.enqueue(4.0)


@pytest.mark.m2
def test_emptied_buffer_is_reusable():
    buffer = filled([1.0, 2.0, 3.0])
    drain(buffer)
    assert buffer.is_empty()
    buffer.enqueue(9.0)
    assert buffer.peek() == 9.0
    assert buffer.size() == 1
