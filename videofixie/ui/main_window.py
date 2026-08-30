from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QEvent, QThread, QTimer, QUrl, Qt, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QFrame,
    QScrollArea,
    QSizePolicy,
    QDoubleSpinBox,
    QSpinBox,
    QStyle,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from videofixie.domain.backends import VIDEO2X_BACKEND_SLUG, bundled_processing_backends
from videofixie.domain.jobs import TestSegment, TestSegmentKind
from videofixie.domain.media import MediaInfo
from videofixie.domain.output_presets import OutputPreset, bundled_output_presets
from videofixie.domain.profiles import ProcessingProfile
from videofixie.domain.release_presets import ReleasePreset
from videofixie.domain.settings import AppSettings
from videofixie.services.app import VideoFixieService
from videofixie.services.environment import MachineEnvironment
from videofixie.services.history import PreviewResult, SavedCut
from videofixie.ui.benchmark_worker import BenchmarkVariantRun, BenchmarkWorker
from videofixie.ui.preview_worker import PreviewWorker, successful_output_path
from videofixie.ui.properties_dialog import PropertiesDialog
from videofixie.ui.release_preset_wizard import ReleasePresetWizard
from videofixie.ui.settings_dialog import SettingsDialog
from videofixie.ui.timeline import SegmentTimeline
from videofixie.ui.timecode import TimecodeEdit


