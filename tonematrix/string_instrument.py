"""Part 2: a simulated plucked string (Karplus-Strong).

The string is a RingBuffer of displacement samples plus two rules for how
that buffer evolves. You built the buffer in Part 1; here you only use its
public interface.

Rules for this file:
  * All access to the samples goes through enqueue/dequeue/peek. Do not reach
    into self.buffer._data, and do not keep a second copy of the samples.
  * The buffer is created once in __init__ and never replaced.
  * pluck() and next_sample() allocate nothing.
"""

from tonematrix.audio import SAMPLE_RATE
from tonematrix.ring_buffer import RingBuffer

# Height of the square wave written into the buffer by pluck().
PLUCK_AMPLITUDE = 0.05

# How much of its energy the string keeps on each trip around the buffer.
DECAY = 0.995


class StringInstrument:
    """A string that rings at a fixed frequency when plucked."""

    def __init__(self, frequency, sample_rate=SAMPLE_RATE):
        """Build a string that vibrates at `frequency` hertz.

        The buffer holds `sample_rate // frequency` samples. Create it, then
        fill it with that many zeros, corresponding to a string at rest. 
        Store the buffer in self.buffer and the frequency in self.frequency.

        Raise ValueError if the frequency is not positive, or if the buffer
        would hold fewer than 2 samples.
        """
        if frequency <= 0:
            raise ValueError("The frequency must be positive.")
        
        buffer_size = int(sample_rate // frequency)
        if buffer_size < 2:
            raise ValueError("The buffer must have at least 2 samples.")

        self.frequency = frequency
        self.buffer = RingBuffer(buffer_size)
        for i in range (buffer_size):
            self.buffer.enqueue(0.0)

    @classmethod
    def make_from_array(cls, values, frequency=None, sample_rate=SAMPLE_RATE):
        """Build a string whose buffer starts out holding `values`.

        Provided, for debugging and for the tests; you will not need to call
        it yourself. It skips __init__ so that it can accept a buffer of any
        contents, including ones no real pluck would produce.
        """
        string = cls.__new__(cls)
        string.frequency = (frequency if frequency is not None
                            else sample_rate / len(values))
        string.buffer = RingBuffer(len(values))
        for value in values:
            string.buffer.enqueue(value)
        return string

    def __len__(self):
        """Number of samples in the buffer. Provided."""
        return self.buffer.size()

    def pluck(self):
        """Excite the string: front half of the buffer to +PLUCK_AMPLITUDE, 
        back half to -PLUCK_AMPLITUDE.
        """
        size = self.buffer.size()
        half = size // 2
        for i in range(size):
            self.buffer.dequeue()
        
        for i in range(size):
            if i < half:
                self.buffer.enqueue(PLUCK_AMPLITUDE)
            else:
                self.buffer.enqueue(-PLUCK_AMPLITUDE)

    def next_sample(self):
        """Return the next output sample and advance the simulation one step."""
        front = self.buffer.dequeue()
        second = self.buffer.peek()
        new_sample = DECAY * (front + second) / 2.0
        self.buffer.enqueue(new_sample)
        return front

    def energy(self):
        """Mean absolute amplitude in the buffer. Provided; used in Part 4.

        Rotating a full queue all the way around leaves it exactly as it
        started, so this reads every sample without disturbing anything. It is
        also a decent worked example of using the buffer's interface.
        """
        total = 0.0
        n = self.buffer.size()
        for _ in range(n):
            value = self.buffer.dequeue()
            total += abs(value)
            self.buffer.enqueue(value)
        return total / n
