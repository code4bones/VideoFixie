from __future__ import annotations

from dataclasses import dataclass, field
from shlex import quote


@dataclass(frozen=True)
class PlannedCommand:
    """A command stage that can be inspected, copied, logged, and executed."""

    program: str
    args: tuple[str, ...] = field(default_factory=tuple)
    label: str = ""

    def argv(self) -> list[str]:
        return [self.program, *self.args]

    def display(self) -> str:
        return " ".join(quote(part) for part in self.argv())
