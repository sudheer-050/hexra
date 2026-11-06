"""Signal smoothing filters."""
from __future__ import annotations

import math


def _alpha(cutoff: float, dt: float) -> float:
    tau = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


class OneEuroFilter:
    """One Euro filter (Casiez, Roussel, Vogel; CHI 2012) for one scalar signal.

    min_cutoff: lower means steadier at rest but more lag.
    beta: higher means less lag during fast movement.
    d_cutoff: cutoff for the speed estimate; rarely needs changing.
    """

    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.0, d_cutoff: float = 1.0):
        if min_cutoff <= 0 or d_cutoff <= 0:
            raise ValueError("min_cutoff and d_cutoff must be positive")
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.reset()

    def reset(self) -> None:
        self._t_prev: float | None = None
        self._x_prev = 0.0
        self._dx_prev = 0.0

    @property
    def velocity(self) -> float:
        """Smoothed speed estimate (signal units per second)."""
        return self._dx_prev

    def __call__(self, x: float, t: float) -> float:
        if self._t_prev is None:
            self._t_prev, self._x_prev, self._dx_prev = t, x, 0.0
            return x
        dt = t - self._t_prev
        if dt <= 0:
            return self._x_prev
        dx = (x - self._x_prev) / dt
        a_d = _alpha(self.d_cutoff, dt)
        dx_hat = a_d * dx + (1.0 - a_d) * self._dx_prev
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = _alpha(cutoff, dt)
        x_hat = a * x + (1.0 - a) * self._x_prev
        self._t_prev, self._x_prev, self._dx_prev = t, x_hat, dx_hat
        return x_hat


class PointFilter:
    """Independent One Euro filters for x and y."""

    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.0, d_cutoff: float = 1.0):
        self._fx = OneEuroFilter(min_cutoff, beta, d_cutoff)
        self._fy = OneEuroFilter(min_cutoff, beta, d_cutoff)

    def __call__(self, x: float, y: float, t: float) -> tuple[float, float]:
        return self._fx(x, t), self._fy(y, t)

    @property
    def velocity(self) -> tuple[float, float]:
        return self._fx.velocity, self._fy.velocity

    def reset(self) -> None:
        self._fx.reset()
        self._fy.reset()
