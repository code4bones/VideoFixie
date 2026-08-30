from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QDialog, QFormLayout, QLabel, QPlainTextEdit, QTabWidget, QVBoxLayout, QWidget

from videofixie.domain.media import MediaInfo
from videofixie.domain.output_presets import OutputPreset
from videofixie.domain.profiles import ProcessingProfile
from videofixie.services.environment import MachineEnvironment


class PropertiesDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Properties")
        self.resize(900, 640)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.source_tab = QWidget()
        self.source_layout = QFormLayout(self.source_tab)
        self.file_label = QLabel("-")
        self.duration_label = QLabel("-")
        self.resolution_label = QLabel("-")
        self.fps_label = QLabel("-")
        self.codec_label = QLabel("-")
        self.scan_label = QLabel("-")
        self.audio_label = QLabel("-")
        self.source_layout.addRow("File", self.file_label)
        self.source_layout.addRow("Duration", self.duration_label)
        self.source_layout.addRow("Resolution", self.resolution_label)
        self.source_layout.addRow("FPS", self.fps_label)
        self.source_layout.addRow("Codec", self.codec_label)
        self.source_layout.addRow("Scan", self.scan_label)
        self.source_layout.addRow("Audio", self.audio_label)
        self.tabs.addTab(self.source_tab, "Source")

        self.environment_tab = QWidget()
        environment_layout = QFormLayout(self.environment_tab)
        self.ffmpeg_label = QLabel("-")
        self.ffprobe_label = QLabel("-")
        self.video2x_label = QLabel("-")
        self.gpu_label = QLabel("-")
        environment_layout.addRow("FFmpeg", self.ffmpeg_label)
        environment_layout.addRow("FFprobe", self.ffprobe_label)
        environment_layout.addRow("Video2X", self.video2x_label)
        environment_layout.addRow("Preferred GPU", self.gpu_label)
        self.tabs.addTab(self.environment_tab, "Environment")

        self.profile_tab = QWidget()
        profile_layout = QVBoxLayout(self.profile_tab)
        self.profile_summary_label = QLabel("-")
        self.profile_summary_label.setWordWrap(True)
        profile_layout.addWidget(self.profile_summary_label)
        profile_layout.addStretch(1)
        self.tabs.addTab(self.profile_tab, "Profile")

        self.commands_tab = QWidget()
        commands_layout = QVBoxLayout(self.commands_tab)
        self.command_text = QPlainTextEdit()
        self.command_text.setReadOnly(True)
        self.command_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        commands_layout.addWidget(self.command_text)
        self.tabs.addTab(self.commands_tab, "Commands")

        self.setStyleSheet(
            """
            QDialog, QWidget { background: #17191f; color: #e8edf5; }
            QLabel { color: #e8edf5; }
            QPlainTextEdit {
                background: #222732; color: #e8edf5; border: 1px solid #3d4554; border-radius: 4px; padding: 4px;
            }
            QTabWidget::pane { border: 1px solid #343a46; }
            QTabBar::tab { background: #222732; color: #b7c0cf; padding: 7px 12px; border: 1px solid #343a46; }
            QTabBar::tab:selected { background: #303849; color: #ffffff; }
            QGroupBox { border: 1px solid #343a46; border-radius: 6px; margin-top: 18px; padding: 8px; }
            """
        )

    def update_data(
        self,
        media: MediaInfo | None,
        source_path: Path | None,
        environment: MachineEnvironment | None,
        profile: ProcessingProfile,
        output_preset: OutputPreset,
        profile_summary: str,
        command_log: str,
    ) -> None:
        self._update_source(media, source_path)
        self._update_environment(environment)
        self.profile_summary_label.setText(
            f"{profile.name} ({profile.slug})\n"
            f"{profile_summary}\n\n"
            f"Output: {output_preset.name} ({output_preset.slug})"
        )
        self.command_text.setPlainText(command_log)

    def _update_source(self, media: MediaInfo | None, source_path: Path | None) -> None:
        if media is None:
            self.file_label.setText("No file selected")
            self.duration_label.setText("-")
            self.resolution_label.setText("-")
            self.fps_label.setText("-")
            self.codec_label.setText("-")
            self.scan_label.setText("-")
            self.audio_label.setText("-")
            return
        video = media.primary_video
        self.file_label.setText(source_path.name if source_path else str(media.path))
        self.duration_label.setText(_format_seconds(media.duration_seconds))
        if video is None:
            self.resolution_label.setText("-")
            self.fps_label.setText("-")
            self.codec_label.setText("-")
            self.scan_label.setText("-")
        else:
            self.resolution_label.setText(f"{video.width}x{video.height}")
            self.fps_label.setText("-" if video.fps is None else f"{video.fps:.3g}")
            self.codec_label.setText(video.codec_name or "unknown")
            self.scan_label.setText(video.scan_type)
        self.audio_label.setText(str(len(media.audio_streams)))

    def _update_environment(self, environment: MachineEnvironment | None) -> None:
        if environment is None:
            self.ffmpeg_label.setText("-")
            self.ffprobe_label.setText("-")
            self.video2x_label.setText("-")
            self.gpu_label.setText("-")
            return
        self.ffmpeg_label.setText(_tool_text(environment.ffmpeg.available, environment.ffmpeg.path, environment.ffmpeg.version))
        self.ffprobe_label.setText(_tool_text(environment.ffprobe.available, environment.ffprobe.path, environment.ffprobe.version))
        self.video2x_label.setText(_tool_text(environment.video2x.available, environment.video2x.path, environment.video2x.version))
        if environment.preferred_gpu is None:
            self.gpu_label.setText("-")
        else:
            self.gpu_label.setText(f"{environment.preferred_gpu.index}. {environment.preferred_gpu.name}")


def _tool_text(available: bool, path: str | None, version: str | None) -> str:
    state = "ok" if available else "missing"
    details = version or path or ""
    return f"{state} {details}".strip()


def _format_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    minutes, second = divmod(int(round(seconds)), 60)
    hours, minute = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minute:02d}:{second:02d}"
    return f"{minute}:{second:02d}"
