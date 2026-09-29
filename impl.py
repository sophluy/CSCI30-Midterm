"""Selects which implementation the tests run against.

By default the tests import your code from `tonematrix/`. Setting the
environment variable TONEMATRIX_IMPL=solution points them at the reference
implementation instead, which is how the course staff sanity-checks the
tests themselves.
"""

import os

if os.environ.get("TONEMATRIX_IMPL") == "solution":
    from solution.matrix import ToneMatrix
    from solution.ring_buffer import RingBuffer
    from solution.string_instrument import StringInstrument
else:
    from tonematrix.matrix import ToneMatrix
    from tonematrix.ring_buffer import RingBuffer
    from tonematrix.string_instrument import StringInstrument

__all__ = ["RingBuffer", "StringInstrument", "ToneMatrix"]
