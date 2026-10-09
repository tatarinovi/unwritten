from __future__ import annotations

import random
from collections.abc import Sequence


class CounterRNG:
    """Deterministic RNG whose whole state is (seed, counter).

    Each draw builds a fresh Random from an integer mix, then increments the
    counter. Same seed and same number of draws always yield the same sequence.
    """

    def __init__(self, seed: int, counter: int = 0) -> None:
        self.seed = int(seed)
        self.counter = int(counter)

    def _pull(self) -> random.Random:
        mixed = (self.seed * 1_000_003 + self.counter * 9_176 + 0x9E3779B9) & ((1 << 63) - 1)
        self.counter += 1
        return random.Random(mixed)

    def random(self) -> float:
        return self._pull().random()

    def choice(self, options: Sequence[int]) -> int:
        if not options:
            raise ValueError("cannot choose from an empty sequence")
        return int(self._pull().choice(list(options)))
