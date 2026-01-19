"""Main application window."""

import os
import json
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QToolBar,
    QLabel, QSpinBox, QDoubleSpinBox, QComboBox, QPushButton,
    QColorDialog, QFileDialog, QMessageBox, QStatusBar, QSplitter,
    QFrame, QMenu, QGroupBox, QFormLayout, QDialog, QDialogButtonBox,
    QLineEdit, QListWidget, QListWidgetItem, QApplication
)
from PySide6.QtCore import Qt, QSettings, QTimer, Signal
from PySide6.QtGui import QAction, QIcon, QColor, QKeySequence, QFont, QFontDatabase
from typing import Optional
import fitz

from .pdf_viewer import PDFViewer
from .thumbnail_panel import ThumbnailPanel
from .annotation_list import AnnotationListPanel
from .models import NumberAnnotation, NumberStyle, AnnotationStore, StylePresets, parse_number
from .undo_manager import UndoManager, UndoAction


class StylePresetDialog(QDialog):
    """Dialog for managing style presets."""

    def __init__(self, presets: StylePresets, current_style: NumberStyle, parent=None):
        super().__init__(parent)
        self.presets = presets
        self.current_style = current_style
        self.selected_preset: Optional[str] = None

        self.setWindowTitle("Style Presets")
        self.setMinimumSize(300, 400)

        layout = QVBoxLayout(self)

        # List of presets
        self.list_widget = QListWidget()
        self._populate_list()
        self.list_widget.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.list_widget)

        # Save current as preset
        save_layout = QHBoxLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("New preset name...")
        save_layout.addWidget(self.name_edit)

        save_btn = QPushButton("Save Current")
        save_btn.clicked.connect(self._save_current)
        save_layout.addWidget(save_btn)
        layout.addLayout(save_layout)

        # Buttons
        btn_layout = QHBoxLayout()

        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(self._delete_selected)
        btn_layout.addWidget(delete_btn)

        btn_layout.addStretch()

        load_btn = QPushButton("Load")
        load_btn.clicked.connect(self._load_selected)
        btn_layout.addWidget(load_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _populate_list(self):
        self.list_widget.clear()
        for name in self.presets.names():
            self.list_widget.addItem(name)

    def _save_current(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Please enter a name for the preset.")
            return

        style = NumberStyle(**{
            'name': name,
            'font_family': self.current_style.font_family,
            'font_size': self.current_style.font_size,
            'text_color': self.current_style.text_color,
            'bg_color': self.current_style.bg_color,
            'bg_opacity': self.current_style.bg_opacity,
            'padding': self.current_style.padding,
        })
        self.presets.save(style)
        self._populate_list()
        self.name_edit.clear()

    def _delete_selected(self):
        item = self.list_widget.currentItem()
        if item:
            name = item.text()
            if name == "Default":
                QMessageBox.warning(self, "Error", "Cannot delete the default preset.")
                return
            self.presets.delete(name)
            self._populate_list()

    def _load_selected(self):
        item = self.list_widget.currentItem()
        if item:
            self.selected_preset = item.text()
            self.accept()

    def _on_double_click(self, item):
        self.selected_preset = item.text()
        self.accept()


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Napisy-TWON v2")
        self.setMinimumSize(1000, 700)

        # State
        self._current_file: Optional[str] = None
        self._style = NumberStyle()
        self._presets = StylePresets()
        self._undo_manager = UndoManager()
        self._recent_files: list[str] = []
        self._max_recent = 10

        # Settings
        self._settings = QSettings("NapisyTWON", "NapisyTWON2")
        self._load_settings()

        # Create UI
        self._create_actions()
        self._create_menus()
        self._create_toolbar()
        self._create_central_widget()
        self._create_statusbar()

        # Connect signals
        self._connect_signals()

        # Apply loaded settings
        self._apply_settings()

    def _create_actions(self):
        """Create all actions."""
        # File actions
        self.action_open = QAction("&Open PDF...", self)
        self.action_open.setShortcut(QKeySequence.StandardKey.Open)
        self.action_open.triggered.connect(self._open_file)

        self.action_save = QAction("&Save", self)
        self.action_save.setShortcut(QKeySequence.StandardKey.Save)
        self.action_save.triggered.connect(self._save_file)
        self.action_save.setEnabled(False)

        self.action_save_as = QAction("Save &As...", self)
        self.action_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.action_save_as.triggered.connect(self._save_file_as)
        self.action_save_as.setEnabled(False)

        self.action_export_image = QAction("&Export Page as Image...", self)
        self.action_export_image.setShortcut(QKeySequence("Ctrl+E"))
        self.action_export_image.triggered.connect(self._export_image)
        self.action_export_image.setEnabled(False)

        self.action_export_positions = QAction("Export Positions...", self)
        self.action_export_positions.triggered.connect(self._export_positions)

        self.action_import_positions = QAction("Import Positions...", self)
        self.action_import_positions.triggered.connect(self._import_positions)

        self.action_exit = QAction("E&xit", self)
        self.action_exit.setShortcut(QKeySequence.StandardKey.Quit)
        self.action_exit.triggered.connect(self.close)

        # Edit actions
        self.action_undo = QAction("&Undo", self)
        self.action_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.action_undo.triggered.connect(self._undo)
        self.action_undo.setEnabled(False)

        self.action_redo = QAction("&Redo", self)
        self.action_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self.action_redo.triggered.connect(self._redo)
        self.action_redo.setEnabled(False)

        self.action_delete = QAction("&Delete Selected", self)
        self.action_delete.setShortcut(QKeySequence.StandardKey.Delete)
        self.action_delete.triggered.connect(self._delete_selected)
        self.action_delete.setEnabled(False)

        self.action_clear_all = QAction("Clear &All Numbers", self)
        self.action_clear_all.triggered.connect(self._clear_all)

        # View actions
        self.action_zoom_in = QAction("Zoom &In", self)
        self.action_zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self.action_zoom_in.triggered.connect(lambda: self._viewer.zoom_in())

        self.action_zoom_out = QAction("Zoom &Out", self)
        self.action_zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self.action_zoom_out.triggered.connect(lambda: self._viewer.zoom_out())

        self.action_zoom_fit = QAction("&Fit to Window", self)
        self.action_zoom_fit.setShortcut(QKeySequence("Ctrl+0"))
        self.action_zoom_fit.triggered.connect(lambda: self._viewer.zoom_fit())

        self.action_zoom_100 = QAction("&Actual Size", self)
        self.action_zoom_100.setShortcut(QKeySequence("Ctrl+1"))
        self.action_zoom_100.triggered.connect(lambda: self._viewer.zoom_100())

        self.action_next_page = QAction("&Next Page", self)
        self.action_next_page.setShortcut(QKeySequence("Right"))
        self.action_next_page.triggered.connect(lambda: self._viewer.next_page())

        self.action_prev_page = QAction("&Previous Page", self)
        self.action_prev_page.setShortcut(QKeySequence("Left"))
        self.action_prev_page.triggered.connect(lambda: self._viewer.prev_page())

        # Style actions
        self.action_presets = QAction("Style &Presets...", self)
        self.action_presets.triggered.connect(self._show_presets)

    def _create_menus(self):
        """Create menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")
        file_menu.addAction(self.action_open)

        self.recent_menu = file_menu.addMenu("Recent Files")
        self._update_recent_menu()

        file_menu.addSeparator()
        file_menu.addAction(self.action_save)
        file_menu.addAction(self.action_save_as)
        file_menu.addSeparator()
        file_menu.addAction(self.action_export_image)
        file_menu.addAction(self.action_export_positions)
        file_menu.addAction(self.action_import_positions)
        file_menu.addSeparator()
        file_menu.addAction(self.action_exit)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")
        edit_menu.addAction(self.action_undo)
        edit_menu.addAction(self.action_redo)
        edit_menu.addSeparator()
        edit_menu.addAction(self.action_delete)
        edit_menu.addAction(self.action_clear_all)

        # View menu
        view_menu = menubar.addMenu("&View")
        view_menu.addAction(self.action_zoom_in)
        view_menu.addAction(self.action_zoom_out)
        view_menu.addAction(self.action_zoom_fit)
        view_menu.addAction(self.action_zoom_100)
        view_menu.addSeparator()
        view_menu.addAction(self.action_prev_page)
        view_menu.addAction(self.action_next_page)

        # Style menu
        style_menu = menubar.addMenu("&Style")
        style_menu.addAction(self.action_presets)

    def _create_toolbar(self):
        """Create main toolbar."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # Number settings
        toolbar.addWidget(QLabel(" Next #: "))
        self._number_spin = QSpinBox()
        self._number_spin.setRange(1, 9999)
        self._number_spin.setValue(1)
        self._number_spin.setFixedWidth(70)
        self._number_spin.valueChanged.connect(self._on_number_changed)
        toolbar.addWidget(self._number_spin)

        toolbar.addSeparator()

        # Font
        toolbar.addWidget(QLabel(" Font: "))
        self._font_combo = QComboBox()
        self._font_combo.setFixedWidth(150)
        families = QFontDatabase.families()
        self._font_combo.addItems(sorted(families))
        self._font_combo.setCurrentText("Arial")
        self._font_combo.currentTextChanged.connect(self._on_style_changed)
        toolbar.addWidget(self._font_combo)

        # Size
        toolbar.addWidget(QLabel(" Size: "))
        self._size_spin = QSpinBox()
        self._size_spin.setRange(8, 200)
        self._size_spin.setValue(48)
        self._size_spin.setFixedWidth(60)
        self._size_spin.valueChanged.connect(self._on_style_changed)
        toolbar.addWidget(self._size_spin)

        toolbar.addSeparator()

        # Colors
        toolbar.addWidget(QLabel(" Text: "))
        self._text_color_btn = QPushButton()
        self._text_color_btn.setFixedSize(30, 25)
        self._text_color_btn.setStyleSheet(f"background-color: {self._style.text_color};")
        self._text_color_btn.clicked.connect(self._choose_text_color)
        toolbar.addWidget(self._text_color_btn)

        toolbar.addWidget(QLabel(" BG: "))
        self._bg_color_btn = QPushButton()
        self._bg_color_btn.setFixedSize(30, 25)
        self._bg_color_btn.setStyleSheet(f"background-color: {self._style.bg_color};")
        self._bg_color_btn.clicked.connect(self._choose_bg_color)
        toolbar.addWidget(self._bg_color_btn)

        # Opacity
        toolbar.addWidget(QLabel(" Opacity: "))
        self._opacity_spin = QDoubleSpinBox()
        self._opacity_spin.setRange(0.0, 1.0)
        self._opacity_spin.setSingleStep(0.1)
        self._opacity_spin.setValue(1.0)
        self._opacity_spin.setFixedWidth(60)
        self._opacity_spin.valueChanged.connect(self._on_style_changed)
        toolbar.addWidget(self._opacity_spin)

        toolbar.addSeparator()

        # Presets button
        presets_btn = QPushButton("Presets")
        presets_btn.clicked.connect(self._show_presets)
        toolbar.addWidget(presets_btn)

        toolbar.addSeparator()

        # Page navigation
        toolbar.addWidget(QLabel(" Page: "))
        self._page_spin = QSpinBox()
        self._page_spin.setRange(1, 1)
        self._page_spin.setValue(1)
        self._page_spin.setFixedWidth(60)
        self._page_spin.valueChanged.connect(self._on_page_spin_changed)
        toolbar.addWidget(self._page_spin)

        self._page_total_label = QLabel(" / 0 ")
        toolbar.addWidget(self._page_total_label)

        # Zoom indicator
        self._zoom_label = QLabel(" Zoom: 100% ")
        toolbar.addWidget(self._zoom_label)

    def _create_central_widget(self):
        """Create the central widget with splitter."""
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Thumbnail panel
        self._thumbnail_panel = ThumbnailPanel()
        splitter.addWidget(self._thumbnail_panel)

        # PDF viewer
        self._viewer = PDFViewer()
        splitter.addWidget(self._viewer)

        # Annotation list panel
        self._annotation_panel = AnnotationListPanel()
        splitter.addWidget(self._annotation_panel)

        # Set sizes
        splitter.setSizes([150, 700, 200])

        self.setCentralWidget(splitter)

    def _create_statusbar(self):
        """Create status bar."""
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._statusbar.showMessage("Ready")

    def _connect_signals(self):
        """Connect signals between components."""
        # Viewer signals
        self._viewer.page_changed.connect(self._on_page_changed)
        self._viewer.zoom_changed.connect(self._on_zoom_changed)
        self._viewer.annotation_selected.connect(self._on_annotation_selected)
        self._viewer.annotation_added.connect(self._on_annotation_added)
        self._viewer.annotation_moved.connect(self._on_annotation_moved)
        self._viewer.annotation_deleted.connect(self._on_annotation_deleted)
        self._viewer.duplicate_number_requested.connect(self._on_duplicate_number_requested)

        # Thumbnail panel signals
        self._thumbnail_panel.page_selected.connect(self._viewer.go_to_page)

        # Annotation list panel signals
        self._annotation_panel.jump_to_annotation.connect(self._jump_to_annotation)
        self._annotation_panel.annotation_selected.connect(self._on_list_annotation_selected)
        self._annotation_panel.change_number_requested.connect(self._change_annotation_number)
        self._annotation_panel.delete_requested.connect(self._delete_annotation_with_options)

        # Undo manager signals
        self._undo_manager.state_changed.connect(self._update_undo_actions)

    def _load_settings(self):
        """Load application settings."""
        # Window geometry
        geometry = self._settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

        # Recent files
        recent = self._settings.value("recent_files", [])
        if isinstance(recent, list):
            self._recent_files = recent

        # Style presets
        presets_json = self._settings.value("style_presets")
        if presets_json:
            try:
                self._presets.from_json(presets_json)
            except:
                pass

        # Current style
        style_json = self._settings.value("current_style")
        if style_json:
            try:
                data = json.loads(style_json)
                self._style = NumberStyle.from_dict(data)
            except:
                pass

    def _save_settings(self):
        """Save application settings."""
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("recent_files", self._recent_files)
        self._settings.setValue("style_presets", self._presets.to_json())
        self._settings.setValue("current_style", json.dumps(self._style.to_dict()))

    def _apply_settings(self):
        """Apply loaded settings to UI."""
        self._font_combo.setCurrentText(self._style.font_family)
        self._size_spin.setValue(self._style.font_size)
        self._text_color_btn.setStyleSheet(f"background-color: {self._style.text_color};")
        self._bg_color_btn.setStyleSheet(f"background-color: {self._style.bg_color};")
        self._opacity_spin.setValue(self._style.bg_opacity)

    def _update_recent_menu(self):
        """Update the recent files menu."""
        self.recent_menu.clear()
        for path in self._recent_files:
            action = self.recent_menu.addAction(os.path.basename(path))
            action.setData(path)
            action.triggered.connect(lambda checked, p=path: self._open_recent(p))

        if self._recent_files:
            self.recent_menu.addSeparator()
            clear_action = self.recent_menu.addAction("Clear Recent")
            clear_action.triggered.connect(self._clear_recent)

    def _add_recent_file(self, path: str):
        """Add a file to recent files list."""
        if path in self._recent_files:
            self._recent_files.remove(path)
        self._recent_files.insert(0, path)
        self._recent_files = self._recent_files[:self._max_recent]
        self._update_recent_menu()

    def _clear_recent(self):
        """Clear recent files list."""
        self._recent_files.clear()
        self._update_recent_menu()

    def _open_recent(self, path: str):
        """Open a recent file."""
        if os.path.exists(path):
            self._do_open_file(path)
        else:
            QMessageBox.warning(self, "File Not Found", f"File not found:\n{path}")
            self._recent_files.remove(path)
            self._update_recent_menu()

    def _open_file(self):
        """Open a PDF file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open PDF", "",
            "PDF Files (*.pdf);;All Files (*.*)"
        )
        if path:
            self._do_open_file(path)

    def _do_open_file(self, path: str):
        """Actually open a PDF file."""
        if self._check_unsaved():
            return

        if self._viewer.open_document(path):
            self._current_file = path
            self._add_recent_file(path)
            self._update_title()
            self._enable_file_actions(True)
            self._undo_manager.clear()

            # Update thumbnail panel
            doc = self._viewer.get_document()
            if doc:
                self._thumbnail_panel.set_document(doc)

            # Update annotation panel
            self._refresh_annotation_panel()

            # Update page navigation
            self._on_page_changed(0)

            self._statusbar.showMessage(f"Opened: {os.path.basename(path)}")
        else:
            QMessageBox.warning(self, "Error", f"Could not open file:\n{path}")

    def _check_unsaved(self) -> bool:
        """Check for unsaved changes. Returns True if should cancel."""
        if self._viewer.get_annotations().modified:
            result = QMessageBox.question(
                self, "Unsaved Changes",
                "There are unsaved changes. Do you want to save?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel
            )
            if result == QMessageBox.StandardButton.Save:
                self._save_file()
                return False
            elif result == QMessageBox.StandardButton.Cancel:
                return True
        return False

    def _save_file(self):
        """Save the current file."""
        if not self._current_file:
            self._save_file_as()
            return

        self._do_save_file(self._current_file)

    def _save_file_as(self):
        """Save as a new file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save PDF As", "",
            "PDF Files (*.pdf)"
        )
        if path:
            self._do_save_file(path)

    def _do_save_file(self, path: str):
        """Actually save the PDF file."""
        doc = self._viewer.get_document()
        if not doc:
            return

        try:
            # Apply annotations to PDF
            annotations = self._viewer.get_annotations()
            for annotation in annotations.all():
                if annotation.applied_to_pdf:
                    continue

                page = doc.load_page(annotation.page)
                style = annotation.style
                text = str(annotation.number)

                # Convert colors
                def hex_to_rgb(hex_color):
                    hex_color = hex_color.lstrip('#')
                    return tuple(int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4))

                fg_rgb = hex_to_rgb(style.text_color)
                bg_rgb = hex_to_rgb(style.bg_color) if style.bg_opacity > 0 else None

                # Calculate rect
                text_width = len(text) * style.font_size * 0.6
                text_height = style.font_size * 1.2
                padding = style.padding

                rect = fitz.Rect(
                    annotation.x,
                    annotation.y,
                    annotation.x + text_width + padding * 2,
                    annotation.y + text_height + padding
                )

                # Add annotation
                annot = page.add_freetext_annot(
                    rect,
                    text,
                    fontsize=style.font_size,
                    fontname="helv",
                    text_color=fg_rgb,
                    fill_color=bg_rgb,
                    align=fitz.TEXT_ALIGN_CENTER
                )
                if bg_rgb and style.bg_opacity < 1.0:
                    annot.set_opacity(style.bg_opacity)
                annot.update()

                annotation.applied_to_pdf = True

            # Save
            doc.save(path, garbage=4, deflate=True)

            self._current_file = path
            annotations.modified = False
            self._update_title()
            self._statusbar.showMessage(f"Saved: {os.path.basename(path)}")

        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))

    def _export_image(self):
        """Export current page as image."""
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "Export Page as Image", "",
            "PNG Image (*.png);;JPEG Image (*.jpg);;All Files (*.*)"
        )
        if not path:
            return

        # Determine format
        if path.lower().endswith('.jpg') or path.lower().endswith('.jpeg'):
            fmt = "JPG"
        else:
            fmt = "PNG"
            if not path.lower().endswith('.png'):
                path += '.png'

        # Get image
        page = self._viewer.current_page()
        img = self._viewer.get_page_image(page, scale=2.0)
        if img:
            img.save(path, fmt)
            self._statusbar.showMessage(f"Exported: {os.path.basename(path)}")

    def _export_positions(self):
        """Export annotation positions to JSON."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Positions", "",
            "JSON Files (*.json)"
        )
        if not path:
            return

        if not path.lower().endswith('.json'):
            path += '.json'

        try:
            with open(path, 'w') as f:
                f.write(self._viewer.get_annotations().to_json())
            self._statusbar.showMessage(f"Exported positions: {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def _import_positions(self):
        """Import annotation positions from JSON."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Positions", "",
            "JSON Files (*.json)"
        )
        if not path:
            return

        try:
            with open(path, 'r') as f:
                json_str = f.read()

            annotations = self._viewer.get_annotations()
            annotations.from_json(json_str)
            self._viewer.set_annotations(annotations)
            self._refresh_annotation_panel()
            self._update_title()
            self._update_thumbnail_indicators()
            self._statusbar.showMessage(f"Imported positions: {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.critical(self, "Import Error", str(e))

    def _enable_file_actions(self, enabled: bool):
        """Enable/disable file-related actions."""
        self.action_save.setEnabled(enabled)
        self.action_save_as.setEnabled(enabled)
        self.action_export_image.setEnabled(enabled)

    def _update_title(self):
        """Update window title."""
        title = "Napisy-TWON v2"
        if self._current_file:
            title += f" - {os.path.basename(self._current_file)}"
        if self._viewer.get_annotations().modified:
            title += " *"
        self.setWindowTitle(title)

    def _on_page_changed(self, page: int):
        """Handle page change."""
        total = self._viewer.page_count()
        # Update page spinbox without triggering signal
        self._page_spin.blockSignals(True)
        self._page_spin.setRange(1, max(1, total))
        self._page_spin.setValue(page + 1)
        self._page_spin.blockSignals(False)
        self._page_total_label.setText(f" / {total} ")
        self._thumbnail_panel.set_current_page(page)

    def _on_page_spin_changed(self, value: int):
        """Handle page spinbox value change."""
        self._viewer.go_to_page(value - 1)

    def _on_zoom_changed(self, zoom: float):
        """Handle zoom change."""
        self._zoom_label.setText(f" Zoom: {int(zoom * 100)}% ")

    def _on_annotation_selected(self, annotation):
        """Handle annotation selection."""
        self.action_delete.setEnabled(annotation is not None)
        if annotation:
            self._statusbar.showMessage(f"Selected: #{annotation.number}")
        else:
            self._statusbar.showMessage("Ready")

    def _on_annotation_added(self, annotation: NumberAnnotation):
        """Handle new annotation added."""
        # Update next number spinner (only for whole numbers)
        main, sub = parse_number(annotation.number)
        if sub == 0:
            self._number_spin.setValue(main + 1)

        self._update_title()
        self._update_thumbnail_indicators()
        self._refresh_annotation_panel()

        # Add undo action
        action = UndoAction(
            description=f"Add #{annotation.number}",
            undo_data=annotation,
            redo_data=annotation,
            undo_func=lambda a: self._undo_add_annotation(a),
            redo_func=lambda a: self._redo_add_annotation(a)
        )
        self._undo_manager.push(action)

        self._statusbar.showMessage(f"Added: #{annotation.number}")

    def _undo_add_annotation(self, annotation: NumberAnnotation):
        """Undo adding an annotation."""
        self._viewer.delete_annotation(annotation)
        self._refresh_annotation_panel()

    def _redo_add_annotation(self, annotation: NumberAnnotation):
        """Redo adding an annotation."""
        self._viewer.add_annotation(annotation)
        self._refresh_annotation_panel()

    def _on_annotation_moved(self, annotation: NumberAnnotation, old_x: float, old_y: float):
        """Handle annotation moved."""
        self._update_title()

        new_x, new_y = annotation.x, annotation.y

        action = UndoAction(
            description=f"Move #{annotation.number}",
            undo_data=(annotation, new_x, new_y, old_x, old_y),
            redo_data=(annotation, old_x, old_y, new_x, new_y),
            undo_func=lambda d: self._move_annotation(d[0], d[3], d[4]),
            redo_func=lambda d: self._move_annotation(d[0], d[3], d[4])
        )
        self._undo_manager.push(action)

    def _move_annotation(self, annotation: NumberAnnotation, x: float, y: float):
        """Move an annotation to a position."""
        annotation.x = x
        annotation.y = y
        # Refresh display
        page = self._viewer.current_page()
        if annotation.page == page:
            self._viewer.go_to_page(page)

    def _on_annotation_deleted(self, annotation: NumberAnnotation):
        """Handle annotation deleted."""
        self._update_title()
        self._update_thumbnail_indicators()
        self._refresh_annotation_panel()

        action = UndoAction(
            description=f"Delete #{annotation.number}",
            undo_data=annotation,
            redo_data=annotation,
            undo_func=lambda a: self._undo_delete_annotation(a),
            redo_func=lambda a: self._redo_delete_annotation(a)
        )
        self._undo_manager.push(action)

        self._statusbar.showMessage(f"Deleted: #{annotation.number}")

    def _undo_delete_annotation(self, annotation: NumberAnnotation):
        """Undo deleting an annotation."""
        self._viewer.add_annotation(annotation)
        self._refresh_annotation_panel()

    def _redo_delete_annotation(self, annotation: NumberAnnotation):
        """Redo deleting an annotation."""
        self._viewer.delete_annotation(annotation)
        self._refresh_annotation_panel()

    def _update_thumbnail_indicators(self):
        """Update annotation indicators on thumbnails."""
        annotations = self._viewer.get_annotations()
        by_page = {}
        for a in annotations.all():
            by_page[a.page] = by_page.get(a.page, 0) + 1
        self._thumbnail_panel.update_annotation_indicators(by_page)

    def _on_number_changed(self, value: int):
        """Handle next number changed."""
        self._viewer.set_next_number(str(value))

    def _on_style_changed(self):
        """Handle style settings changed."""
        self._style.font_family = self._font_combo.currentText()
        self._style.font_size = self._size_spin.value()
        self._style.bg_opacity = self._opacity_spin.value()
        self._viewer.set_style(self._style)

    def _choose_text_color(self):
        """Open color picker for text color."""
        color = QColorDialog.getColor(QColor(self._style.text_color), self)
        if color.isValid():
            self._style.text_color = color.name()
            self._text_color_btn.setStyleSheet(f"background-color: {color.name()};")
            self._on_style_changed()

    def _choose_bg_color(self):
        """Open color picker for background color."""
        color = QColorDialog.getColor(QColor(self._style.bg_color), self)
        if color.isValid():
            self._style.bg_color = color.name()
            self._bg_color_btn.setStyleSheet(f"background-color: {color.name()};")
            self._on_style_changed()

    def _show_presets(self):
        """Show style presets dialog."""
        dialog = StylePresetDialog(self._presets, self._style, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_preset:
            style = self._presets.get(dialog.selected_preset)
            if style:
                self._style = style
                self._apply_settings()
                self._on_style_changed()

    def _undo(self):
        """Undo last action."""
        desc = self._undo_manager.undo()
        if desc:
            self._statusbar.showMessage(f"Undo: {desc}")
            self._update_title()

    def _redo(self):
        """Redo last undone action."""
        desc = self._undo_manager.redo()
        if desc:
            self._statusbar.showMessage(f"Redo: {desc}")
            self._update_title()

    def _update_undo_actions(self):
        """Update undo/redo action states."""
        self.action_undo.setEnabled(self._undo_manager.can_undo())
        self.action_redo.setEnabled(self._undo_manager.can_redo())

        undo_desc = self._undo_manager.undo_description()
        redo_desc = self._undo_manager.redo_description()

        self.action_undo.setText(f"&Undo {undo_desc}" if undo_desc else "&Undo")
        self.action_redo.setText(f"&Redo {redo_desc}" if redo_desc else "&Redo")

    def _delete_selected(self):
        """Delete selected annotation."""
        # Trigger delete in viewer via key event
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtCore import QEvent
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
        self._viewer.keyPressEvent(event)

    def _clear_all(self):
        """Clear all annotations."""
        result = QMessageBox.question(
            self, "Clear All",
            "Delete all annotations?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if result == QMessageBox.StandardButton.Yes:
            annotations = self._viewer.get_annotations()
            annotations.clear()
            self._viewer.set_annotations(annotations)
            self._undo_manager.clear()
            self._refresh_annotation_panel()
            self._update_title()
            self._update_thumbnail_indicators()
            self._statusbar.showMessage("Cleared all annotations")

    def _refresh_annotation_panel(self):
        """Refresh the annotation list panel."""
        self._annotation_panel.set_annotations(self._viewer.get_annotations())

    def _on_duplicate_number_requested(self, number: str, pdf_x: float, pdf_y: float):
        """Handle when user tries to insert a duplicate number."""
        annotations = self._viewer.get_annotations()

        # Show dialog with options
        msg = QMessageBox(self)
        msg.setWindowTitle("Number Already Exists")
        msg.setText(f"Number {number} already exists.")
        msg.setInformativeText("What would you like to do?")

        advance_btn = msg.addButton("Auto-advance others", QMessageBox.ButtonRole.ActionRole)
        sub_btn = msg.addButton("Use sub-number", QMessageBox.ButtonRole.ActionRole)
        cancel_btn = msg.addButton(QMessageBox.StandardButton.Cancel)

        msg.exec()

        if msg.clickedButton() == advance_btn:
            # Auto-advance all numbers >= number
            changes = annotations.advance_numbers_from(number, 1)
            # Now insert the annotation with the original number
            self._viewer.insert_annotation_at(pdf_x, pdf_y, number)
            self._viewer.refresh_page()
            self._refresh_annotation_panel()
            self._statusbar.showMessage(f"Inserted #{number}, advanced {len(changes)} others")

        elif msg.clickedButton() == sub_btn:
            # Use next available sub-number
            main, _ = parse_number(number)
            sub_num = annotations.get_next_sub_number(str(main))
            self._viewer.insert_annotation_at(pdf_x, pdf_y, sub_num)
            self._statusbar.showMessage(f"Inserted #{sub_num}")

    def _jump_to_annotation(self, annotation: NumberAnnotation):
        """Jump to an annotation's location."""
        self._viewer.go_to_page(annotation.page)
        self._viewer.select_annotation(annotation)
        self._viewer.center_on_annotation(annotation)

    def _on_list_annotation_selected(self, annotation: NumberAnnotation):
        """Handle annotation selected in the list."""
        if annotation.page == self._viewer.current_page():
            self._viewer.select_annotation(annotation)

    def _change_annotation_number(self, annotation: NumberAnnotation):
        """Show dialog to change an annotation's number."""
        from PySide6.QtWidgets import QInputDialog

        annotations = self._viewer.get_annotations()
        current_num = annotation.number

        new_num, ok = QInputDialog.getText(
            self, "Change Number",
            f"Enter new number for #{current_num}:",
            text=current_num
        )

        if not ok or not new_num.strip():
            return

        new_num = new_num.strip()

        # Validate the number format
        try:
            parse_number(new_num)
        except (ValueError, IndexError):
            QMessageBox.warning(self, "Invalid Number",
                                "Please enter a valid number (e.g., 67 or 67.1)")
            return

        # Check for duplicates
        if annotations.has_number(new_num) and new_num != current_num:
            self._handle_duplicate_number(annotation, new_num)
        else:
            self._do_change_number(annotation, new_num)

    def _handle_duplicate_number(self, annotation: NumberAnnotation, new_num: str):
        """Handle when user tries to change to an existing number."""
        annotations = self._viewer.get_annotations()

        # Show dialog with options
        msg = QMessageBox(self)
        msg.setWindowTitle("Number Already Exists")
        msg.setText(f"Number {new_num} already exists.")
        msg.setInformativeText("What would you like to do?")

        advance_btn = msg.addButton("Auto-advance others", QMessageBox.ButtonRole.ActionRole)
        sub_btn = msg.addButton("Use sub-number", QMessageBox.ButtonRole.ActionRole)
        cancel_btn = msg.addButton(QMessageBox.StandardButton.Cancel)

        msg.exec()

        if msg.clickedButton() == advance_btn:
            # Auto-advance all numbers >= new_num
            old_num = annotation.number
            changes = annotations.advance_numbers_from(new_num, 1)
            annotation.number = new_num
            self._viewer.refresh_page()
            self._refresh_annotation_panel()
            self._update_title()
            self._statusbar.showMessage(f"Changed #{old_num} to #{new_num}, advanced {len(changes)} others")

        elif msg.clickedButton() == sub_btn:
            # Use next available sub-number
            main, _ = parse_number(new_num)
            sub_num = annotations.get_next_sub_number(str(main))
            self._do_change_number(annotation, sub_num)

    def _do_change_number(self, annotation: NumberAnnotation, new_num: str):
        """Actually change an annotation's number."""
        old_num = annotation.number
        annotation.number = new_num

        self._viewer.refresh_page()
        self._refresh_annotation_panel()
        self._update_title()

        # Add undo action
        action = UndoAction(
            description=f"Change #{old_num} to #{new_num}",
            undo_data=(annotation, old_num, new_num),
            redo_data=(annotation, new_num, old_num),
            undo_func=lambda d: self._restore_number(d[0], d[1]),
            redo_func=lambda d: self._restore_number(d[0], d[1])
        )
        self._undo_manager.push(action)

        self._statusbar.showMessage(f"Changed: #{old_num} to #{new_num}")

    def _restore_number(self, annotation: NumberAnnotation, number: str):
        """Restore an annotation's number (for undo/redo)."""
        annotation.number = number
        self._viewer.refresh_page()
        self._refresh_annotation_panel()

    def _delete_annotation_with_options(self, annotation: NumberAnnotation):
        """Delete an annotation with option to auto-decrease following numbers."""
        annotations = self._viewer.get_annotations()
        main, sub = parse_number(annotation.number)

        # Only offer auto-decrease for whole numbers
        if sub == 0:
            msg = QMessageBox(self)
            msg.setWindowTitle("Delete Annotation")
            msg.setText(f"Delete annotation #{annotation.number}?")
            msg.setInformativeText("Do you want to auto-decrease following numbers?")

            decrease_btn = msg.addButton("Delete && decrease others", QMessageBox.ButtonRole.ActionRole)
            delete_btn = msg.addButton("Delete only", QMessageBox.ButtonRole.ActionRole)
            cancel_btn = msg.addButton(QMessageBox.StandardButton.Cancel)

            msg.exec()

            if msg.clickedButton() == cancel_btn:
                return

            if msg.clickedButton() == decrease_btn:
                # First collect changes, then delete and apply
                changes = annotations.decrease_numbers_from(annotation.number, 1)
                self._viewer.delete_annotation(annotation)
                self._viewer.refresh_page()
                self._refresh_annotation_panel()
                self._update_title()
                self._update_thumbnail_indicators()
                self._statusbar.showMessage(f"Deleted #{annotation.number}, decreased {len(changes)} others")
                return

            # Fall through to regular delete
            if msg.clickedButton() == delete_btn:
                self._viewer.delete_annotation(annotation)
        else:
            # Sub-numbers: just confirm deletion
            result = QMessageBox.question(
                self, "Delete Annotation",
                f"Delete annotation #{annotation.number}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if result == QMessageBox.StandardButton.Yes:
                self._viewer.delete_annotation(annotation)

    def closeEvent(self, event):
        """Handle window close."""
        if self._check_unsaved():
            event.ignore()
            return

        self._save_settings()
        self._viewer.close_document()
        event.accept()
