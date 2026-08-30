from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLineEdit


class TimecodeEdit(QLineEdit):
    valueChanged = Signal(float)

    def __init__(self, value: float = 0.0, parent=None) -> None:
        super().__init__(parent)
        self._minimum = 0.0
        self._maximum = 24 * 60 * 60.0
        self._value = 0.0
        self.setPlaceholderText("mm:ss.mmm")
        self.setMinimumWidth(96)
        self.editingFinished.connect(self._commit_text)
        self.setValue(value)

    def setRange(self, minimum: float, maximum: float) -> None:  # noqa: N802
        self._minimum = minimum
        self._maximum = max(minimum, maximum)
        self.setValue(self._value)

    def value(self) -> float:
        return self._value

    def setValue(self, value: float) -> None:  # noqa: N802
        clamped = min(max(self._minimum, float(value)), self._maximum)
        changed = abs(clamped - self._value) >= 0.0005
        self._value = clamped
        self.setText(format_timecode(clamped))
        if changed:
            self.valueChanged.emit(self._value)

    def _commit_text(self) -> None:
        try:
            self.setValue(parse_timecode(self.text()))
        except ValueError:
            self.setText(format_timecode(self._value))


def parse_timecode(value: str) -> float:
    text = value.strip().replace(",", ".")
    if not text:
        raise ValueError("Timecode is empty")

    parts = text.split(":")
    if len(parts) == 1:
        seconds = float(parts[0])
    elif len(parts) == 2:
        minutes = int(parts[0])
        seconds = minutes * 60 + float(parts[1])
    elif len(parts) == 3:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = hours * 3600 + minutes * 60 + float(parts[2])
    else:
        raise ValueError(f"Unsupported timecode: {value}")

    if seconds < 0:
        raise ValueError("Timecode must be non-negative")
    return seconds


def format_timecode(seconds: float) -> str:
    total_milliseconds = max(0, round(seconds * 1000))
    total_seconds, milliseconds = divmod(total_milliseconds, 1000)
    minutes_total, second = divmod(total_seconds, 60)
    hours, minute = divmod(minutes_total, 60)
    if hours:
        return f"{hours:d}:{minute:02d}:{second:02d}.{milliseconds:03d}"
    return f"{minute:d}:{second:02d}.{milliseconds:03d}"
