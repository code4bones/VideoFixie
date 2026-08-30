from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from videofixie.domain.jobs import TestSegment, TestSegmentKind


class SegmentTimeline(QWidget):
    segmentChanged = Signal(object)
    playheadChanged = Signal(float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._duration_seconds = 0.0
        self._segment = TestSegment("Preview", 0.0, 15.0, TestSegmentKind.CUSTOM)
        self._playhead_seconds = 0.0
        self._display_start_seconds: float | None = None
        self._display_end_seconds: float | None = None
        self._show_segment_handles = True
        self._drag_mode: str | None = None
        self.setMinimumHeight(118)
        self.setMouseTracking(True)

    def set_duration(self, duration_seconds: float | None) -> None:
        self._duration_seconds = max(0.0, duration_seconds or 0.0)
        if self._duration_seconds > 0:
            end = min(self._segment.end_seconds, self._duration_seconds)
            start = min(self._segment.start_seconds, max(0.0, end - 0.1))
            if end <= start:
                end = min(self._duration_seconds, start + min(15.0, self._duration_seconds))
            self._segment = replace(self._segment, start_seconds=start, end_seconds=end)
            self._playhead_seconds = min(self._playhead_seconds, self._duration_seconds)
            self._clamp_display_window()
        self.update()

    def set_segment(self, segment: TestSegment) -> None:
        self._segment = self._clamp_segment(segment)
        self.update()

    def segment(self) -> TestSegment:
        return self._segment

    def playhead_seconds(self) -> float:
        return self._playhead_seconds

    def set_playhead(self, seconds: float, emit: bool = True) -> None:
        self._playhead_seconds = self._clamp_visible_time(seconds)
        if emit:
            self.playheadChanged.emit(self._playhead_seconds)
        self.update()

    def set_display_window(self, start_seconds: float, end_seconds: float, show_segment_handles: bool = False) -> None:
        start = max(0.0, start_seconds)
        end = max(start + 0.1, end_seconds)
        if self._duration_seconds > 0:
            start = min(start, max(0.0, self._duration_seconds - 0.1))
            end = min(max(start + 0.1, end), self._duration_seconds)
        self._display_start_seconds = start
        self._display_end_seconds = end
        self._show_segment_handles = show_segment_handles
        self._playhead_seconds = self._clamp_visible_time(self._playhead_seconds)
        self.update()

    def clear_display_window(self) -> None:
        self._display_start_seconds = None
        self._display_end_seconds = None
        self._show_segment_handles = True
        self._playhead_seconds = self._clamp_visible_time(self._playhead_seconds)
        self.update()

    def display_window(self) -> tuple[float, float]:
        return self._visible_start_end()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        track = self._track_rect()

        painter.fillRect(self.rect(), QColor("#17191f"))
        painter.setPen(QPen(QColor("#3a3f4b"), 1))
        painter.setBrush(QColor("#252a34"))
        painter.drawRoundedRect(track, 4, 4)

        self._draw_ticks(painter, track)
        if self._show_segment_handles:
            self._draw_segment(painter, track)
        self._draw_playhead(painter, track)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = event.position()
        x = point.x()
        track = self._track_rect()
        in_x = self._time_to_x(self._segment.start_seconds)
        out_x = self._time_to_x(self._segment.end_seconds)
        playhead_x = self._time_to_x(self._playhead_seconds)

        if self._show_segment_handles and self._in_handle_rect(track, in_x).contains(point):
            self._drag_mode = "in"
        elif self._show_segment_handles and self._out_handle_rect(track, out_x).contains(point):
            self._drag_mode = "out"
        elif self._playhead_handle_rect(track, playhead_x).contains(point):
            self._drag_mode = "playhead"
        elif self._show_segment_handles and in_x < x < out_x:
            self._drag_mode = "range"
            self._range_anchor = self._x_to_time(x)
            self._range_start = self._segment.start_seconds
            self._range_end = self._segment.end_seconds
        else:
            self._drag_mode = "playhead"
            self.set_playhead(self._x_to_time(x))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._drag_mode:
            return

        current = self._x_to_time(event.position().x())
        minimum_gap = min(0.1, self._duration_seconds) if self._duration_seconds else 0.1

        if self._drag_mode == "in" and self._show_segment_handles:
            start = min(current, self._segment.end_seconds - minimum_gap)
            self._emit_segment(replace(self._segment, start_seconds=max(0.0, start)))
        elif self._drag_mode == "out" and self._show_segment_handles:
            end = max(current, self._segment.start_seconds + minimum_gap)
            self._emit_segment(replace(self._segment, end_seconds=self._clamp_time(end)))
        elif self._drag_mode == "playhead":
            self.set_playhead(current)
        elif self._drag_mode == "range" and self._show_segment_handles:
            delta = current - getattr(self, "_range_anchor", current)
            length = getattr(self, "_range_end", self._segment.end_seconds) - getattr(self, "_range_start", self._segment.start_seconds)
            start = getattr(self, "_range_start", self._segment.start_seconds) + delta
            start = min(max(0.0, start), max(0.0, self._duration_seconds - length))
            self._emit_segment(replace(self._segment, start_seconds=start, end_seconds=start + length))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        del event
        self._drag_mode = None

    def _draw_ticks(self, painter: QPainter, track: QRectF) -> None:
        painter.setPen(QPen(QColor("#586071"), 1))
        start, end = self._visible_start_end()
        duration = max(0.1, end - start)
        tick_count = 6
        metrics = QFontMetrics(self.font())
        for index in range(tick_count + 1):
            seconds = start + duration * index / tick_count
            x = self._time_to_x(seconds)
            painter.drawLine(QPoint(round(x), round(track.bottom() + 4)), QPoint(round(x), round(track.bottom() + 12)))
            label = _format_time(seconds)
            painter.setPen(QColor("#9aa3b5"))
            painter.drawText(round(x - metrics.horizontalAdvance(label) / 2), round(track.bottom() + 28), label)
            painter.setPen(QPen(QColor("#586071"), 1))

    def _draw_segment(self, painter: QPainter, track: QRectF) -> None:
        in_x = self._time_to_x(self._segment.start_seconds)
        out_x = self._time_to_x(self._segment.end_seconds)
        selected = QRectF(in_x, track.top(), max(4.0, out_x - in_x), track.height())
        painter.setPen(QPen(QColor("#d4b04f"), 1))
        painter.setBrush(QColor("#3d3422"))
        painter.drawRoundedRect(selected, 4, 4)
        painter.setPen(QPen(QColor("#e6c15a"), 1))
        painter.drawLine(QPoint(round(in_x), round(track.top())), QPoint(round(in_x), round(track.bottom())))
        painter.drawLine(QPoint(round(out_x), round(track.top())), QPoint(round(out_x), round(track.bottom())))
        painter.setBrush(QColor("#e6c15a"))
        painter.drawRoundedRect(self._in_handle_rect(track, in_x), 2, 2)
        painter.drawRoundedRect(self._out_handle_rect(track, out_x), 2, 2)

    def _draw_playhead(self, painter: QPainter, track: QRectF) -> None:
        x = self._time_to_x(self._playhead_seconds)
        painter.setPen(QPen(QColor("#74b8ff"), 1))
        painter.drawLine(QPoint(round(x), round(track.top() - 4)), QPoint(round(x), round(track.bottom() + 4)))
        painter.setBrush(QColor("#74b8ff"))
        painter.drawEllipse(QRectF(x - 3, track.center().y() - 3, 6, 6))

    def _emit_segment(self, segment: TestSegment) -> None:
        self._segment = self._clamp_segment(segment)
        self.segmentChanged.emit(self._segment)
        self.update()

    def _time_to_x(self, seconds: float) -> float:
        rect = self.rect().adjusted(18, 12, -18, -16)
        start, end = self._visible_start_end()
        visible_duration = max(0.1, end - start)
        clamped = min(max(start, seconds), end)
        return rect.left() + ((clamped - start) / visible_duration) * rect.width()

    def _x_to_time(self, x: float) -> float:
        rect = self.rect().adjusted(18, 12, -18, -16)
        if rect.width() <= 0:
            return self._visible_start_end()[0]
        ratio = min(1.0, max(0.0, (x - rect.left()) / rect.width()))
        start, end = self._visible_start_end()
        return start + ratio * max(0.1, end - start)

    def _track_rect(self) -> QRectF:
        rect = self.rect().adjusted(18, 12, -18, -16)
        return QRectF(rect.left(), rect.center().y() - 9, rect.width(), 18)

    def _in_handle_rect(self, track: QRectF, x: float) -> QRectF:
        return QRectF(x - 4, track.top() - 20, 8, 14)

    def _out_handle_rect(self, track: QRectF, x: float) -> QRectF:
        return QRectF(x - 4, track.bottom() + 6, 8, 14)

    def _playhead_handle_rect(self, track: QRectF, x: float) -> QRectF:
        return QRectF(x - 6, track.top() - 10, 12, track.height() + 20)

    def _clamp_time(self, seconds: float) -> float:
        if self._duration_seconds <= 0:
            return max(0.0, seconds)
        return min(max(0.0, seconds), self._duration_seconds)

    def _clamp_visible_time(self, seconds: float) -> float:
        seconds = self._clamp_time(seconds)
        start, end = self._visible_start_end()
        return min(max(start, seconds), end)

    def _clamp_segment(self, segment: TestSegment) -> TestSegment:
        if self._duration_seconds <= 0:
            return segment
        start = self._clamp_time(segment.start_seconds)
        end = self._clamp_time(segment.end_seconds)
        if end <= start:
            end = min(self._duration_seconds, start + 0.1)
        return replace(segment, start_seconds=start, end_seconds=end)

    def _visible_start_end(self) -> tuple[float, float]:
        if self._display_start_seconds is not None and self._display_end_seconds is not None:
            return self._display_start_seconds, max(self._display_start_seconds + 0.1, self._display_end_seconds)
        duration = self._duration_seconds or max(self._segment.end_seconds, 1.0)
        return 0.0, max(0.1, duration)

    def _clamp_display_window(self) -> None:
        if self._display_start_seconds is None or self._display_end_seconds is None:
            return
        self.set_display_window(self._display_start_seconds, self._display_end_seconds, self._show_segment_handles)


def _format_time(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    minutes, second = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minute:02d}:{second:02d}"
    return f"{minute:d}:{second:02d}"
