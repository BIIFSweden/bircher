import re
from collections.abc import Sequence
from pathlib import Path

from qtpy.QtCore import QObject, QThread, Signal
from qtpy.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .models import Image
from .utils import write_archive
from .widgets import ConsensusImageList, ImageTableModel, ImageTableView


class MainWindow(QMainWindow):
    class ArchiveWriterThread(QThread):
        step = Signal(int, Image)
        completed = Signal()
        error = Signal(Exception)

        def __init__(
            self,
            archive_file: str | Path,
            images: Sequence[Image],
            parent: QObject | None = None,
        ) -> None:
            super().__init__(parent)
            self._archive_file = archive_file
            self._images = images

        def run(self) -> None:
            try:
                archive_writer = write_archive(self._archive_file, self._images)
                for i, img in enumerate(archive_writer):
                    self.step.emit(i, img)
                self.completed.emit()
            except Exception as e:
                self.error.emit(e)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._thread: MainWindow.ArchiveWriterThread | None = None
        central_widget = QWidget()
        central_widget_layout = QVBoxLayout()
        self._images = ConsensusImageList()
        self._image_table_model = ImageTableModel(self._images)
        self._image_table_model.modelReset.connect(lambda: self._update_button_states())
        self._image_table_model.dataChanged.connect(
            lambda top_left, bottom_right: self._update_button_states()
        )
        self._images.set_model(self._image_table_model)
        self._image_table_view = ImageTableView(self._images)
        self._image_table_view.setModel(self._image_table_model)
        self._image_table_view.selectionModel().selectionChanged.connect(
            lambda selected, deselected: self._update_button_states()
        )
        central_widget_layout.addWidget(self._image_table_view)
        regex_and_buttons_widget = QWidget()
        regex_and_buttons_layout = QHBoxLayout()
        self._regex_line_edit = QLineEdit()
        self._regex_line_edit.setPlaceholderText(
            "POSIX file path pattern (Python regular expression, optional)"
        )
        self._regex_line_edit.textChanged.connect(self._on_regex_line_edit_text_changed)
        regex_and_buttons_layout.addWidget(self._regex_line_edit)
        self._remove_selected_rows_button = QPushButton("Remove selected rows")
        self._remove_selected_rows_button.clicked.connect(
            self._on_remove_selected_rows_button_clicked
        )
        regex_and_buttons_layout.addWidget(self._remove_selected_rows_button)
        self._create_archive_button = QPushButton("Create archive")
        self._create_archive_button.clicked.connect(
            self._on_create_archive_button_clicked
        )
        regex_and_buttons_layout.addWidget(self._create_archive_button)
        regex_and_buttons_widget.setLayout(regex_and_buttons_layout)
        central_widget_layout.addWidget(regex_and_buttons_widget)
        central_widget.setLayout(central_widget_layout)
        self.setCentralWidget(central_widget)
        self._status_bar = QStatusBar()
        self._status_bar.showMessage("Ready")
        self._progress_bar = QProgressBar()
        self._progress_bar.setHidden(True)
        self._status_bar.addPermanentWidget(self._progress_bar)
        self.setStatusBar(self._status_bar)
        self.setGeometry(100, 100, 800, 600)
        self.setWindowTitle("bircher")
        self._update_button_states()

    def _on_regex_line_edit_text_changed(self, text: str) -> None:
        if text:
            try:
                posix_path_pattern = re.compile(text)
                self._regex_line_edit.setStyleSheet("background-color: white")
            except re.error:
                posix_path_pattern = None
                self._regex_line_edit.setStyleSheet("background-color: red")
        else:
            posix_path_pattern = None
            self._regex_line_edit.setStyleSheet("background-color: white")
        self._image_table_model.set_posix_path_pattern(posix_path_pattern)

    def _on_remove_selected_rows_button_clicked(self) -> None:
        for index in sorted(
            self._image_table_view.selectionModel().selectedRows(),
            key=lambda index: index.row(),
            reverse=True,
        ):
            self._images.pop(index.row())

    def _on_create_archive_button_clicked(self) -> None:
        archive_file, selected_filter = QFileDialog.getSaveFileName(
            parent=self,
            dir=str(Path.home() / "Untitled"),
            filter="Image archive (*.tar.gz)",
            selectedFilter="Image archive (*.tar.gz)",
        )
        if archive_file:
            self._thread = MainWindow.ArchiveWriterThread(archive_file, self._images)
            self._update_button_states()

            @self._thread.step.connect
            def on_thread_step(i, img):
                self._progress_bar.setValue(i + 1)

            @self._thread.completed.connect
            def on_thread_completed():
                self._status_bar.showMessage("Archive created")
                self._progress_bar.setHidden(True)
                self._thread = None
                self._update_button_states()

            @self._thread.error.connect
            def on_thread_error(e):
                self._status_bar.showMessage(f"Error: {e}")
                self._progress_bar.setHidden(True)
                self._thread = None
                self._update_button_states()

            self._status_bar.showMessage("Creating archive...")
            self._progress_bar.setMaximum(len(self._images))
            self._progress_bar.setHidden(False)
            self._progress_bar.setValue(0)
            self._thread.start()

    def _update_button_states(self) -> None:
        self._remove_selected_rows_button.setEnabled(
            self._thread is None
            and self._image_table_view.selectionModel().hasSelection()
        )
        self._create_archive_button.setEnabled(
            self._thread is None
            and len(self._images) > 0
            and len(set(img.posix_path for img in self._images)) == len(self._images)
        )

    @property
    def image_table_model(self) -> ImageTableModel:
        return self._image_table_model
