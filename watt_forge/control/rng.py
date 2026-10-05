"""Deterministic pseudo-random numbers, identical in Python, JavaScript and C.

xorshift32 (Marsaglia 2003) gives 32-bit integers using only shifts and XOR, so all three
languages produce the same sequence exactly. Gaussian-like noise uses the Irwin-Hall sum of
four uniforms (pure arithmetic, no log/cos), so it is also bit-identical across languages.
"""
from __future__ import annotations

SQRT3 = 1.7320508075688772  # literal, not math.sqrt(3), so every port uses the same double
MASK = 0xFFFFFFFF


class XorShift32:
    def __init__(self, seed: int = 2463534242):
        self.x = (seed & MASK) or 2463534242

    def next_u32(self) -> int:
        x = self.x
        x ^= (x << 13) & MASK
        x ^= x >> 17
        x ^= (x << 5) & MASK
        self.x = x & MASK
        return self.x

    def uniform(self) -> float:
        """Uniform in [0, 1)."""
        return self.next_u32() / 4294967296.0

    def normal(self) -> float:
        """Zero-mean, unit-variance noise: Irwin-Hall(4), rescaled. Bounded to +/-3.46 sigma."""
        s = self.uniform() + self.uniform() + self.uniform() + self.uniform()
        return (s - 2.0) * SQRT3
