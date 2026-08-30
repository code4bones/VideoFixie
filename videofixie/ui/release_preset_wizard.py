from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWizard,
    QWizardPage,
    QWidget,
)

from videofixie.domain.media import MediaInfo
from videofixie.domain.release_presets import ReleasePreset
from videofixie.services.release_presets import (
    ReleaseChoice,
    build_release_preset,
    container_choices,
    release_goal_choices,
    resolution_policy_choices,
    stream_policy_choices,
)


class ReleasePresetWizard(QWizard):
    def __init__(self, media: MediaInfo | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.media = media
        self.setWindowTitle("Release Preset Wizard")
        self.resize(760, 560)

        self.goal_page = ChoicePage(
            title="Release Goal",
            subtitle="Choose the final file's primary purpose.",
            field_name="release_goal",
            choices=release_goal_choices(media),
        )
        self.resolution_page = ChoicePage(
            title="Resolution",
            subtitle="Choose how the restored frame size is handled.",
            field_name="resolution_policy",
            choices=resolution_policy_choices(media),
        )
        self.container_page = ChoicePage(
            title="Container",
            subtitle="Choose the release file wrapper.",
            field_name="container",
            choices=container_choices(),
        )
        self.stream_page = StreamsPage()
        self.destination_page = DestinationPage()
        self.summary_page = SummaryPage(self)

        self.addPage(self.goal_page)
        self.addPage(self.resolution_page)
        self.addPage(self.container_page)
        self.addPage(self.stream_page)
        self.addPage(self.destination_page)
        self.addPage(self.summary_page)

        self.setStyleSheet(
            """
            QWizard, QWizardPage, QWidget { background: #17191f; color: #e8edf5; }
            QLabel { color: #e8edf5; }
            QComboBox, QLineEdit, QPlainTextEdit {
                background: #222732; color: #e8edf5; border: 1px solid #3d4554; border-radius: 4px; padding: 4px;
            }
            QPushButton { background: #2d3543; color: #eef3fb; border: 1px solid #495366; border-radius: 4px; padding: 6px 10px; }
            QPushButton:hover { background: #384254; }
            """
        )

    def release_preset(self) -> ReleasePreset:
        return build_release_preset(
            goal_slug=self.goal_page.current_slug(),
            resolution_policy=self.resolution_page.current_slug(),
            container=self.container_page.current_slug(),
            audio_policy=self.stream_page.audio_policy(),
            subtitle_policy=self.stream_page.subtitle_policy(),
            metadata_policy=self.stream_page.metadata_policy(),
            destination_directory=str(self.field("destination_directory")),
            naming_template=str(self.field("naming_template")),
        )


class ChoicePage(QWizardPage):
    def __init__(self, title: str, subtitle: str, field_name: str, choices: tuple[ReleaseChoice, ...]) -> None:
        super().__init__()
        self.choices = choices
        self.setTitle(title)
        self.setSubTitle(subtitle)
        layout = QVBoxLayout(self)
        self.combo = QComboBox()
        for choice in choices:
            self.combo.addItem(choice.display_label, choice.slug)
        recommended_index = next((index for index, choice in enumerate(choices) if choice.recommended), 0)
        self.combo.setCurrentIndex(recommended_index)
        self.explanation = QLabel()
        self.explanation.setWordWrap(True)
        layout.addWidget(self.combo)
        layout.addWidget(self.explanation)
        layout.addStretch(1)
        del field_name
        self.combo.currentIndexChanged.connect(self._update_explanation)
        self._update_explanation()

    def current_slug(self) -> str:
        return str(self.combo.currentData())

    def _update_explanation(self, *_args: object) -> None:
        choice = self.choices[max(0, self.combo.currentIndex())]
        recommendation = "Recommended for the current context.\n\n" if choice.recommended else ""
        self.explanation.setText(f"{recommendation}{choice.explanation}")


class StreamsPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Streams")
        self.setSubTitle("Choose how audio, subtitles and metadata are preserved.")
        layout = QFormLayout(self)

        self.audio_combo = _choice_combo(stream_policy_choices("audio"))
        self.subtitle_combo = _choice_combo(stream_policy_choices("subtitles"))
        self.metadata_combo = _choice_combo(stream_policy_choices("metadata"))
        self.details = QLabel()
        self.details.setWordWrap(True)

        layout.addRow("Audio", self.audio_combo)
        layout.addRow("Subtitles", self.subtitle_combo)
        layout.addRow("Metadata", self.metadata_combo)
        layout.addRow("", self.details)

        for combo in (self.audio_combo, self.subtitle_combo, self.metadata_combo):
            combo.currentIndexChanged.connect(self._update_details)
        self._update_details()

    def audio_policy(self) -> str:
        return str(self.audio_combo.currentData())

    def subtitle_policy(self) -> str:
        return str(self.subtitle_combo.currentData())

    def metadata_policy(self) -> str:
        return str(self.metadata_combo.currentData())

    def _update_details(self) -> None:
        self.details.setText(
            "Recommended defaults preserve source streams where practical. Re-encoding or dropping streams improves compatibility but changes or removes source data."
        )


class DestinationPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Destination")
        self.setSubTitle("Choose where releases are written and how files are named.")
        layout = QFormLayout(self)
        self.destination_edit = QLineEdit("outputs")
        self.naming_edit = QLineEdit("{source_stem}.{profile}.{release_goal}.{container}")
        layout.addRow("Directory", self._directory_row())
        layout.addRow("Naming template", self.naming_edit)
        self.registerField("destination_directory*", self.destination_edit)
        self.registerField("naming_template*", self.naming_edit)

    def _directory_row(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.destination_edit, 1)
        button = QPushButton("Browse")
        button.clicked.connect(self._browse)
        layout.addWidget(button)
        return row

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select release directory", self.destination_edit.text() or str(Path.cwd()))
        if path:
            self.destination_edit.setText(path)


class SummaryPage(QWizardPage):
    def __init__(self, wizard: ReleasePresetWizard) -> None:
        super().__init__()
        self.release_wizard = wizard
        self.setTitle("Summary")
        self.setSubTitle("Review the human-facing choices and exact technical settings before saving.")
        layout = QVBoxLayout(self)
        self.summary_text = QPlainTextEdit()
        self.summary_text.setReadOnly(True)
        layout.addWidget(self.summary_text)

    def initializePage(self) -> None:  # noqa: N802
        preset = self.release_wizard.release_preset()
        lines = [
            "Human summary:",
            *preset.human_summary_lines(),
            "",
            "Technical settings:",
            *preset.technical_summary_lines(),
        ]
        self.summary_text.setPlainText("\n".join(lines))


def _choice_combo(choices: tuple[ReleaseChoice, ...]) -> QComboBox:
    combo = QComboBox()
    for choice in choices:
        combo.addItem(choice.display_label, choice.slug)
    recommended_index = next((index for index, choice in enumerate(choices) if choice.recommended), 0)
    combo.setCurrentIndex(recommended_index)
    return combo