class MainWindow(QMainWindow):
    def __init__(self, service: VideoFixieService | None = None) -> None:
        super().__init__()
        self.service = service or VideoFixieService(Path.cwd())
        self.environment: MachineEnvironment | None = None
        self.media: MediaInfo | None = None
        self.source_path: Path | None = None
        self.profiles = self.service.profiles()
        self.output_presets = self.service.output_presets() if hasattr(self.service, "output_presets") else bundled_output_presets()
        self.processing_backends = (
            self.service.processing_backends()
            if hasattr(self.service, "processing_backends")
            else bundled_processing_backends()
        )
        self.settings = self.service.load_settings() if hasattr(self.service, "load_settings") else AppSettings()
        self.profile_summary_text = ""
        self.current_release_preset: ReleasePreset | None = None
        self._syncing_segment_controls = False
        self.current_job = None
        self.current_plan_segment: TestSegment | None = None
        self.running_preview_job = None
        self.running_preview_segment: TestSegment | None = None
        self.processed_output_path: Path | None = None
        self.processed_segment: TestSegment | None = None
        self.saved_cuts: tuple[SavedCut, ...] = ()
        self.saved_results: tuple[PreviewResult, ...] = ()
        self.large_split_window: LargeSplitWindow | None = None
        self.properties_dialog: PropertiesDialog | None = None
        self.preview_thread: QThread | None = None
        self.preview_worker: PreviewWorker | None = None
        self.benchmark_plan = None
        self.benchmark_thread: QThread | None = None
        self.benchmark_worker: BenchmarkWorker | None = None
        self.variant_tiles: list[VariantTile] = []
        self.benchmark_outputs: dict[int, Path] = {}
        self._syncing_playhead = False
        self._restarting_playback = False
        self._suppress_planning = True

        self.setWindowTitle("VideoFixie")
        self.resize(1280, 820)

        self._build_actions()
        self._build_ui()
        self._apply_style()
        try:
            self._load_environment()
        finally:
            self._suppress_planning = False
        self._update_profile_summary()

    def _build_actions(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        open_action = toolbar.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton), "Open")
        open_action.triggered.connect(self.open_source)

        plan_action = toolbar.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView), "Plan Preview")
        plan_action.triggered.connect(self.plan_preview)

        self.run_action = toolbar.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay), "Run Preview")
        self.run_action.triggered.connect(self.toggle_preview)

        self.large_view_action = toolbar.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarMaxButton), "Large View")
        self.large_view_action.triggered.connect(self.open_large_view)

        release_action = toolbar.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton), "Release")
        release_action.triggered.connect(self.open_release_preset_wizard)

        properties_action = toolbar.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView), "Properties")
        properties_action.triggered.connect(self.open_properties)

        settings_action = toolbar.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView), "Settings")
        settings_action.triggered.connect(self.open_settings)

        refresh_action = toolbar.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload), "Refresh Env")
        refresh_action.triggered.connect(self._load_environment)

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(10, 8, 10, 10)
        root_layout.setSpacing(8)
        self.setCentralWidget(root)

        top_row = QHBoxLayout()
        self.profile_combo = QComboBox()
        for profile in self.profiles:
            self.profile_combo.addItem(profile.name, profile.slug)
        self.profile_combo.currentIndexChanged.connect(self._update_profile_summary)

        self.output_combo = QComboBox()
        for output_preset in self.output_presets:
            self.output_combo.addItem(output_preset.name, output_preset.slug)
        self.output_combo.currentIndexChanged.connect(self._update_profile_summary)

        self.gpu_combo = QComboBox()
        top_row.addWidget(QLabel("Profile"))
        top_row.addWidget(self.profile_combo, 1)
        top_row.addWidget(QLabel("Output"))
        top_row.addWidget(self.output_combo, 1)
        top_row.addWidget(QLabel("GPU"))
        top_row.addWidget(self.gpu_combo, 1)
        root_layout.addLayout(top_row)

        self.tabs = QTabWidget()
        self.video_widget = QVideoWidget()
        self.video_widget.installEventFilter(self)
        self.tabs.addTab(self.video_widget, "Original")
        self.processed_video_widget = QVideoWidget()
        self.processed_video_widget.installEventFilter(self)
        self.tabs.addTab(self.processed_video_widget, "Processed")
        split_widget = QWidget()
        split_layout = QHBoxLayout(split_widget)
        split_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.setSpacing(8)
        self.split_original_widget = QVideoWidget()
        self.split_processed_widget = QVideoWidget()
        split_layout.addWidget(self.split_original_widget, 1)
        split_layout.addWidget(self.split_processed_widget, 1)
        self.tabs.addTab(split_widget, "Split")

        self.variants_tab = QWidget()
        variants_layout = QVBoxLayout(self.variants_tab)
        variants_layout.setContentsMargins(8, 8, 8, 8)
        variants_layout.setSpacing(8)
        variants_toolbar = QHBoxLayout()
        self.run_variants_button = QPushButton("Run Variants")
        self.apply_variant_button = QPushButton("Apply Selected")
        self.variant_parallel_spin = QSpinBox()
        self.variant_parallel_spin.setRange(1, 3)
        self.variant_parallel_spin.setValue(3)
        self.variant_parallel_spin.setToolTip("Maximum active Video2X variants")
        self.variant_status_label = QLabel("No variants planned")
        variants_toolbar.addWidget(self.run_variants_button)
        variants_toolbar.addWidget(self.apply_variant_button)
        variants_toolbar.addWidget(QLabel("Parallel"))
        variants_toolbar.addWidget(self.variant_parallel_spin)
        variants_toolbar.addWidget(self.variant_status_label, 1)
        variants_layout.addLayout(variants_toolbar)
        self.variant_scroll = QScrollArea()
        self.variant_scroll.setWidgetResizable(True)
        self.variant_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.variant_grid_widget = QWidget()
        self.variant_grid_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.variant_grid = QGridLayout(self.variant_grid_widget)
        self.variant_grid.setContentsMargins(0, 0, 0, 0)
        self.variant_grid.setSpacing(8)
        self.variant_scroll.setWidget(self.variant_grid_widget)
        variants_layout.addWidget(self.variant_scroll, 1)
        self.tabs.addTab(self.variants_tab, "Variants")
        self.tabs.currentChanged.connect(self._on_active_tab_changed)
        root_layout.addWidget(self.tabs, 1)

        self.command_text = QPlainTextEdit(self)
        self.command_text.setReadOnly(True)
        self.command_text.setPlaceholderText("Planned commands")
        self.command_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.command_text.hide()

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video_widget)
        self.player.positionChanged.connect(self._on_player_position)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.player.mediaStatusChanged.connect(lambda status: self._on_media_status_changed(self.player, status))
        self.processed_player = QMediaPlayer(self)
        self.processed_audio = QAudioOutput(self)
        self.processed_player.setAudioOutput(self.processed_audio)
        self.processed_player.setVideoOutput(self.processed_video_widget)
        self.processed_player.positionChanged.connect(self._on_processed_position)
        self.processed_player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.processed_player.mediaStatusChanged.connect(lambda status: self._on_media_status_changed(self.processed_player, status))
        self.split_original_player = QMediaPlayer(self)
        self.split_original_audio = QAudioOutput(self)
        self.split_original_audio.setMuted(True)
        self.split_original_player.setAudioOutput(self.split_original_audio)
        self.split_original_player.setVideoOutput(self.split_original_widget)
        self.split_original_player.positionChanged.connect(self._on_split_original_position)
        self.split_original_player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.split_original_player.mediaStatusChanged.connect(lambda status: self._on_media_status_changed(self.split_original_player, status))
        self.split_processed_player = QMediaPlayer(self)
        self.split_processed_audio = QAudioOutput(self)
        self.split_processed_player.setAudioOutput(self.split_processed_audio)
        self.split_processed_player.setVideoOutput(self.split_processed_widget)
        self.split_processed_player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.split_processed_player.mediaStatusChanged.connect(lambda status: self._on_media_status_changed(self.split_processed_player, status))

        timeline_panel = QWidget()
        timeline_layout = QVBoxLayout(timeline_panel)
        timeline_layout.setContentsMargins(0, 0, 0, 0)
        self.timeline = SegmentTimeline()
        self.timeline.segmentChanged.connect(self._on_timeline_segment)
        self.timeline.playheadChanged.connect(self._on_timeline_playhead)
        timeline_layout.addWidget(self.timeline)

        segment_controls = QGridLayout()
        self.segment_label = QComboBox()
        self.segment_label.setEditable(True)
        self.segment_label.addItems(["Preview", "Face", "Motion", "Detail", "Dark"])
        self.segment_kind = QComboBox()
        for kind in TestSegmentKind:
            self.segment_kind.addItem(kind.value, kind.value)
        self.in_spin = TimecodeEdit()
        self.out_spin = TimecodeEdit()
        self.duration_spin = _seconds_spin()
        self.duration_spin.setValue(15.0)
        self.set_in_button = QPushButton("Set IN")
        self.set_out_button = QPushButton("Set OUT")
        self.play_button = QPushButton("Play")
        self.large_view_button = QPushButton("Large View")
        self.save_cut_button = QPushButton("Save Cut")
        self.cut_combo = QComboBox()
        self.load_cut_button = QPushButton("Load Cut")
        self.result_combo = QComboBox()
        self.load_result_button = QPushButton("Load Result")
        self.run_preview_button = QPushButton("Run Preview")

        segment_controls.addWidget(QLabel("Segment"), 0, 0)
        segment_controls.addWidget(self.segment_label, 0, 1)
        segment_controls.addWidget(QLabel("Kind"), 0, 2)
        segment_controls.addWidget(self.segment_kind, 0, 3)
        segment_controls.addWidget(QLabel("IN"), 1, 0)
        segment_controls.addWidget(self.in_spin, 1, 1)
        segment_controls.addWidget(QLabel("OUT"), 1, 2)
        segment_controls.addWidget(self.out_spin, 1, 3)
        segment_controls.addWidget(QLabel("Duration"), 1, 4)
        segment_controls.addWidget(self.duration_spin, 1, 5)
        segment_controls.addWidget(self.set_in_button, 0, 4)
        segment_controls.addWidget(self.set_out_button, 0, 5)
        segment_controls.addWidget(self.play_button, 0, 6, 2, 1)
        segment_controls.addWidget(self.large_view_button, 0, 7)
        segment_controls.addWidget(self.save_cut_button, 1, 7)
        segment_controls.addWidget(QLabel("Cut"), 2, 0)
        segment_controls.addWidget(self.cut_combo, 2, 1, 1, 5)
        segment_controls.addWidget(self.load_cut_button, 2, 6)
        segment_controls.addWidget(QLabel("Result"), 3, 0)
        segment_controls.addWidget(self.result_combo, 3, 1, 1, 5)
        segment_controls.addWidget(self.load_result_button, 3, 6)
        segment_controls.addWidget(self.run_preview_button, 0, 8, 4, 1)
        timeline_layout.addLayout(segment_controls)

        progress_row = QHBoxLayout()
        self.preview_progress = QProgressBar()
        self.preview_progress.setRange(0, 1000)
        self.preview_progress.setValue(0)
        self.preview_status = QLabel("Preview idle")
        progress_row.addWidget(self.preview_progress, 1)
        progress_row.addWidget(self.preview_status)
        timeline_layout.addLayout(progress_row)
        root_layout.addWidget(timeline_panel)

        self.in_spin.valueChanged.connect(self._on_segment_controls_changed)
        self.out_spin.valueChanged.connect(self._on_segment_controls_changed)
        self.duration_spin.valueChanged.connect(self._on_duration_changed)
        self.segment_label.currentTextChanged.connect(self._on_segment_controls_changed)
        self.segment_kind.currentIndexChanged.connect(self._on_segment_controls_changed)
        self.set_in_button.clicked.connect(self._set_in_from_playhead)
        self.set_out_button.clicked.connect(self._set_out_from_playhead)
        self.play_button.clicked.connect(self.toggle_playback)
        self.large_view_button.clicked.connect(self.open_large_view)
        self.save_cut_button.clicked.connect(self.save_current_cut)
        self.load_cut_button.clicked.connect(self.load_selected_cut)
        self.load_result_button.clicked.connect(self.load_selected_result)
        self.run_preview_button.clicked.connect(self.toggle_preview)
        self.run_variants_button.clicked.connect(self.toggle_benchmark)
        self.apply_variant_button.clicked.connect(self.apply_selected_variant)

        self._apply_settings_defaults_to_controls()
        self._update_large_view_state()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #17191f; color: #e8edf5; }
            QToolBar { background: #20242c; border: 0; spacing: 6px; padding: 4px; }
            QGroupBox { border: 1px solid #343a46; border-radius: 6px; margin-top: 18px; padding: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #b7c0cf; }
            QLabel { color: #e8edf5; }
            QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit, QPlainTextEdit {
                background: #222732; color: #e8edf5; border: 1px solid #3d4554; border-radius: 4px; padding: 4px;
            }
            QPushButton { background: #2d3543; color: #eef3fb; border: 1px solid #495366; border-radius: 4px; padding: 6px 10px; }
            QPushButton:hover { background: #384254; }
            QPushButton:disabled { color: #738096; background: #242a35; border-color: #313846; }
            QTabWidget::pane { border: 1px solid #343a46; }
            QTabBar::tab { background: #222732; color: #b7c0cf; padding: 7px 12px; border: 1px solid #343a46; }
            QTabBar::tab:selected { background: #303849; color: #ffffff; }
            """
        )

    def open_source(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open video",
            str(Path.cwd()),
            "Video files (*.mp4 *.mkv *.mov *.avi *.webm);;All files (*)",
        )
        if path:
            self.load_source(Path(path))

    def open_settings(self) -> None:
        dialog = SettingsDialog(
            self.settings,
            self.profiles,
            self.output_presets,
            self.environment,
            self,
            processing_backends=self.processing_backends,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        old_backend = self.settings.active_backend_slug
        self._suppress_planning = True
        try:
            self.settings = dialog.settings()
            if hasattr(self.service, "save_settings"):
                self.service.save_settings(self.settings)
            self._apply_settings_defaults_to_controls()
            if old_backend != self.settings.active_backend_slug:
                self._select_first_compatible_profile()
            self._load_environment()
        finally:
            self._suppress_planning = False
        self._update_profile_summary()

    def open_properties(self) -> None:
        if self.properties_dialog is None:
            self.properties_dialog = PropertiesDialog(self)
            self.properties_dialog.finished.connect(lambda _result: self._clear_properties_dialog())
        self._refresh_properties_dialog()
        self.properties_dialog.show()
        self.properties_dialog.raise_()
        self.properties_dialog.activateWindow()

    def open_release_preset_wizard(self) -> None:
        wizard = ReleasePresetWizard(self.media, self)
        if wizard.exec() != QDialog.DialogCode.Accepted:
            return
        self.current_release_preset = wizard.release_preset()
        self.command_text.appendPlainText(
            "\nRelease preset:\n"
            + "\n".join(self.current_release_preset.human_summary_lines())
            + "\n\nRelease technical settings:\n"
            + "\n".join(self.current_release_preset.technical_summary_lines())
        )
        self._refresh_properties_dialog()
        self.preview_status.setText(f"Release preset ready: {self.current_release_preset.name}")

    def load_source(self, path: Path) -> None:
        try:
            self.media = self.service.analyze_source(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Source analysis failed", str(exc))
            return

        self.source_path = path
        self._suppress_planning = True
        try:
            self.player.setSource(QUrl.fromLocalFile(str(path)))
            self.split_original_player.setSource(QUrl.fromLocalFile(str(path)))
            self.processed_player.setSource(QUrl())
            self.split_processed_player.setSource(QUrl())
            self._clear_variant_tiles()
            self.benchmark_plan = None
            self.benchmark_outputs = {}
            self.current_plan_segment = None
            self.running_preview_job = None
            self.running_preview_segment = None
            self.processed_output_path = None
            self.processed_segment = None
            self.saved_cuts = ()
            self.saved_results = ()
            self._update_large_view_state()
            self._update_source_info()
            duration = self.media.duration_seconds or 0.0
            self.timeline.set_duration(duration)
            self.timeline.clear_display_window()
            end = min(duration, 15.0) if duration else 15.0
            saved_cut = self._load_latest_saved_cut(path)
            if saved_cut is not None:
                self._apply_saved_cut(saved_cut)
            else:
                self._set_segment(TestSegment("Preview", 0.0, end, TestSegmentKind.CUSTOM))
            self._select_first_compatible_profile()
            self._refresh_saved_cuts()
            self._refresh_saved_results()
        finally:
            self._suppress_planning = False
        self._update_profile_summary()

    def plan_preview(self) -> None:
        if self._suppress_planning:
            return
        if self.source_path is None:
            self.command_text.setPlainText("Open a source video to plan preview commands.")
            self._refresh_properties_dialog()
            return
        if self.media is None or self.environment is None:
            self.command_text.setPlainText("Source or environment is not ready.")
            self._refresh_properties_dialog()
            return
        profile = self._selected_profile()
        output_preset = self._selected_output_preset()
        segment = self._current_segment()
        try:
            plan = self.service.plan_preview_with_context(
                source_path=self.source_path,
                work_dir=self._preview_work_dir(),
                profile=profile,
                segment=segment,
                media=self.media,
                environment=self.environment,
                device_index=self._selected_device_index(),
                output_preset=output_preset,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Preview planning failed", str(exc))
            return

        self.current_job = plan.job
        self.current_plan_segment = plan.segment

        lines = [
            f"Profile: {plan.profile.name} ({plan.profile.slug})",
            (
                f"Output preset: {plan.output_preset.name} ({plan.output_preset.slug}) | "
                f"{plan.output_preset.codec} CRF {plan.output_preset.crf} preset {plan.output_preset.encoder_preset}"
            ),
            f"Segment: {plan.segment.label} [{plan.segment.kind.value}] {plan.segment.start_seconds:.3f}-{plan.segment.end_seconds:.3f}s",
            f"Output: {plan.job.output_path}",
        ]
        for index, stage in enumerate(plan.job.stages, start=1):
            lines.extend(["", f"Stage {index}: {stage.label}", stage.command.display()])
            for generated_file in stage.generated_files:
                description = generated_file.description or "Generated file"
                lines.extend(["", f"{description}: {generated_file.path}", generated_file.content.rstrip()])
        self.command_text.setPlainText("\n".join(lines))
        self._refresh_properties_dialog()

    def toggle_playback(self) -> None:
        if self._active_player_is_playing():
            self.pause_active()
        else:
            self.play_active()

    def play_active(self) -> None:
        self._refresh_video_outputs()
        if self.tabs.currentIndex() == 0:
            self.processed_player.pause()
            self.split_original_player.pause()
            self.split_processed_player.pause()
            self.player.play()
        elif self.tabs.currentIndex() == 1:
            if self.processed_output_path is None:
                return
            self.player.pause()
            self.split_original_player.pause()
            self.split_processed_player.pause()
            self._seek_processed_from_source_time(self.timeline_playhead_seconds())
            self.processed_player.play()
        elif self.tabs.currentIndex() == 2:
            if self.processed_output_path is None:
                return
            self.player.pause()
            self.processed_player.pause()
            self._seek_split_from_source_time(self.timeline_playhead_seconds())
            self.split_processed_player.play()
            self.split_original_player.play()
        else:
            return
        self._update_playback_button()

    def pause_active(self) -> None:
        self.player.pause()
        self.processed_player.pause()
        self.split_original_player.pause()
        self.split_processed_player.pause()
        self._update_playback_button()

    def toggle_preview(self) -> None:
        if self.preview_thread is None:
            self.run_preview()
        else:
            self.cancel_preview()

    def save_current_cut(self) -> None:
        if self.source_path is None:
            self.preview_status.setText("Open a source video before saving a cut")
            return
        segment = self._current_segment()
        name, accepted = QInputDialog.getText(
            self,
            "Save Cut",
            "Cut name",
            QLineEdit.EchoMode.Normal,
            segment.label,
        )
        if not accepted:
            return
        name = name.strip()
        if not name:
            QMessageBox.warning(self, "Could not save cut", "Cut name must not be empty")
            return
        segment = TestSegment(
            label=name,
            kind=segment.kind,
            start_seconds=segment.start_seconds,
            end_seconds=segment.end_seconds,
        )
        self._suppress_planning = True
        try:
            self._set_segment(segment)
        finally:
            self._suppress_planning = False
        try:
            saved_cut = self.service.save_source_segment(
                self.source_path,
                segment,
                self._selected_profile().slug,
                self._selected_output_preset().slug,
                backend_slug=self.settings.active_backend_slug,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not save cut", str(exc))
            return
        self.preview_status.setText(f"Cut saved: {saved_cut.segment.label}")
        self._refresh_saved_cuts()
        self._select_saved_cut(saved_cut)
        self._refresh_saved_results()
        self._update_profile_summary()

    def load_selected_cut(self) -> None:
        cut = self._prompt_for_cut_to_load()
        if cut is None:
            self.preview_status.setText("No saved cut selected")
            return
        self._suppress_planning = True
        try:
            self._apply_saved_cut(cut)
            self._select_first_compatible_profile()
        finally:
            self._suppress_planning = False
        self._update_profile_summary()
        self.preview_status.setText(f"Loaded cut: {cut.segment.label}")

    def _prompt_for_cut_to_load(self) -> SavedCut | None:
        cuts = tuple(cut for cut in self.saved_cuts if isinstance(cut, SavedCut))
        if not cuts:
            return None
        labels = [_cut_text(cut) for cut in cuts]
        current_cut = self.cut_combo.currentData()
        current_index = 0
        if isinstance(current_cut, SavedCut):
            for index, cut in enumerate(cuts):
                if _same_cut(cut, current_cut):
                    current_index = index
                    break
        selected, accepted = QInputDialog.getItem(
            self,
            "Load Cut",
            "Cut",
            labels,
            current_index,
            False,
        )
        if not accepted:
            return None
        try:
            return cuts[labels.index(selected)]
        except ValueError:
            return None

    def load_selected_result(self) -> None:
        result = self.result_combo.currentData()
        if not isinstance(result, PreviewResult):
            self.preview_status.setText("No saved result selected")
            return
        if not result.output_path.exists():
            self.preview_status.setText(f"Saved result is missing: {result.output_path.name}")
            return
        self._apply_preview_result(result)

    def open_large_view(self) -> None:
        if not self._large_view_available():
            self._update_large_view_state()
            return
        index = self.tabs.currentIndex()
        if index == 0:
            self._toggle_video_fullscreen(self.video_widget)
        elif index == 1:
            if self.processed_output_path is None:
                return
            self._toggle_video_fullscreen(self.processed_video_widget)
            self._seek_processed_from_source_time(self.timeline_playhead_seconds())
        elif index == 2:
            self._open_large_split_view()
        else:
            tile = self._selected_variant_tile()
            if tile is not None:
                self.open_benchmark_variant(tile.index)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        fullscreen_widgets = tuple(
            widget
            for widget in (getattr(self, "video_widget", None), getattr(self, "processed_video_widget", None))
            if widget is not None
        )
        if watched in fullscreen_widgets and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Space and watched.isFullScreen():
                self.toggle_playback()
                return True
            if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_F11):
                if watched.isFullScreen():
                    watched.setFullScreen(False)
                    self._refresh_video_outputs()
                    self._update_large_view_state()
                    return True
        return super().eventFilter(watched, event)

    def run_preview(self) -> None:
        self.plan_preview()
        if self.current_job is None:
            return
        if self.preview_thread is not None:
            return
        if self.benchmark_thread is not None:
            self.preview_status.setText("Variant benchmark is running")
            return

        job = self.current_job
        segment = self.current_plan_segment or self._current_segment()
        self.running_preview_job = job
        self.running_preview_segment = segment

        job.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.preview_thread = QThread(self)
        self.preview_worker = PreviewWorker(job)
        self.preview_worker.moveToThread(self.preview_thread)
        self.preview_thread.started.connect(self.preview_worker.run)
        self.preview_worker.stageStarted.connect(self._on_preview_stage_started)
        self.preview_worker.outputReceived.connect(self._on_preview_output)
        self.preview_worker.progressChanged.connect(self._on_preview_progress)
        self.preview_worker.finished.connect(self._on_preview_finished)
        self.preview_worker.failed.connect(self._on_preview_failed)
        self.preview_worker.finished.connect(self.preview_thread.quit)
        self.preview_worker.failed.connect(self.preview_thread.quit)
        self.preview_worker.finished.connect(self.preview_worker.deleteLater)
        self.preview_worker.failed.connect(self.preview_worker.deleteLater)
        self.preview_thread.finished.connect(self._cleanup_preview_thread)
        self._set_preview_running(True)
        self.preview_status.setText("Preview running")
        self.preview_progress.setValue(0)
        self.command_text.appendPlainText("\nRun log:")
        self.preview_thread.start()

    def cancel_preview(self) -> None:
        if self.preview_worker is not None:
            self.preview_status.setText("Cancelling preview")
            self.preview_worker.cancel()

    def toggle_benchmark(self) -> None:
        if self.benchmark_thread is None:
            self.run_benchmark()
        else:
            self.cancel_benchmark()

    def run_benchmark(self) -> None:
        self._run_benchmark_indices(None)

    def rerun_benchmark_variant(self, index: int) -> None:
        self._run_benchmark_indices((index,))

    def _run_benchmark_indices(self, indices: tuple[int, ...] | None) -> None:
        if self.source_path is None or self.media is None or self.environment is None:
            self.variant_status_label.setText("Open a source video first")
            return
        if self.benchmark_thread is not None:
            return
        if self.preview_thread is not None:
            self.variant_status_label.setText("Preview is running")
            return
        try:
            if self.benchmark_plan is None or indices is None:
                self.benchmark_plan = self.service.plan_video2x_benchmark_with_context(
                    source_path=self.source_path,
                    work_dir=self._preview_work_dir(),
                    segment=self._current_segment(),
                    media=self.media,
                    environment=self.environment,
                    device_index=self._selected_device_index(),
                    output_preset=self._selected_output_preset(),
                )
                self._build_variant_tiles()
                self._write_benchmark_plan_log()
            elif not self.variant_tiles:
                self._build_variant_tiles()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Variant benchmark planning failed", str(exc))
            return

        self.benchmark_thread = QThread(self)
        self.benchmark_worker = BenchmarkWorker(
            self.benchmark_plan,
            indices,
            max_parallel_jobs=self.variant_parallel_spin.value(),
        )
        self.benchmark_worker.moveToThread(self.benchmark_thread)
        self.benchmark_thread.started.connect(self.benchmark_worker.run)
        self.benchmark_worker.variantStarted.connect(self._on_benchmark_variant_started)
        self.benchmark_worker.stageStarted.connect(self._on_benchmark_stage_started)
        self.benchmark_worker.outputReceived.connect(self._on_benchmark_output)
        self.benchmark_worker.progressChanged.connect(self._on_benchmark_progress)
        self.benchmark_worker.variantFinished.connect(self._on_benchmark_variant_finished)
        self.benchmark_worker.finished.connect(self._on_benchmark_finished)
        self.benchmark_worker.failed.connect(self._on_benchmark_failed)
        self.benchmark_worker.finished.connect(self.benchmark_thread.quit)
        self.benchmark_worker.failed.connect(self.benchmark_thread.quit)
        self.benchmark_worker.finished.connect(self.benchmark_worker.deleteLater)
        self.benchmark_worker.failed.connect(self.benchmark_worker.deleteLater)
        self.benchmark_thread.finished.connect(self._cleanup_benchmark_thread)
        self._mark_benchmark_queue(indices)
        self._set_benchmark_running(True)
        self.variant_status_label.setText("Variant benchmark running")
        self.tabs.setCurrentWidget(self.variants_tab)
        self.benchmark_thread.start()

    def cancel_benchmark(self) -> None:
        if self.benchmark_worker is not None:
            self.variant_status_label.setText("Cancelling variant benchmark")
            self.benchmark_worker.cancel()

    def apply_selected_variant(self) -> None:
        tile = self._selected_variant_tile()
        if tile is None or self.benchmark_plan is None:
            self.variant_status_label.setText("No variant selected")
            return
        variant = self.benchmark_plan.variants[tile.index].variant
        if self.settings.active_backend_slug != VIDEO2X_BACKEND_SLUG:
            self.settings = replace(self.settings, active_backend_slug=VIDEO2X_BACKEND_SLUG)
            if hasattr(self.service, "save_settings"):
                self.service.save_settings(self.settings)
        self._ensure_profile_available(variant.profile)
        self._select_profile_slug(variant.profile.slug)
        self.variant_status_label.setText(f"Applied: {variant.label}")
        self._update_profile_summary()

    def _on_benchmark_variant_started(self, index: int, label: str) -> None:
        self._variant_tile(index).set_running(label)
        self.variant_status_label.setText(f"Running: {label}")

    def _on_benchmark_stage_started(self, index: int, label: str, command: str) -> None:
        if index < 0:
            self.variant_status_label.setText(label)
            self.command_text.appendPlainText(f"\n[Benchmark queue] Running: {label}\n{command}")
            self._refresh_properties_dialog()
            return
        tile = self._variant_tile(index)
        tile.set_stage(label)
        self.command_text.appendPlainText(f"\n[{tile.title_text}] Running: {label}\n{command}")
        self._refresh_properties_dialog()

    def _on_benchmark_output(self, index: int, line: str) -> None:
        if index < 0:
            self.command_text.appendPlainText(f"[Benchmark queue] {line}")
            self._refresh_properties_dialog()
            return
        tile = self._variant_tile(index)
        self.command_text.appendPlainText(f"[{tile.title_text}] {line}")
        self._refresh_properties_dialog()

    def _on_benchmark_progress(self, index: int, progress) -> None:
        if index < 0:
            if progress.percent is not None:
                self.variant_status_label.setText(f"Preparing benchmark source: {progress.percent:.1f}%")
            return
        self._variant_tile(index).set_progress(progress)

    def _on_benchmark_variant_finished(self, run: BenchmarkVariantRun) -> None:
        tile = self._variant_tile(run.index)
        elapsed = sum(stage.duration_seconds for stage in run.result.stages)
        progress_events = [progress for stage in run.result.stages for progress in stage.progress]
        fps = next((progress.fps for progress in reversed(progress_events) if progress.fps is not None), None)
        if run.output_path is not None:
            self.benchmark_outputs[run.index] = run.output_path
            tile.set_completed(run.output_path, elapsed, fps)
        elif run.result.cancelled:
            tile.set_failed("cancelled", elapsed, fps)
        else:
            tile.set_failed(run.error or "failed", elapsed, fps)

    def _on_benchmark_finished(self) -> None:
        completed = sum(1 for tile in self.variant_tiles if tile.output_path is not None)
        self.variant_status_label.setText(f"Variant benchmark finished: {completed}/{len(self.variant_tiles)} ready")
        self._set_benchmark_running(False)

    def _on_benchmark_failed(self, message: str) -> None:
        self.variant_status_label.setText("Variant benchmark failed")
        self._set_benchmark_running(False)
        QMessageBox.critical(self, "Variant benchmark failed", message)

    def _cleanup_benchmark_thread(self) -> None:
        if self.benchmark_thread is not None:
            self.benchmark_thread.deleteLater()
        self.benchmark_worker = None
        self.benchmark_thread = None

    def _set_benchmark_running(self, running: bool) -> None:
        self.run_variants_button.setText("Cancel Variants" if running else "Run Variants")
        self.apply_variant_button.setEnabled(not running)
        self.variant_parallel_spin.setEnabled(not running)
        for tile in self.variant_tiles:
            tile.set_actions_enabled(not running)

    def _mark_benchmark_queue(self, indices: tuple[int, ...] | None) -> None:
        selected_indices = indices or tuple(range(len(self.variant_tiles)))
        for position, index in enumerate(selected_indices, start=1):
            self._variant_tile(index).set_queued(position)

    def _build_variant_tiles(self) -> None:
        if self.benchmark_plan is None:
            return
        self._clear_variant_tiles()
        for index, planned_variant in enumerate(self.benchmark_plan.variants):
            tile = VariantTile(index, planned_variant.variant.label, planned_variant.variant.parameters)
            tile.openRequested.connect(self.open_benchmark_variant)
            tile.applyRequested.connect(self.apply_benchmark_variant)
            tile.rerunRequested.connect(self.rerun_benchmark_variant)
            tile.selected.connect(self._select_variant_tile)
            self.variant_tiles.append(tile)
        self._layout_variant_tiles()
        if self.variant_tiles:
            self._select_variant_tile(0)
        self.variant_status_label.setText(f"{len(self.variant_tiles)} variants planned")

    def _clear_variant_tiles(self) -> None:
        for tile in self.variant_tiles:
            tile.setParent(None)
            tile.deleteLater()
        self.variant_tiles = []
        while self.variant_grid.count():
            item = self.variant_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

    def _layout_variant_tiles(self) -> None:
        if not hasattr(self, "variant_grid"):
            return
        while self.variant_grid.count():
            self.variant_grid.takeAt(0)
        viewport_width = max(240, self.variant_scroll.viewport().width() - 18)
        columns = max(1, min(3, viewport_width // 280))
        for index, tile in enumerate(self.variant_tiles):
            self.variant_grid.addWidget(tile, index // columns, index % columns)
        for column in range(columns):
            self.variant_grid.setColumnStretch(column, 1)

    def _write_benchmark_plan_log(self) -> None:
        if self.benchmark_plan is None:
            return
        lines = [
            "Video2X variant benchmark:",
            f"Segment: {self.benchmark_plan.segment.label} {self.benchmark_plan.segment.start_seconds:.3f}-{self.benchmark_plan.segment.end_seconds:.3f}s",
            f"Output preset: {self.benchmark_plan.output_preset.name} ({self.benchmark_plan.output_preset.slug})",
        ]
        for index, planned_variant in enumerate(self.benchmark_plan.variants, start=1):
            lines.extend(["", f"Variant {index}: {planned_variant.variant.label}", planned_variant.variant.parameters])
            for stage_index, stage in enumerate(planned_variant.preview.job.stages, start=1):
                lines.extend([f"  Stage {stage_index}: {stage.label}", f"  {stage.command.display()}"])
        self.command_text.setPlainText("\n".join(lines))
        self._refresh_properties_dialog()

    def _variant_tile(self, index: int) -> "VariantTile":
        return self.variant_tiles[index]

    def _selected_variant_tile(self) -> "VariantTile | None":
        for tile in self.variant_tiles:
            if tile.is_selected:
                return tile
        return self.variant_tiles[0] if self.variant_tiles else None

    def _select_variant_tile(self, index: int) -> None:
        for tile in self.variant_tiles:
            tile.set_selected(tile.index == index)
        self._update_large_view_state()

    def open_benchmark_variant(self, index: int) -> None:
        tile = self._variant_tile(index)
        if tile.output_path is None or self.benchmark_plan is None or self.source_path is None:
            return
        self.processed_output_path = tile.output_path
        self.processed_segment = self.benchmark_plan.segment
        self.processed_player.setSource(QUrl.fromLocalFile(str(tile.output_path.resolve())))
        self.split_processed_player.setSource(QUrl.fromLocalFile(str(tile.output_path.resolve())))
        self._set_timeline_playhead(self.benchmark_plan.segment.start_seconds)
        self.tabs.setCurrentIndex(1)
        self._update_timeline_view()
        self._update_large_view_state()
        self.open_large_view()

    def apply_benchmark_variant(self, index: int) -> None:
        self._select_variant_tile(index)
        self.apply_selected_variant()

    def _ensure_profile_available(self, profile: ProcessingProfile) -> None:
        if any(candidate.slug == profile.slug for candidate in self.profiles):
            return
        self.profiles = (*self.profiles, profile)
        self.profile_combo.addItem(profile.name, profile.slug)

    def _on_preview_stage_started(self, label: str, command: str) -> None:
        self.preview_status.setText(label)
        self.command_text.appendPlainText(f"\nRunning: {label}\n{command}")
        self._refresh_properties_dialog()

    def _on_preview_output(self, line: str) -> None:
        self.command_text.appendPlainText(line)
        self._refresh_properties_dialog()

    def _on_preview_progress(self, progress) -> None:
        if progress.percent is not None:
            self.preview_progress.setValue(round(progress.percent * 10))
        details = []
        if progress.current_frame is not None and progress.total_frames is not None:
            details.append(f"{progress.current_frame}/{progress.total_frames}")
        if progress.fps is not None:
            details.append(f"{progress.fps:.2f} fps")
        if progress.remaining:
            details.append(f"{progress.remaining} remaining")
        self.preview_status.setText(" | ".join(details) if details else "Preview running")

    def _on_preview_finished(self, result) -> None:
        finished_job = self.running_preview_job or self.current_job
        output_path = successful_output_path(result, finished_job.output_path) if finished_job is not None else None
        self._set_preview_running(False)
        if output_path is not None:
            segment = self.running_preview_segment or self.current_plan_segment or self._current_segment()
            self.processed_output_path = output_path
            self.processed_segment = segment
            self.preview_progress.setValue(1000)
            self.preview_status.setText(f"Preview ready: {output_path.name}")
            self._record_preview_result(output_path, segment)
            self.processed_player.setSource(QUrl.fromLocalFile(str(output_path.resolve())))
            self.split_processed_player.setSource(QUrl.fromLocalFile(str(output_path.resolve())))
            self.timeline.set_playhead(segment.start_seconds, emit=False)
            self.tabs.setCurrentIndex(1)
            self._update_timeline_view()
            self._update_large_view_state()
            self.processed_player.setPosition(0)
            self.processed_player.play()
            self._update_playback_button()
        elif result.cancelled:
            self.preview_status.setText("Preview cancelled")
        else:
            failed = result.stages[-1] if result.stages else None
            exit_code = failed.exit_code if failed else "unknown"
            self.preview_status.setText(f"Preview failed: exit {exit_code}")

    def _on_preview_failed(self, message: str) -> None:
        self._set_preview_running(False)
        self.preview_status.setText("Preview failed")
        QMessageBox.critical(self, "Preview execution failed", message)

    def _cleanup_preview_thread(self) -> None:
        if self.preview_thread is not None:
            self.preview_thread.deleteLater()
        self.preview_worker = None
        self.preview_thread = None
        self.running_preview_job = None
        self.running_preview_segment = None

    def _set_preview_running(self, running: bool) -> None:
        self.run_action.setText("Cancel Preview" if running else "Run Preview")
        self.run_action.setIcon(
            self.style().standardIcon(
                QStyle.StandardPixmap.SP_MediaStop if running else QStyle.StandardPixmap.SP_MediaPlay
            )
        )
        self.run_preview_button.setText("Cancel Preview" if running else "Run Preview")

    def _load_environment(self) -> None:
        self.environment = self.service.discover_environment()

        self.gpu_combo.clear()
        if self.environment.video2x_capabilities is not None:
            preferred_index = self.environment.preferred_gpu.index if self.environment.preferred_gpu else None
            for row, device in enumerate(self.environment.video2x_capabilities.devices):
                self.gpu_combo.addItem(f"{device.index}. {device.name}", device.index)
                if device.index == preferred_index:
                    self.gpu_combo.setCurrentIndex(row)
        self._refresh_properties_dialog()
        self.plan_preview()

    def _update_source_info(self) -> None:
        self._refresh_properties_dialog()

    def _update_profile_summary(self) -> None:
        profile = self._selected_profile()
        output_preset = self._selected_output_preset()
        flags = []
        if profile.experimental:
            flags.append("Experimental")
        if profile.noise_level is not None:
            flags.append(f"Noise {profile.noise_level}")
        else:
            flags.append("Noise unchanged")
        self.profile_summary_text = (
            f"{profile.summary}\n"
            f"Processor: {profile.processor} / {profile.model}\n"
            f"Scale: {profile.scale or 'target'}x | {', '.join(flags)}\n"
            f"Output: {output_preset.name} | {output_preset.codec} CRF {output_preset.crf} | {output_preset.encoder_preset}"
        )
        self._refresh_properties_dialog()
        if not self._suppress_planning:
            self.plan_preview()

    def _selected_profile(self) -> ProcessingProfile:
        slug = self.profile_combo.currentData()
        for profile in self.profiles:
            if profile.slug == slug:
                return profile
        return self.profiles[0]

    def _selected_output_preset(self) -> OutputPreset:
        slug = self.output_combo.currentData()
        for output_preset in self.output_presets:
            if output_preset.slug == slug:
                return output_preset
        return self.output_presets[0]

    def _selected_device_index(self) -> int | None:
        value = self.gpu_combo.currentData()
        return int(value) if value is not None else None

    def _preview_work_dir(self) -> Path:
        return Path(self.settings.cache_directory).expanduser() / "previews"

    def _current_segment(self) -> TestSegment:
        label = self.segment_label.currentText().strip() or "Preview"
        return TestSegment(
            label=label,
            kind=TestSegmentKind(self.segment_kind.currentData() or TestSegmentKind.CUSTOM.value),
            start_seconds=self.in_spin.value(),
            end_seconds=max(self.out_spin.value(), self.in_spin.value() + 0.1),
        )

    def _set_segment(self, segment: TestSegment) -> None:
        self._syncing_segment_controls = True
        self.segment_label.setCurrentText(segment.label)
        self.segment_kind.setCurrentIndex(max(0, self.segment_kind.findData(segment.kind.value)))
        self.in_spin.setValue(segment.start_seconds)
        self.out_spin.setValue(segment.end_seconds)
        self.duration_spin.setValue(segment.duration_seconds)
        self.timeline.set_segment(segment)
        self._update_timeline_view()
        self._syncing_segment_controls = False

    def _on_timeline_segment(self, segment: TestSegment) -> None:
        self._set_segment(segment)
        self.plan_preview()

    def _on_timeline_playhead(self, seconds: float) -> None:
        if self._syncing_playhead:
            return
        if self.tabs.currentIndex() == 0:
            self.player.setPosition(round(seconds * 1000))
        elif self.tabs.currentIndex() == 1:
            self._seek_processed_from_source_time(seconds)
        elif self.tabs.currentIndex() == 2:
            self._seek_split_from_source_time(seconds)

    def _on_player_position(self, milliseconds: int) -> None:
        if self.tabs.currentIndex() == 0:
            self._set_timeline_playhead(milliseconds / 1000)

    def _on_processed_position(self, milliseconds: int) -> None:
        if self.tabs.currentIndex() != 1 or self.processed_segment is None:
            return
        self._set_timeline_playhead(self._source_seconds_for_processed_milliseconds(milliseconds))

    def _on_split_original_position(self, milliseconds: int) -> None:
        if self.tabs.currentIndex() != 2:
            return
        source_time = milliseconds / 1000
        if self.processed_segment is not None and source_time >= self.processed_segment.end_seconds:
            if self._active_player_is_playing() and not self._restarting_playback:
                self._restart_active_playback_from_start()
                return
            source_time = self.processed_segment.start_seconds
        self._set_timeline_playhead(source_time)
        if self.processed_segment is not None:
            expected = self._processed_milliseconds_for_source_time(source_time)
            playback_position = self._playback_milliseconds_for_processed_milliseconds(expected)
            if abs(self.split_processed_player.position() - playback_position) > 350:
                self.split_processed_player.setPosition(playback_position)

    def _on_segment_controls_changed(self) -> None:
        if self._syncing_segment_controls:
            return
        self._set_segment(self._current_segment())
        self.plan_preview()

    def _on_duration_changed(self) -> None:
        if self._syncing_segment_controls:
            return
        start = self.in_spin.value()
        end = start + self.duration_spin.value()
        if self.media and self.media.duration_seconds:
            end = min(end, self.media.duration_seconds)
        self.out_spin.setValue(end)
        self._on_segment_controls_changed()

    def _set_in_from_playhead(self) -> None:
        self.in_spin.setValue(self.timeline_playhead_seconds())

    def _set_out_from_playhead(self) -> None:
        self.out_spin.setValue(max(self.timeline_playhead_seconds(), self.in_spin.value() + 0.1))

    def _on_active_tab_changed(self, index: int) -> None:
        self.pause_active()
        self._refresh_video_outputs()
        self._update_timeline_view()
        source_time = self.timeline_playhead_seconds()
        if index == 0:
            self.player.setPosition(round(source_time * 1000))
        elif index == 1:
            self._seek_processed_from_source_time(source_time)
        elif index == 2:
            self._seek_split_from_source_time(source_time)
        self._update_large_view_state()
        self._update_playback_button()

    def _on_playback_state_changed(self, state=None) -> None:
        del state
        self._update_playback_button()

    def _on_media_status_changed(self, player: QMediaPlayer, status) -> None:
        if self._restarting_playback:
            return
        if status == QMediaPlayer.MediaStatus.EndOfMedia and self._player_matches_active_view(player):
            self._restart_active_playback_from_start()

    def _active_player_is_playing(self) -> bool:
        playing = QMediaPlayer.PlaybackState.PlayingState
        if self.tabs.currentIndex() == 0:
            return self.player.playbackState() == playing
        if self.tabs.currentIndex() == 1:
            return self.processed_player.playbackState() == playing
        if self.tabs.currentIndex() == 2:
            return self.split_original_player.playbackState() == playing or self.split_processed_player.playbackState() == playing
        return False

    def _player_matches_active_view(self, player: QMediaPlayer) -> bool:
        if self.tabs.currentIndex() == 0:
            return player is self.player
        if self.tabs.currentIndex() == 1:
            return player is self.processed_player
        if self.tabs.currentIndex() == 2:
            return player in (self.split_original_player, self.split_processed_player)
        return False

    def _update_playback_button(self) -> None:
        if not hasattr(self, "play_button"):
            return
        self.play_button.setText("Stop" if self._active_player_is_playing() else "Play")

    def timeline_playhead_seconds(self) -> float:
        return self.timeline.playhead_seconds()

    def _set_timeline_playhead(self, seconds: float) -> None:
        self._syncing_playhead = True
        try:
            self.timeline.set_playhead(seconds, emit=False)
        finally:
            self._syncing_playhead = False

    def _restart_active_playback_from_start(self) -> None:
        self._restarting_playback = True
        try:
            if self.tabs.currentIndex() == 0:
                self.player.setPosition(0)
                self._set_timeline_playhead(0)
                self.player.play()
            elif self.tabs.currentIndex() == 1:
                if self.processed_segment is None or self.processed_output_path is None:
                    self._update_playback_button()
                    return
                self._seek_processed_from_source_time(self.processed_segment.start_seconds)
                self.processed_player.play()
            elif self.tabs.currentIndex() == 2:
                if self.processed_segment is None or self.processed_output_path is None:
                    self._update_playback_button()
                    return
                self._seek_split_from_source_time(self.processed_segment.start_seconds)
                self.split_processed_player.play()
                self.split_original_player.play()
        finally:
            self._restarting_playback = False
        self._update_playback_button()

    def _seek_processed_from_source_time(self, source_time: float) -> None:
        if self.processed_segment is None:
            return
        local_ms = self._processed_milliseconds_for_source_time(source_time)
        self.processed_player.setPosition(self._playback_milliseconds_for_processed_milliseconds(local_ms))
        self._set_timeline_playhead(self.processed_segment.start_seconds + local_ms / 1000)

    def _seek_split_from_source_time(self, source_time: float) -> None:
        if self.processed_segment is None:
            self.split_original_player.setPosition(round(source_time * 1000))
            return
        local_ms = self._processed_milliseconds_for_source_time(source_time)
        mapped_source_time = self.processed_segment.start_seconds + local_ms / 1000
        self.split_original_player.setPosition(round(mapped_source_time * 1000))
        self.split_processed_player.setPosition(self._playback_milliseconds_for_processed_milliseconds(local_ms))
        self._set_timeline_playhead(mapped_source_time)

    def _processed_milliseconds_for_source_time(self, source_time: float) -> int:
        if self.processed_segment is None:
            return 0
        local_seconds = source_time - self.processed_segment.start_seconds
        local_seconds = min(max(0.0, local_seconds), self.processed_segment.duration_seconds)
        return round(local_seconds * 1000)

    def _source_seconds_for_processed_milliseconds(self, milliseconds: int) -> float:
        if self.processed_segment is None:
            return max(0.0, milliseconds / 1000)
        local_seconds = milliseconds / 1000
        local_seconds = min(max(0.0, local_seconds), self.processed_segment.duration_seconds)
        return self.processed_segment.start_seconds + local_seconds

    def _playback_milliseconds_for_processed_milliseconds(self, milliseconds: int) -> int:
        if self.processed_segment is None:
            return max(0, milliseconds)
        duration_ms = round(self.processed_segment.duration_seconds * 1000)
        if duration_ms <= 40:
            return max(0, min(milliseconds, duration_ms))
        return min(max(0, milliseconds), duration_ms - 40)

    def _update_timeline_view(self) -> None:
        if not hasattr(self, "timeline"):
            return
        if self.tabs.currentIndex() in (1, 2) and self.processed_segment is not None:
            self.timeline.set_display_window(
                self.processed_segment.start_seconds,
                self.processed_segment.end_seconds,
                show_segment_handles=False,
            )
        else:
            self.timeline.clear_display_window()

    def _refresh_video_outputs(self) -> None:
        self.player.setVideoOutput(self.video_widget)
        self.processed_player.setVideoOutput(self.processed_video_widget)
        self.split_original_player.setVideoOutput(self.split_original_widget)
        self.split_processed_player.setVideoOutput(self.split_processed_widget)
        if self.processed_output_path is not None:
            source_url = QUrl.fromLocalFile(str(self.processed_output_path.resolve()))
            if self.processed_player.source() != source_url:
                self.processed_player.setSource(source_url)
            if self.split_processed_player.source() != source_url:
                self.split_processed_player.setSource(source_url)

    def _record_preview_result(self, output_path: Path, segment: TestSegment) -> None:
        if self.source_path is None:
            return
        try:
            self.service.record_preview_result(
                self.source_path,
                output_path,
                self._selected_profile(),
                segment,
                self._selected_output_preset(),
            )
        except Exception as exc:  # noqa: BLE001
            self.command_text.appendPlainText(f"\nHistory save failed: {exc}")
            return
        self._refresh_saved_results()

    def _load_latest_saved_cut(self, source_path: Path) -> SavedCut | None:
        try:
            if hasattr(self.service, "load_source_cut"):
                return self.service.load_source_cut(source_path)
            saved_segment = self.service.load_source_segment(source_path)
            if saved_segment is not None:
                return SavedCut(segment=saved_segment, profile_slug=None, updated_at="")
            return None
        except Exception as exc:  # noqa: BLE001
            self.command_text.appendPlainText(f"\nHistory load failed: {exc}")
            return None

    def _refresh_saved_cuts(self) -> None:
        self.cut_combo.clear()
        if self.source_path is None:
            self.saved_cuts = ()
            self.cut_combo.addItem("No source loaded", None)
            return
        try:
            if hasattr(self.service, "saved_cuts_for_source"):
                self.saved_cuts = self.service.saved_cuts_for_source(self.source_path)
            else:
                latest = self._load_latest_saved_cut(self.source_path)
                self.saved_cuts = (latest,) if latest is not None else ()
        except Exception as exc:  # noqa: BLE001
            self.saved_cuts = ()
            self.cut_combo.addItem(f"Cuts unavailable: {exc}", None)
            return
        if not self.saved_cuts:
            self.cut_combo.addItem("No saved cuts for this source", None)
            return
        for cut in self.saved_cuts:
            self.cut_combo.addItem(_cut_text(cut), cut)

    def _refresh_saved_results(self) -> None:
        self.result_combo.clear()
        if self.source_path is None:
            self.saved_results = ()
            self.result_combo.addItem("No source loaded", None)
            return
        try:
            self.saved_results = self.service.preview_results_for_source(self.source_path)
        except Exception as exc:  # noqa: BLE001
            self.saved_results = ()
            self.result_combo.addItem(f"History unavailable: {exc}", None)
            return
        if not self.saved_results:
            self.result_combo.addItem("No saved results for this source", None)
            return
        for result in self.saved_results:
            missing = "" if result.output_exists else " [missing]"
            self.result_combo.addItem(_result_text(result) + missing, result)

    def _apply_preview_result(self, result: PreviewResult) -> None:
        segment = result.segment()
        self._select_profile_slug(result.profile_slug)
        self._set_segment(segment)
        self.processed_output_path = result.output_path
        self.processed_segment = segment
        self.processed_player.setSource(QUrl.fromLocalFile(str(result.output_path.resolve())))
        self.split_processed_player.setSource(QUrl.fromLocalFile(str(result.output_path.resolve())))
        self._set_timeline_playhead(segment.start_seconds)
        self.tabs.setCurrentIndex(1)
        self._update_timeline_view()
        self._update_large_view_state()
        self._seek_processed_from_source_time(segment.start_seconds)
        self.preview_status.setText(f"Loaded saved result: {result.output_path.name}")

    def _apply_saved_cut(self, cut: SavedCut) -> None:
        if cut.profile_slug:
            self._select_profile_slug(cut.profile_slug)
        if cut.output_preset_slug:
            self._select_output_preset_slug(cut.output_preset_slug)
        self._set_segment(cut.segment)
        self._select_saved_cut(cut)

    def _select_saved_cut(self, cut: SavedCut) -> None:
        for index in range(self.cut_combo.count()):
            current = self.cut_combo.itemData(index)
            if isinstance(current, SavedCut) and _same_cut(current, cut):
                self.cut_combo.setCurrentIndex(index)
                return

    def _select_profile_slug(self, profile_slug: str) -> None:
        index = self.profile_combo.findData(profile_slug)
        if index >= 0:
            self.profile_combo.setCurrentIndex(index)

    def _select_output_preset_slug(self, output_preset_slug: str) -> None:
        index = self.output_combo.findData(output_preset_slug)
        if index >= 0:
            self.output_combo.setCurrentIndex(index)

    def _apply_settings_defaults_to_controls(self) -> None:
        self._select_profile_slug(self.settings.default_profile_slug)
        self._select_output_preset_slug(self.settings.default_output_preset_slug)
        self._select_first_compatible_profile()

    def _select_first_compatible_profile(self) -> None:
        profile = self._selected_profile()
        if profile.supports_backend(self.settings.active_backend_slug):
            return
        for candidate in self.profiles:
            if candidate.supports_backend(self.settings.active_backend_slug):
                self._select_profile_slug(candidate.slug)
                self.preview_status.setText(f"Selected compatible profile: {candidate.name}")
                return
        self.preview_status.setText(f"No profile is compatible with backend: {self.settings.active_backend_slug}")

    def _refresh_properties_dialog(self) -> None:
        if self.properties_dialog is None:
            return
        self.properties_dialog.update_data(
            media=self.media,
            source_path=self.source_path,
            environment=self.environment,
            profile=self._selected_profile(),
            output_preset=self._selected_output_preset(),
            profile_summary=f"Backend: {self.settings.active_backend_slug}\n{self.profile_summary_text}",
            command_log=self.command_text.toPlainText(),
        )

    def _clear_properties_dialog(self) -> None:
        self.properties_dialog = None

    def _open_large_split_view(self) -> None:
        if self.source_path is None or self.processed_output_path is None or self.processed_segment is None:
            self._update_large_view_state()
            return
        if self.large_split_window is not None:
            self.large_split_window.close()
            return
        self.pause_active()
        self.large_split_window = LargeSplitWindow(
            source_path=self.source_path,
            processed_path=self.processed_output_path,
            segment=self.processed_segment,
            source_time=self.timeline_playhead_seconds(),
            on_close=self._restore_split_video_outputs,
        )
        self.large_split_window.show()
        self.large_split_window.play()

    def _restore_split_video_outputs(self) -> None:
        self.pause_active()
        self.large_split_window = None
        self._refresh_video_outputs()
        self._update_large_view_state()

    def _toggle_video_fullscreen(self, widget: QVideoWidget) -> None:
        widget.setFullScreen(not widget.isFullScreen())
        if not widget.isFullScreen():
            self._refresh_video_outputs()
        self._update_large_view_state()

    def _large_view_available(self) -> bool:
        if not hasattr(self, "tabs"):
            return False
        if self.tabs.currentIndex() == 0:
            return self.source_path is not None or self.player.source().isValid()
        if self.tabs.currentIndex() == 1:
            return self.processed_output_path is not None
        if self.tabs.currentIndex() == 2:
            return self.source_path is not None and self.processed_output_path is not None and self.processed_segment is not None
        tile = self._selected_variant_tile()
        return tile is not None and tile.output_path is not None

    def _update_large_view_state(self) -> None:
        if not hasattr(self, "large_view_button"):
            return
        enabled = self._large_view_available()
        self.large_view_button.setEnabled(enabled)
        self.large_view_action.setEnabled(enabled)
        if self.tabs.currentIndex() == 3 and not enabled:
            reason = "Run or select a completed variant first"
        elif self.tabs.currentIndex() == 2 and not enabled:
            reason = "Run or load a processed preview first"
        elif self.tabs.currentIndex() == 1 and self.processed_output_path is None:
            reason = "Run or load a processed preview first"
        elif self.tabs.currentIndex() == 0 and self.source_path is None and not self.player.source().isValid():
            reason = "Open a source video first"
        else:
            reason = "Open Large View"
        self.large_view_button.setToolTip(reason)
        self.large_view_action.setToolTip(reason)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.preview_worker is not None:
            self.preview_worker.cancel()
        if self.benchmark_worker is not None:
            self.benchmark_worker.cancel()
        self.pause_active()
        if self.large_split_window is not None:
            self.large_split_window.close()
        if self.preview_thread is not None:
            self.preview_thread.quit()
            self.preview_thread.wait(2000)
        if self.benchmark_thread is not None:
            self.benchmark_thread.quit()
            self.benchmark_thread.wait(2000)
        super().closeEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._layout_variant_tiles()


class VariantTile(QFrame):
    openRequested = Signal(int)
    applyRequested = Signal(int)
    rerunRequested = Signal(int)
    selected = Signal(int)

    def __init__(self, index: int, title: str, parameters: str) -> None:
        super().__init__()
        self.index = index
        self.title_text = title
        self.output_path: Path | None = None
        self.is_selected = False
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumWidth(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            """
            VariantTile {
                background: #20242c;
                border: 1px solid #343a46;
                border-radius: 6px;
            }
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-weight: 600;")
        self.title_label.setWordWrap(True)
        self.params_label = QLabel(parameters)
        self.params_label.setWordWrap(True)
        self.status_label = QLabel("Ready")
        self.status_label.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.result_label = QLabel("Queued output will open in Large View")
        self.result_label.setWordWrap(True)
        self.result_label.setMinimumHeight(54)
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_label.setStyleSheet("background: #11151d; color: #aeb8c8; border: 1px solid #303846; border-radius: 4px;")
        actions = QHBoxLayout()
        self.open_button = QPushButton("Open")
        self.apply_button = QPushButton("Apply")
        self.rerun_button = QPushButton("Rerun")
        self.open_button.setEnabled(False)
        actions.addWidget(self.open_button)
        actions.addWidget(self.apply_button)
        actions.addWidget(self.rerun_button)
        layout.addWidget(self.title_label)
        layout.addWidget(self.params_label)
        layout.addWidget(self.result_label)
        layout.addWidget(self.progress)
        layout.addWidget(self.status_label)
        layout.addLayout(actions)
        self.open_button.clicked.connect(lambda: self.openRequested.emit(self.index))
        self.apply_button.clicked.connect(lambda: self.applyRequested.emit(self.index))
        self.rerun_button.clicked.connect(lambda: self.rerunRequested.emit(self.index))

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.selected.emit(self.index)
        super().mousePressEvent(event)

    def set_selected(self, selected: bool) -> None:
        self.is_selected = selected
        border = "#7aa2ff" if selected else "#343a46"
        self.setStyleSheet(
            f"""
            VariantTile {{
                background: #20242c;
                border: 1px solid {border};
                border-radius: 6px;
            }}
            """
        )

    def set_running(self, label: str) -> None:
        self.output_path = None
        self.open_button.setEnabled(False)
        self.progress.setValue(0)
        self.status_label.setText(f"Running: {label}")
        self.result_label.setText("Running")

    def set_queued(self, position: int) -> None:
        self.output_path = None
        self.open_button.setEnabled(False)
        self.progress.setValue(0)
        self.status_label.setText(f"Queued #{position}")
        self.result_label.setText("Waiting in queue")

    def set_stage(self, label: str) -> None:
        self.status_label.setText(label)

    def set_progress(self, progress) -> None:
        if progress.percent is not None:
            self.progress.setValue(round(progress.percent * 10))
        details = []
        if progress.current_frame is not None and progress.total_frames is not None:
            details.append(f"{progress.current_frame}/{progress.total_frames}")
        if progress.fps is not None:
            details.append(f"{progress.fps:.2f} fps")
        if progress.remaining:
            details.append(f"{progress.remaining} remaining")
        if details:
            self.status_label.setText(" | ".join(details))

    def set_completed(self, output_path: Path, elapsed_seconds: float, fps: float | None) -> None:
        self.output_path = output_path
        self.open_button.setEnabled(True)
        self.progress.setValue(1000)
        self.result_label.setText(output_path.name)
        timing = f"{elapsed_seconds:.1f}s"
        speed = f" | {fps:.2f} fps" if fps is not None else ""
        self.status_label.setText(f"Ready: {timing}{speed}")

    def set_failed(self, error: str, elapsed_seconds: float, fps: float | None) -> None:
        self.output_path = None
        self.open_button.setEnabled(False)
        speed = f" | {fps:.2f} fps" if fps is not None else ""
        self.status_label.setText(f"Failed: {error} ({elapsed_seconds:.1f}s{speed})")
        self.result_label.setText("No output")

    def set_actions_enabled(self, enabled: bool) -> None:
        self.apply_button.setEnabled(enabled)
        self.rerun_button.setEnabled(enabled)
        self.open_button.setEnabled(enabled and self.output_path is not None)


class LargeSplitWindow(QWidget):
    def __init__(
        self,
        source_path: Path,
        processed_path: Path,
        segment: TestSegment,
        source_time: float,
        on_close,
    ) -> None:
        super().__init__()
        self._on_close = on_close
        self.segment = segment
        self._restarting_playback = False
        self._pending_play = False
        self._pending_play_retries = 0
        self._pending_source_time = source_time
        self._last_source_seek_ms = 0
        self._last_processed_seek_ms = 0
        self.setWindowTitle("VideoFixie - Split Compare")
        self.resize(1600, 720)
        self.setMinimumSize(900, 360)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.original_widget = QVideoWidget()
        self.processed_widget = QVideoWidget()
        layout.addWidget(self.original_widget, 1)
        layout.addWidget(self.processed_widget, 1)
        self.setStyleSheet("QWidget { background: #050609; }")

        self.original_player = QMediaPlayer(self)
        self.original_audio = QAudioOutput(self)
        self.original_audio.setMuted(True)
        self.original_player.setAudioOutput(self.original_audio)
        self.original_player.setVideoOutput(self.original_widget)
        self.original_player.setSource(QUrl.fromLocalFile(str(source_path.resolve())))
        self.original_player.positionChanged.connect(self._on_original_position)
        self.original_player.mediaStatusChanged.connect(self._on_media_status_changed)

        self.processed_player = QMediaPlayer(self)
        self.processed_audio = QAudioOutput(self)
        self.processed_player.setAudioOutput(self.processed_audio)
        self.processed_player.setVideoOutput(self.processed_widget)
        self.processed_player.setSource(QUrl.fromLocalFile(str(processed_path.resolve())))
        self.processed_player.mediaStatusChanged.connect(self._on_media_status_changed)

        self.seek_source_time(source_time)
        QTimer.singleShot(0, self._apply_pending_seek)
        QTimer.singleShot(150, self._apply_pending_seek)

    def play(self) -> None:
        self._pending_play = True
        self._maybe_start_pending_play()

    def pause(self) -> None:
        self.original_player.pause()
        self.processed_player.pause()

    def toggle_playback(self) -> None:
        if self._is_playing():
            self.pause()
        else:
            self.play()

    def seek_source_time(self, source_time: float) -> None:
        self._pending_source_time = source_time
        self._apply_pending_seek()

    def _on_original_position(self, milliseconds: int) -> None:
        source_time = milliseconds / 1000
        if source_time >= self.segment.end_seconds:
            if self._is_playing() and not self._restarting_playback:
                self._restart_from_start()
            return
        expected = self._processed_milliseconds_for_source_time(source_time)
        playback_position = self._playback_milliseconds_for_processed_milliseconds(expected)
        if abs(self.processed_player.position() - playback_position) > 350:
            self.processed_player.setPosition(playback_position)

    def _on_media_status_changed(self, status) -> None:
        if self._restarting_playback:
            return
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._restart_from_start()
        elif status in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
            QMediaPlayer.MediaStatus.BufferingMedia,
        ):
            self._apply_pending_seek()
            self._maybe_start_pending_play()

    def _restart_from_start(self) -> None:
        self._restarting_playback = True
        try:
            self.seek_source_time(self.segment.start_seconds)
            self._start_players()
        finally:
            self._restarting_playback = False

    def _maybe_start_pending_play(self) -> None:
        if not self._pending_play:
            return
        self._apply_pending_seek()
        if self._media_ready_to_play():
            self._pending_play = False
            self._pending_play_retries = 0
            self._start_players()
            return
        if self._pending_play_retries < 20:
            self._pending_play_retries += 1
            QTimer.singleShot(100, self._maybe_start_pending_play)

    def _start_players(self) -> None:
        self._apply_pending_seek()
        self.processed_player.play()
        self.original_player.play()

    def _apply_pending_seek(self) -> None:
        local_ms = self._processed_milliseconds_for_source_time(self._pending_source_time)
        self._last_source_seek_ms = self._source_milliseconds_for_source_time(self._pending_source_time)
        self._last_processed_seek_ms = self._playback_milliseconds_for_processed_milliseconds(local_ms)
        self.original_player.setPosition(self._last_source_seek_ms)
        self.processed_player.setPosition(self._last_processed_seek_ms)

    def _media_ready_to_play(self) -> bool:
        loading = QMediaPlayer.MediaStatus.LoadingMedia
        no_media = QMediaPlayer.MediaStatus.NoMedia
        invalid = QMediaPlayer.MediaStatus.InvalidMedia
        blocked_statuses = {loading, no_media, invalid}
        return (
            self.original_player.mediaStatus() not in blocked_statuses
            and self.processed_player.mediaStatus() not in blocked_statuses
        )

    def _source_milliseconds_for_source_time(self, source_time: float) -> int:
        local_ms = self._processed_milliseconds_for_source_time(source_time)
        return round((self.segment.start_seconds + local_ms / 1000) * 1000)

    def _processed_milliseconds_for_source_time(self, source_time: float) -> int:
        local_seconds = source_time - self.segment.start_seconds
        local_seconds = min(max(0.0, local_seconds), self.segment.duration_seconds)
        return round(local_seconds * 1000)

    def _playback_milliseconds_for_processed_milliseconds(self, milliseconds: int) -> int:
        duration_ms = round(self.segment.duration_seconds * 1000)
        if duration_ms <= 40:
            return max(0, min(milliseconds, duration_ms))
        return min(max(0, milliseconds), duration_ms - 40)

    def _is_playing(self) -> bool:
        playing = QMediaPlayer.PlaybackState.PlayingState
        return self.original_player.playbackState() == playing or self.processed_player.playbackState() == playing

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Space:
            self.toggle_playback()
            return
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_F11):
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._pending_play = False
        self.pause()
        self.original_player.setVideoOutput(None)
        self.processed_player.setVideoOutput(None)
        self.original_player.setSource(QUrl())
        self.processed_player.setSource(QUrl())
        self._on_close()
        super().closeEvent(event)


def _seconds_spin() -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(0, 24 * 60 * 60)
    spin.setDecimals(3)
    spin.setSingleStep(1.0)
    spin.setSuffix(" s")
    return spin


def _result_text(result: PreviewResult) -> str:
    return (
        f"{result.created_at} | {result.profile_name} | {result.output_preset_name} | "
        f"{result.start_seconds:.3f}-{result.end_seconds:.3f}s | {result.output_path.name}"
    )


def _cut_text(cut: SavedCut) -> str:
    profile = cut.profile_slug or "profile"
    output = cut.output_preset_slug or "output"
    backend = f" | {cut.backend_slug}" if cut.backend_slug else ""
    return (
        f"{cut.segment.label} [{cut.segment.kind.value}] "
        f"{cut.segment.start_seconds:.3f}-{cut.segment.end_seconds:.3f}s | {profile} | {output}{backend}"
    )


def _same_cut(left: SavedCut, right: SavedCut) -> bool:
    if left.id is not None and right.id is not None:
        return left.id == right.id
    return (
        left.segment.label == right.segment.label
        and left.source_path == right.source_path
        and left.segment.start_seconds == right.segment.start_seconds
        and left.segment.end_seconds == right.segment.end_seconds
    )
