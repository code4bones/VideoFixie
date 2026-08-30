from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from videofixie.domain.backends import (
    VAPOURSYNTH_BACKEND_SLUG,
    VIDEO2X_BACKEND_SLUG,
    ProcessingBackendDescriptor,
    bundled_processing_backends,
)
from videofixie.domain.output_presets import OutputPreset
from videofixie.domain.profiles import ProcessingProfile
from videofixie.domain.settings import AppSettings
from videofixie.services.environment import MachineEnvironment


class SettingsDialog(QDialog):
    def __init__(
        self,
        settings: AppSettings,
        profiles: tuple[ProcessingProfile, ...],
        output_presets: tuple[OutputPreset, ...],
        environment: MachineEnvironment | None,
        parent: QWidget | None = None,
        *,
        processing_backends: tuple[ProcessingBackendDescriptor, ...] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(720, 360)
        self.processing_backends = processing_backends or bundled_processing_backends()

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.backend_combo = QComboBox()
        for backend in self.processing_backends:
            self.backend_combo.addItem(backend.name, backend.slug)
        backend_index = self.backend_combo.findData(settings.active_backend_slug)
        if backend_index < 0:
            self.backend_combo.addItem(f"{settings.active_backend_slug} (not available)", settings.active_backend_slug)
            backend_index = self.backend_combo.findData(settings.active_backend_slug)
        if backend_index >= 0:
            self.backend_combo.setCurrentIndex(backend_index)
        form.addRow("Processing backend", self.backend_combo)

        self.ffmpeg_path_edit = QLineEdit(settings.ffmpeg_path or "")
        self.ffprobe_path_edit = QLineEdit(settings.ffprobe_path or "")
        self.video2x_path_edit = QLineEdit(settings.video2x_path or "")
        self.vapoursynth_python_path_edit = QLineEdit(settings.vapoursynth_python_path or "")
        self.vspipe_path_edit = QLineEdit(settings.vspipe_path or "")
        self.output_directory_edit = QLineEdit(settings.output_directory)
        self.cache_directory_edit = QLineEdit(settings.cache_directory)
        self.models_directory_edit = QLineEdit(settings.models_directory)

        form.addRow("FFmpeg", self._file_path_row(self.ffmpeg_path_edit))
        form.addRow("FFprobe", self._file_path_row(self.ffprobe_path_edit))
        form.addRow("Output directory", self._directory_path_row(self.output_directory_edit))
        form.addRow("Cache directory", self._directory_path_row(self.cache_directory_edit))
        form.addRow("Managed models directory", self._directory_path_row(self.models_directory_edit))

        self.video2x_group = QGroupBox("Video2X")
        video2x_form = QFormLayout(self.video2x_group)
        layout.addWidget(self.video2x_group)
        video2x_form.addRow("Executable/AppImage", self._file_path_row(self.video2x_path_edit))

        self.gpu_combo = QComboBox()
        self.gpu_combo.addItem("Auto", None)
        if environment and environment.video2x_capabilities:
            for device in environment.video2x_capabilities.devices:
                self.gpu_combo.addItem(f"{device.index}. {device.name}", device.index)
        if settings.preferred_gpu_index is not None and self.gpu_combo.findData(settings.preferred_gpu_index) < 0:
            self.gpu_combo.addItem(f"{settings.preferred_gpu_index}. Configured", settings.preferred_gpu_index)
        gpu_index = self.gpu_combo.findData(settings.preferred_gpu_index)
        if gpu_index >= 0:
            self.gpu_combo.setCurrentIndex(gpu_index)
        video2x_form.addRow("Preferred GPU", self.gpu_combo)

        self.vapoursynth_group = QGroupBox("VapourSynth")
        vapoursynth_form = QFormLayout(self.vapoursynth_group)
        layout.addWidget(self.vapoursynth_group)
        vapoursynth_form.addRow("Python", self._file_path_row(self.vapoursynth_python_path_edit))
        vapoursynth_form.addRow("vspipe", self._file_path_row(self.vspipe_path_edit))

        self.default_profile_combo = QComboBox()
        for profile in profiles:
            self.default_profile_combo.addItem(profile.name, profile.slug)
        profile_index = self.default_profile_combo.findData(settings.default_profile_slug)
        if profile_index >= 0:
            self.default_profile_combo.setCurrentIndex(profile_index)
        form.addRow("Default profile", self.default_profile_combo)

        self.default_output_combo = QComboBox()
        for output_preset in output_presets:
            self.default_output_combo.addItem(output_preset.name, output_preset.slug)
        output_index = self.default_output_combo.findData(settings.default_output_preset_slug)
        if output_index >= 0:
            self.default_output_combo.setCurrentIndex(output_index)
        form.addRow("Default output", self.default_output_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.backend_combo.currentIndexChanged.connect(self._update_backend_controls)
        self._update_backend_controls()

    def settings(self) -> AppSettings:
        return AppSettings(
            active_backend_slug=str(self.backend_combo.currentData() or VIDEO2X_BACKEND_SLUG),
            ffmpeg_path=_optional_text(self.ffmpeg_path_edit.text()),
            ffprobe_path=_optional_text(self.ffprobe_path_edit.text()),
            video2x_path=_optional_text(self.video2x_path_edit.text()),
            vapoursynth_python_path=_optional_text(self.vapoursynth_python_path_edit.text()),
            vspipe_path=_optional_text(self.vspipe_path_edit.text()),
            output_directory=_required_text(self.output_directory_edit.text(), "outputs"),
            cache_directory=_required_text(self.cache_directory_edit.text(), "cache"),
            models_directory=_required_text(self.models_directory_edit.text(), "models"),
            preferred_gpu_index=_optional_int(self.gpu_combo.currentData()),
            default_profile_slug=str(self.default_profile_combo.currentData()),
            default_output_preset_slug=str(self.default_output_combo.currentData()),
        )

    def _update_backend_controls(self) -> None:
        active_backend = self.backend_combo.currentData()
        self.video2x_group.setVisible(active_backend == VIDEO2X_BACKEND_SLUG)
        self.vapoursynth_group.setVisible(active_backend == VAPOURSYNTH_BACKEND_SLUG)

    def _file_path_row(self, line_edit: QLineEdit) -> QWidget:
        return self._path_row(line_edit, browse=lambda: self._browse_file(line_edit))

    def _directory_path_row(self, line_edit: QLineEdit) -> QWidget:
        return self._path_row(line_edit, browse=lambda: self._browse_directory(line_edit))

    def _path_row(self, line_edit: QLineEdit, browse) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(line_edit, 1)
        button = QPushButton("Browse")
        button.clicked.connect(browse)
        layout.addWidget(button)
        return row

    def _browse_file(self, line_edit: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select executable", line_edit.text() or ".")
        if path:
            line_edit.setText(path)

    def _browse_directory(self, line_edit: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select directory", line_edit.text() or ".")
        if path:
            line_edit.setText(path)


def _optional_text(value: str) -> str | None:
    text = value.strip()
    return text or None


def _required_text(value: str, fallback: str) -> str:
    text = _optional_text(value)
    return text if text is not None else fallback


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
