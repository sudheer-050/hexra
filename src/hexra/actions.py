"""Mouse output backends."""
from __future__ import annotations

from typing import Protocol


class Mouse(Protocol):
    is_down: bool

    def move(self, x: float, y: float) -> None: ...
    def press(self) -> None: ...
    def release(self) -> None: ...
    def click_right(self) -> None: ...
    def scroll(self, steps: int) -> None: ...
    def hscroll(self, steps: int) -> None: ...


class NullMouse:
    """Does nothing. Used by --dry-run and in tests."""

    def __init__(self) -> None:
        self.is_down = False
        self.position: tuple[float, float] | None = None
        self.right_clicks = 0
        self.scroll_total = 0
        self.hscroll_total = 0

    def move(self, x: float, y: float) -> None:
        self.position = (x, y)

    def press(self) -> None:
        self.is_down = True

    def release(self) -> None:
        self.is_down = False

    def click_right(self) -> None:
        self.right_clicks += 1

    def scroll(self, steps: int) -> None:
        self.scroll_total += steps

    def hscroll(self, steps: int) -> None:
        self.hscroll_total += steps


class PynputMouse:
    """Real mouse output. pynput is imported lazily so tests run on any machine."""

    def __init__(self) -> None:
        from pynput.mouse import Button, Controller

        self._button = Button.left
        self._mouse = Controller()
        self.is_down = False

    @property
    def position(self):
        return tuple(self._mouse.position)

    def move(self, x: float, y: float) -> None:
        self._mouse.position = (round(x), round(y))

    def press(self) -> None:
        if not self.is_down:
            self._mouse.press(self._button)
            self.is_down = True

    def release(self) -> None:
        if self.is_down:
            self._mouse.release(self._button)
            self.is_down = False

    def click_right(self) -> None:
        from pynput.mouse import Button

        self._mouse.click(Button.right)

    def scroll(self, steps: int) -> None:
        self._mouse.scroll(0, steps)  # positive = up

    def hscroll(self, steps: int) -> None:
        self._mouse.scroll(steps, 0)  # positive = right
