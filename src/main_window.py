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

from .pdf_viewer import PDFViewer, ToolMode
from .annotation_list import AnnotationListPanel
from .models import NumberAnnotation, NumberStyle, AnnotationStore, StylePresets, parse_number
from .undo_manager import UndoManager, UndoAction
from .translations import tr, Translator


class StylePresetDialog(QDialog):
    """Dialog for managing style presets."""

    def __init__(self, presets: StylePresets, current_style: NumberStyle, parent=None):
        super().__init__(parent)
        self.presets = presets
        self.current_style = current_style
        self.selected_preset: Optional[str] = None

        self.setWindowTitle(tr("Style Presets"))
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
        self.name_edit.setPlaceholderText(tr("New preset name..."))
        save_layout.addWidget(self.name_edit)

        save_btn = QPushButton(tr("Save Current"))
        save_btn.clicked.connect(self._save_current)
        save_layout.addWidget(save_btn)
        layout.addLayout(save_layout)

        # Buttons
        btn_layout = QHBoxLayout()

        delete_btn = QPushButton(tr("Delete"))
        delete_btn.clicked.connect(self._delete_selected)
        btn_layout.addWidget(delete_btn)

        btn_layout.addStretch()

        load_btn = QPushButton(tr("Load"))
        load_btn.clicked.connect(self._load_selected)
        btn_layout.addWidget(load_btn)

        close_btn = QPushButton(tr("Close"))
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
            QMessageBox.warning(self, tr("Error"), tr("Please enter a name for the preset."))
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
            if name == tr("Default"):
                QMessageBox.warning(self, tr("Error"), tr("Cannot delete the default preset."))
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
        self.setWindowTitle("NapisyTWON")
        self.setMinimumSize(1000, 700)

        # State
        self._current_file: Optional[str] = None
        self._style = NumberStyle()
        self._presets = StylePresets()
        self._undo_manager = UndoManager()
        self._recent_files: list[str] = []
        self._max_recent = 10
        self._empty_mode = False  # For "pusty" (empty) slide marking

        # Settings
        self._settings = QSettings("NapisyTWON", "NapisyTWON")
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
        self.action_open = QAction(tr("&Open PDF..."), self)
        self.action_open.setShortcut(QKeySequence.StandardKey.Open)
        self.action_open.triggered.connect(self._open_file)

        self.action_save = QAction(tr("&Save"), self)
        self.action_save.setShortcut(QKeySequence.StandardKey.Save)
        self.action_save.triggered.connect(self._save_file)
        self.action_save.setEnabled(False)

        self.action_save_as = QAction(tr("Save &As..."), self)
        self.action_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.action_save_as.triggered.connect(self._save_file_as)
        self.action_save_as.setEnabled(False)


        self.action_exit = QAction(tr("E&xit"), self)
        self.action_exit.setShortcut(QKeySequence.StandardKey.Quit)
        self.action_exit.triggered.connect(self.close)

        # Edit actions
        self.action_undo = QAction(tr("&Undo"), self)
        self.action_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.action_undo.triggered.connect(self._undo)
        self.action_undo.setEnabled(False)

        self.action_redo = QAction(tr("&Redo"), self)
        self.action_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self.action_redo.triggered.connect(self._redo)
        self.action_redo.setEnabled(False)

        self.action_delete = QAction(tr("&Delete Selected"), self)
        self.action_delete.setShortcut(QKeySequence.StandardKey.Delete)
        self.action_delete.triggered.connect(self._delete_selected)
        self.action_delete.setEnabled(False)

        self.action_clear_all = QAction(tr("Clear &All Numbers"), self)
        self.action_clear_all.triggered.connect(self._clear_all)

        # View actions
        self.action_zoom_in = QAction(tr("Zoom &In"), self)
        self.action_zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self.action_zoom_in.triggered.connect(lambda: self._viewer.zoom_in())

        self.action_zoom_out = QAction(tr("Zoom &Out"), self)
        self.action_zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self.action_zoom_out.triggered.connect(lambda: self._viewer.zoom_out())

        self.action_zoom_fit = QAction(tr("&Fit to Window"), self)
        self.action_zoom_fit.setShortcut(QKeySequence("Ctrl+0"))
        self.action_zoom_fit.triggered.connect(lambda: self._viewer.zoom_fit())

        self.action_zoom_100 = QAction(tr("&Actual Size"), self)
        self.action_zoom_100.setShortcut(QKeySequence("Ctrl+1"))
        self.action_zoom_100.triggered.connect(lambda: self._viewer.zoom_100())

        self.action_next_page = QAction(tr("&Next Page"), self)
        self.action_next_page.setShortcut(QKeySequence("Right"))
        self.action_next_page.triggered.connect(lambda: self._viewer.next_page())

        self.action_prev_page = QAction(tr("&Previous Page"), self)
        self.action_prev_page.setShortcut(QKeySequence("Left"))
        self.action_prev_page.triggered.connect(lambda: self._viewer.prev_page())

        # Style actions
        self.action_presets = QAction(tr("Style &Presets..."), self)
        self.action_presets.triggered.connect(self._show_presets)

    def _create_menus(self):
        """Create menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu(tr("&File"))
        file_menu.addAction(self.action_open)

        self.recent_menu = file_menu.addMenu(tr("Recent Files"))
        self._update_recent_menu()

        file_menu.addSeparator()
        file_menu.addAction(self.action_save)
        file_menu.addAction(self.action_save_as)
        file_menu.addSeparator()
        file_menu.addAction(self.action_exit)

        # Edit menu
        edit_menu = menubar.addMenu(tr("&Edit"))
        edit_menu.addAction(self.action_undo)
        edit_menu.addAction(self.action_redo)
        edit_menu.addSeparator()
        edit_menu.addAction(self.action_delete)
        edit_menu.addAction(self.action_clear_all)

        # View menu
        view_menu = menubar.addMenu(tr("&View"))
        view_menu.addAction(self.action_zoom_in)
        view_menu.addAction(self.action_zoom_out)
        view_menu.addAction(self.action_zoom_fit)
        view_menu.addAction(self.action_zoom_100)
        view_menu.addSeparator()
        view_menu.addAction(self.action_prev_page)
        view_menu.addAction(self.action_next_page)

        # Style menu
        style_menu = menubar.addMenu(tr("&Style"))
        style_menu.addAction(self.action_presets)
        style_menu.addSeparator()
        save_as_default_action = style_menu.addAction(tr("Save Current as Default"))
        save_as_default_action.triggered.connect(self._save_style_as_default)
        reset_style_action = style_menu.addAction(tr("Reset Style to Defaults"))
        reset_style_action.triggered.connect(self._reset_style_to_defaults)

        # Language menu
        lang_menu = menubar.addMenu(tr("&Language"))
        action_english = lang_menu.addAction("English")
        action_english.triggered.connect(lambda: self._set_language("en"))
        action_polish = lang_menu.addAction("Polski")
        action_polish.triggered.connect(lambda: self._set_language("pl"))

    def _create_toolbar(self):
        """Create main toolbar."""
        toolbar = QToolBar(tr("Main Toolbar"))
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # Tool mode buttons
        toolbar.addWidget(QLabel(tr(" Tool: ")))
        self._insert_tool_btn = QPushButton(tr("Insert"))
        self._insert_tool_btn.setCheckable(True)
        self._insert_tool_btn.setChecked(True)
        self._insert_tool_btn.clicked.connect(lambda: self._set_tool_mode(ToolMode.INSERT))
        toolbar.addWidget(self._insert_tool_btn)

        self._select_tool_btn = QPushButton(tr("Select"))
        self._select_tool_btn.setCheckable(True)
        self._select_tool_btn.clicked.connect(lambda: self._set_tool_mode(ToolMode.SELECT))
        toolbar.addWidget(self._select_tool_btn)

        toolbar.addSeparator()

        # Number settings
        toolbar.addWidget(QLabel(tr(" Next #: ")))
        self._number_edit = QLineEdit()
        self._number_edit.setText("1")
        self._number_edit.setFixedWidth(70)
        self._number_edit.editingFinished.connect(self._on_number_edited)
        toolbar.addWidget(self._number_edit)

        # Empty mode checkbox (for "pusty" slides)
        from PySide6.QtWidgets import QCheckBox
        self._empty_check = QCheckBox(tr("Empty (p)"))
        self._empty_check.setChecked(False)
        self._empty_check.setToolTip("Press 'p' to toggle")
        self._empty_check.stateChanged.connect(self._on_empty_mode_changed)
        toolbar.addWidget(self._empty_check)

        toolbar.addSeparator()

        # Font
        toolbar.addWidget(QLabel(tr(" Font: ")))
        self._font_combo = QComboBox()
        self._font_combo.setFixedWidth(150)
        families = QFontDatabase.families()
        self._font_combo.addItems(sorted(families))
        self._font_combo.setCurrentText("Arial")
        self._font_combo.currentTextChanged.connect(self._on_style_changed)
        toolbar.addWidget(self._font_combo)

        # Size
        toolbar.addWidget(QLabel(tr(" Size: ")))
        self._size_spin = QSpinBox()
        self._size_spin.setRange(8, 200)
        self._size_spin.setValue(48)
        self._size_spin.setFixedWidth(60)
        self._size_spin.valueChanged.connect(self._on_style_changed)
        toolbar.addWidget(self._size_spin)

        toolbar.addSeparator()

        # Colors
        toolbar.addWidget(QLabel(tr(" Text: ")))
        self._text_color_btn = QPushButton()
        self._text_color_btn.setFixedSize(30, 25)
        self._text_color_btn.setStyleSheet(f"background-color: {self._style.text_color};")
        self._text_color_btn.clicked.connect(self._choose_text_color)
        toolbar.addWidget(self._text_color_btn)

        toolbar.addWidget(QLabel(tr(" BG: ")))
        self._bg_color_btn = QPushButton()
        self._bg_color_btn.setFixedSize(30, 25)
        self._bg_color_btn.setStyleSheet(f"background-color: {self._style.bg_color};")
        self._bg_color_btn.clicked.connect(self._choose_bg_color)
        toolbar.addWidget(self._bg_color_btn)

        # Opacity
        toolbar.addWidget(QLabel(tr(" Opacity: ")))
        self._opacity_spin = QDoubleSpinBox()
        self._opacity_spin.setRange(0.0, 1.0)
        self._opacity_spin.setSingleStep(0.1)
        self._opacity_spin.setValue(1.0)
        self._opacity_spin.setFixedWidth(60)
        self._opacity_spin.valueChanged.connect(self._on_style_changed)
        toolbar.addWidget(self._opacity_spin)

        toolbar.addSeparator()

        # Border settings
        from PySide6.QtWidgets import QCheckBox
        self._border_check = QCheckBox(tr("Border"))
        self._border_check.setChecked(True)  # Match NumberStyle default
        self._border_check.stateChanged.connect(self._on_style_changed)
        toolbar.addWidget(self._border_check)

        self._border_width_spin = QSpinBox()
        self._border_width_spin.setRange(1, 20)
        self._border_width_spin.setValue(1)  # Match NumberStyle default
        self._border_width_spin.setFixedWidth(50)
        self._border_width_spin.setToolTip(tr("Border width"))
        self._border_width_spin.valueChanged.connect(self._on_style_changed)
        toolbar.addWidget(self._border_width_spin)

        toolbar.addSeparator()

        # Tail settings (vertical line going down from center bottom)
        self._tail_check = QCheckBox(tr("Tail"))
        self._tail_check.setChecked(True)  # Match NumberStyle default
        self._tail_check.stateChanged.connect(self._on_style_changed)
        toolbar.addWidget(self._tail_check)

        toolbar.addWidget(QLabel(tr(" L:")))
        self._tail_length_spin = QSpinBox()
        self._tail_length_spin.setRange(5, 200)
        self._tail_length_spin.setValue(100)  # Match NumberStyle default
        self._tail_length_spin.setFixedWidth(50)
        self._tail_length_spin.setToolTip(tr("Tail length"))
        self._tail_length_spin.valueChanged.connect(self._on_style_changed)
        toolbar.addWidget(self._tail_length_spin)

        toolbar.addWidget(QLabel(tr(" W:")))
        self._tail_width_spin = QSpinBox()
        self._tail_width_spin.setRange(1, 20)
        self._tail_width_spin.setValue(2)  # Match NumberStyle default
        self._tail_width_spin.setFixedWidth(50)
        self._tail_width_spin.setToolTip(tr("Tail width"))
        self._tail_width_spin.valueChanged.connect(self._on_style_changed)
        toolbar.addWidget(self._tail_width_spin)

        toolbar.addSeparator()

        # Apply to selected button
        self._apply_style_btn = QPushButton(tr("Apply to Selected"))
        self._apply_style_btn.setEnabled(False)
        self._apply_style_btn.clicked.connect(self._apply_style_to_selected)
        toolbar.addWidget(self._apply_style_btn)

        toolbar.addSeparator()

        # Presets button
        presets_btn = QPushButton(tr("Presets"))
        presets_btn.clicked.connect(self._show_presets)
        toolbar.addWidget(presets_btn)

        toolbar.addSeparator()

        # Page navigation
        toolbar.addWidget(QLabel(tr(" Page: ")))
        self._page_spin = QSpinBox()
        self._page_spin.setRange(1, 1)
        self._page_spin.setValue(1)
        self._page_spin.setFixedWidth(60)
        self._page_spin.valueChanged.connect(self._on_page_spin_changed)
        toolbar.addWidget(self._page_spin)

        self._page_total_label = QLabel(" / 0 ")
        toolbar.addWidget(self._page_total_label)

        # Zoom indicator
        self._zoom_label = QLabel(f" {tr('Zoom:')} 100% ")
        toolbar.addWidget(self._zoom_label)

    def _create_central_widget(self):
        """Create the central widget with splitter."""
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # PDF viewer
        self._viewer = PDFViewer()
        splitter.addWidget(self._viewer)

        # Annotation list panel
        self._annotation_panel = AnnotationListPanel()
        splitter.addWidget(self._annotation_panel)

        # Set sizes
        splitter.setSizes([700, 200])

        self.setCentralWidget(splitter)

    def _create_statusbar(self):
        """Create status bar."""
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._statusbar.showMessage(tr("Ready"))

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
        self._viewer.edit_annotation_requested.connect(self._change_annotation_number)

        # Annotation list panel signals
        self._annotation_panel.jump_to_annotation.connect(self._jump_to_annotation)
        self._annotation_panel.annotation_selected.connect(self._on_list_annotation_selected)
        self._annotation_panel.change_number_requested.connect(self._change_annotation_number)
        self._annotation_panel.delete_requested.connect(self._delete_annotation_with_options)

        # Undo manager signals
        self._undo_manager.state_changed.connect(self._update_undo_actions)

    def _load_settings(self):
        """Load application settings."""
        # Language (load first so UI is in correct language)
        language = self._settings.value("language", "pl")
        Translator.set_language(language)

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
        self._settings.setValue("language", Translator.get_language())

    def _set_language(self, lang: str):
        """Set UI language and prompt for restart."""
        Translator.set_language(lang)
        self._settings.setValue("language", lang)
        QMessageBox.information(
            self,
            "Language Changed" if lang == "en" else "Zmieniono język",
            "Please restart the application for the language change to take effect."
            if lang == "en" else
            "Uruchom ponownie aplikację, aby zmiana języka została zastosowana."
        )

    def _save_style_as_default(self):
        """Save current style settings as default."""
        self._settings.setValue("current_style", json.dumps(self._style.to_dict()))
        self._statusbar.showMessage(tr("Current style saved as default"))

    def _reset_style_to_defaults(self):
        """Reset style to factory defaults."""
        self._style = NumberStyle()

        # Block signals to prevent partial updates
        self._font_combo.blockSignals(True)
        self._size_spin.blockSignals(True)
        self._opacity_spin.blockSignals(True)
        self._border_check.blockSignals(True)
        self._border_width_spin.blockSignals(True)
        self._tail_check.blockSignals(True)
        self._tail_length_spin.blockSignals(True)
        self._tail_width_spin.blockSignals(True)

        # Apply all settings
        self._font_combo.setCurrentText(self._style.font_family)
        self._size_spin.setValue(self._style.font_size)
        self._text_color_btn.setStyleSheet(f"background-color: {self._style.text_color};")
        self._bg_color_btn.setStyleSheet(f"background-color: {self._style.bg_color};")
        self._opacity_spin.setValue(self._style.bg_opacity)
        self._border_check.setChecked(self._style.border_enabled)
        self._border_width_spin.setValue(self._style.border_width)
        self._tail_check.setChecked(self._style.tail_enabled)
        self._tail_length_spin.setValue(self._style.tail_length)
        self._tail_width_spin.setValue(self._style.tail_width)

        # Unblock signals
        self._font_combo.blockSignals(False)
        self._size_spin.blockSignals(False)
        self._opacity_spin.blockSignals(False)
        self._border_check.blockSignals(False)
        self._border_width_spin.blockSignals(False)
        self._tail_check.blockSignals(False)
        self._tail_length_spin.blockSignals(False)
        self._tail_width_spin.blockSignals(False)

        self._viewer.set_style(self._style)
        self._statusbar.showMessage(tr("Style reset to defaults"))

    def _apply_settings(self):
        """Apply loaded settings to UI."""
        self._font_combo.setCurrentText(self._style.font_family)
        self._size_spin.setValue(self._style.font_size)
        self._text_color_btn.setStyleSheet(f"background-color: {self._style.text_color};")
        self._bg_color_btn.setStyleSheet(f"background-color: {self._style.bg_color};")
        self._opacity_spin.setValue(self._style.bg_opacity)
        self._border_check.setChecked(self._style.border_enabled)
        self._border_width_spin.setValue(self._style.border_width)
        self._tail_check.setChecked(self._style.tail_enabled)
        self._tail_length_spin.setValue(self._style.tail_length)
        self._tail_width_spin.setValue(self._style.tail_width)

    def _update_recent_menu(self):
        """Update the recent files menu."""
        self.recent_menu.clear()
        for path in self._recent_files:
            action = self.recent_menu.addAction(os.path.basename(path))
            action.setData(path)
            action.triggered.connect(lambda checked, p=path: self._open_recent(p))

        if self._recent_files:
            self.recent_menu.addSeparator()
            clear_action = self.recent_menu.addAction(tr("Clear Recent"))
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
            QMessageBox.warning(self, tr("File Not Found"), f"{tr('File not found:')}\n{path}")
            self._recent_files.remove(path)
            self._update_recent_menu()

    def _open_file(self):
        """Open a PDF file."""
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Open PDF"), "",
            tr("PDF Files (*.pdf);;All Files (*.*)")
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

            # Update annotation panel
            self._refresh_annotation_panel()

            # Update thumbnail indicators (in case annotations were loaded from metadata)
            
            # Update page navigation
            self._on_page_changed(0)

            # Show message about loaded annotations
            num_annotations = len(self._viewer.get_annotations().all())
            if num_annotations > 0:
                self._statusbar.showMessage(f"{tr('Opened:')} {os.path.basename(path)} ({num_annotations} {tr('annotations')})")
            else:
                self._statusbar.showMessage(f"{tr('Opened:')} {os.path.basename(path)}")
        else:
            QMessageBox.warning(self, tr("Error"), f"{tr('Could not open file:')}\n{path}")

    def _check_unsaved(self) -> bool:
        """Check for unsaved changes. Returns True if should cancel."""
        if self._viewer.get_annotations().modified:
            msg = QMessageBox(self)
            msg.setWindowTitle(tr("Unsaved Changes"))
            msg.setText(tr("There are unsaved changes. Do you want to save?"))
            msg.setIcon(QMessageBox.Icon.Question)

            save_btn = msg.addButton(tr("Save"), QMessageBox.ButtonRole.AcceptRole)
            discard_btn = msg.addButton(tr("Discard"), QMessageBox.ButtonRole.DestructiveRole)
            cancel_btn = msg.addButton(tr("Cancel"), QMessageBox.ButtonRole.RejectRole)

            msg.exec()

            if msg.clickedButton() == save_btn:
                self._save_file()
                return False
            elif msg.clickedButton() == cancel_btn:
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
            self, tr("Save PDF As"), "",
            tr("PDF Files (*.pdf)")
        )
        if path:
            self._do_save_file(path)

    def _do_save_file(self, path: str):
        """Actually save the PDF file."""
        doc = self._viewer.get_document()
        if not doc:
            return

        try:
            # Save our annotation metadata to PDF before saving
            self._viewer.save_metadata_to_pdf()

            # Annotations are already in the PDF (direct editing mode)
            # Just save the document
            doc.save(path, garbage=4, deflate=True)

            # Reload the document to get fresh xrefs after garbage collection
            # This ensures annotations can be found and moved properly
            current_page = self._viewer.current_page()
            self._viewer.reload_document(path)
            self._viewer.go_to_page(current_page)

            self._current_file = path
            self._viewer.get_annotations().modified = False
            self._update_title()
            self._statusbar.showMessage(f"{tr('Saved:')} {os.path.basename(path)}")

        except Exception as e:
            QMessageBox.critical(self, tr("Save Error"), str(e))

    def _enable_file_actions(self, enabled: bool):
        """Enable/disable file-related actions."""
        self.action_save.setEnabled(enabled)
        self.action_save_as.setEnabled(enabled)

    def _update_title(self):
        """Update window title."""
        title = "NapisyTWON"
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

    def _on_page_spin_changed(self, value: int):
        """Handle page spinbox value change."""
        self._viewer.go_to_page(value - 1)

    def _on_zoom_changed(self, zoom: float):
        """Handle zoom change."""
        self._zoom_label.setText(f" {tr('Zoom:')} {int(zoom * 100)}% ")

    def _on_annotation_selected(self, annotation):
        """Handle annotation selection."""
        self.action_delete.setEnabled(annotation is not None)
        self._apply_style_btn.setEnabled(annotation is not None)
        if annotation:
            self._statusbar.showMessage(f"{tr('Selected:')} #{annotation.number}")
            # Load annotation's style into the controls
            self._load_style_to_controls(annotation.style)
        else:
            self._statusbar.showMessage(tr("Ready"))

    def _load_style_to_controls(self, style: NumberStyle):
        """Load a style's settings into the toolbar controls."""
        # Block signals to avoid triggering changes
        self._font_combo.blockSignals(True)
        self._size_spin.blockSignals(True)
        self._opacity_spin.blockSignals(True)
        self._border_check.blockSignals(True)
        self._border_width_spin.blockSignals(True)
        self._tail_check.blockSignals(True)
        self._tail_length_spin.blockSignals(True)
        self._tail_width_spin.blockSignals(True)

        self._font_combo.setCurrentText(style.font_family)
        self._size_spin.setValue(style.font_size)
        self._text_color_btn.setStyleSheet(f"background-color: {style.text_color};")
        self._bg_color_btn.setStyleSheet(f"background-color: {style.bg_color};")
        self._opacity_spin.setValue(style.bg_opacity)
        self._border_check.setChecked(style.border_enabled)
        self._border_width_spin.setValue(style.border_width)
        self._tail_check.setChecked(style.tail_enabled)
        self._tail_length_spin.setValue(style.tail_length)
        self._tail_width_spin.setValue(style.tail_width)

        # Update internal style
        self._style = NumberStyle(
            name=style.name,
            font_family=style.font_family,
            font_size=style.font_size,
            text_color=style.text_color,
            bg_color=style.bg_color,
            bg_opacity=style.bg_opacity,
            padding=style.padding,
            border_enabled=style.border_enabled,
            border_width=style.border_width,
            tail_enabled=style.tail_enabled,
            tail_length=style.tail_length,
            tail_width=style.tail_width
        )

        self._font_combo.blockSignals(False)
        self._size_spin.blockSignals(False)
        self._opacity_spin.blockSignals(False)
        self._border_check.blockSignals(False)
        self._border_width_spin.blockSignals(False)
        self._tail_check.blockSignals(False)
        self._tail_length_spin.blockSignals(False)
        self._tail_width_spin.blockSignals(False)

    def _on_annotation_added(self, annotation: NumberAnnotation):
        """Handle new annotation added."""
        # Check if this was an "empty" annotation (ends with 'p')
        num = annotation.number
        if num.endswith('p'):
            base_num = num[:-1]
            # Reset empty mode after inserting
            self._empty_mode = False
            self._empty_check.blockSignals(True)
            self._empty_check.setChecked(False)
            self._empty_check.blockSignals(False)
        else:
            base_num = num

        # Update next number field (strip 'p' for calculation)
        try:
            main, sub = parse_number(base_num)
            if sub == 0:
                self._number_edit.setText(str(main + 1))
            else:
                self._number_edit.setText(f"{main}.{sub + 1}")
        except (ValueError, IndexError):
            # If parsing fails, just increment based on the raw number
            pass

        self._update_title()
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

        self._statusbar.showMessage(f"{tr('Added:')} #{annotation.number}")

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
        self._refresh_annotation_panel()

        action = UndoAction(
            description=f"Delete #{annotation.number}",
            undo_data=annotation,
            redo_data=annotation,
            undo_func=lambda a: self._undo_delete_annotation(a),
            redo_func=lambda a: self._redo_delete_annotation(a)
        )
        self._undo_manager.push(action)

        self._statusbar.showMessage(f"{tr('Deleted:')} #{annotation.number}")

    def _undo_delete_annotation(self, annotation: NumberAnnotation):
        """Undo deleting an annotation."""
        self._viewer.add_annotation(annotation)
        self._refresh_annotation_panel()

    def _redo_delete_annotation(self, annotation: NumberAnnotation):
        """Redo deleting an annotation."""
        self._viewer.delete_annotation(annotation)
        self._refresh_annotation_panel()

    def _on_number_edited(self):
        """Handle next number changed."""
        text = self._number_edit.text().strip()
        if text:
            # Validate the number format (strip 'p' suffix for validation)
            base_text = text.rstrip('p')
            try:
                parse_number(base_text)
                # Update preview with empty suffix if needed
                display_number = base_text + ('p' if self._empty_mode else '')
                self._viewer.set_next_number(display_number)
            except (ValueError, IndexError):
                # Invalid format, reset to current
                pass

    def _on_empty_mode_changed(self, state):
        """Handle empty mode checkbox changed."""
        self._empty_mode = bool(state)
        self._update_preview_number()
        mode_str = tr("Empty mode ON") if self._empty_mode else tr("Empty mode OFF")
        self._statusbar.showMessage(mode_str)

    def _update_preview_number(self):
        """Update the preview number with or without 'p' suffix."""
        text = self._number_edit.text().strip().rstrip('p')
        if text:
            display_number = text + ('p' if self._empty_mode else '')
            self._viewer.set_next_number(display_number)

    def _toggle_empty_mode(self):
        """Toggle empty mode state."""
        self._empty_mode = not self._empty_mode
        self._empty_check.blockSignals(True)
        self._empty_check.setChecked(self._empty_mode)
        self._empty_check.blockSignals(False)
        self._update_preview_number()
        mode_str = tr("Empty mode ON") if self._empty_mode else tr("Empty mode OFF")
        self._statusbar.showMessage(mode_str)

    def _toggle_annotation_empty(self, annotation: NumberAnnotation):
        """Toggle 'p' suffix on an annotation."""
        old_num = annotation.number
        if old_num.endswith('p'):
            new_num = old_num[:-1]
            status = f"{tr('Toggled empty off')} #{new_num}"
        else:
            new_num = old_num + 'p'
            status = f"{tr('Toggled empty on')} #{new_num}"

        annotation.number = new_num

        # Update PDF annotation
        self._viewer._delete_pdf_annotation(annotation)
        self._viewer._add_pdf_annotation(annotation)
        self._viewer.get_annotations().modified = True

        self._viewer.refresh_page()
        self._viewer.select_annotation(annotation)
        self._refresh_annotation_panel()
        self._update_title()

        # Add undo action
        action = UndoAction(
            description=f"Toggle empty #{old_num} to #{new_num}",
            undo_data=(annotation, old_num, new_num),
            redo_data=(annotation, new_num, old_num),
            undo_func=lambda d: self._restore_number(d[0], d[1]),
            redo_func=lambda d: self._restore_number(d[0], d[1])
        )
        self._undo_manager.push(action)

        self._statusbar.showMessage(status)

    def keyPressEvent(self, event):
        """Handle key press events."""
        if event.key() == Qt.Key.Key_P and not event.modifiers():
            # Check if an annotation is selected
            selected = self._viewer._selected_annotation
            if selected:
                # Toggle 'p' suffix on selected annotation
                self._toggle_annotation_empty(selected)
            else:
                # Toggle empty mode for next insertion
                self._toggle_empty_mode()
            event.accept()
            return
        super().keyPressEvent(event)

    def _set_tool_mode(self, mode: ToolMode):
        """Set the current tool mode."""
        self._viewer.set_tool_mode(mode)
        self._insert_tool_btn.setChecked(mode == ToolMode.INSERT)
        self._select_tool_btn.setChecked(mode == ToolMode.SELECT)
        tool_name = tr("Insert") if mode == ToolMode.INSERT else tr("Select")
        self._statusbar.showMessage(f"{tr('Tool:')} {tool_name}")

    def _on_style_changed(self):
        """Handle style settings changed."""
        self._style.font_family = self._font_combo.currentText()
        self._style.font_size = self._size_spin.value()
        self._style.bg_opacity = self._opacity_spin.value()
        self._style.border_enabled = self._border_check.isChecked()
        self._style.border_width = self._border_width_spin.value()
        self._style.tail_enabled = self._tail_check.isChecked()
        self._style.tail_length = self._tail_length_spin.value()
        self._style.tail_width = self._tail_width_spin.value()
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

    def _apply_style_to_selected(self):
        """Apply current style to the selected annotation."""
        # Get selected annotation from viewer
        annotation = self._viewer._selected_annotation
        if not annotation:
            return

        # Apply current style settings
        annotation.style.font_family = self._style.font_family
        annotation.style.font_size = self._style.font_size
        annotation.style.text_color = self._style.text_color
        annotation.style.bg_color = self._style.bg_color
        annotation.style.bg_opacity = self._style.bg_opacity
        annotation.style.border_enabled = self._style.border_enabled
        annotation.style.border_width = self._style.border_width
        annotation.style.tail_enabled = self._style.tail_enabled
        annotation.style.tail_length = self._style.tail_length
        annotation.style.tail_width = self._style.tail_width

        # Update PDF annotation (delete old, create new with new style)
        self._viewer._delete_pdf_annotation(annotation)
        self._viewer._add_pdf_annotation(annotation)
        self._viewer.get_annotations().modified = True

        # Refresh display
        self._viewer.refresh_page()
        self._viewer.select_annotation(annotation)  # Re-select after refresh
        self._update_title()
        self._statusbar.showMessage(f"{tr('Applied style to')} #{annotation.number}")

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
            self._statusbar.showMessage(f"{tr('Undo:')} {desc}")
            self._update_title()

    def _redo(self):
        """Redo last undone action."""
        desc = self._undo_manager.redo()
        if desc:
            self._statusbar.showMessage(f"{tr('Redo:')} {desc}")
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
            self, tr("Clear All"),
            tr("Delete all annotations?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if result == QMessageBox.StandardButton.Yes:
            annotations = self._viewer.get_annotations()
            annotations.clear()
            self._viewer.set_annotations(annotations)
            self._undo_manager.clear()
            self._refresh_annotation_panel()
            self._update_title()
            self._statusbar.showMessage(tr("Cleared all annotations"))

    def _refresh_annotation_panel(self):
        """Refresh the annotation list panel."""
        self._annotation_panel.set_annotations(self._viewer.get_annotations())

    def _on_duplicate_number_requested(self, number: str, pdf_x: float, pdf_y: float):
        """Handle when user tries to insert a duplicate number."""
        annotations = self._viewer.get_annotations()

        # Show dialog with options
        msg = QMessageBox(self)
        msg.setWindowTitle(tr("Number Already Exists"))
        msg.setText(f"{tr('Number')} {number} {tr('already exists.')}")
        msg.setInformativeText(tr("What would you like to do?"))

        advance_btn = msg.addButton(tr("Auto-advance others"), QMessageBox.ButtonRole.ActionRole)
        sub_btn = msg.addButton(tr("Use sub-number"), QMessageBox.ButtonRole.ActionRole)
        cancel_btn = msg.addButton(QMessageBox.StandardButton.Cancel)

        msg.exec()

        if msg.clickedButton() == advance_btn:
            # Auto-advance all numbers >= number
            changes = annotations.advance_numbers_from(number, 1)

            # Update PDF annotations for all changed numbers
            for changed_ann, _, _ in changes:
                self._viewer._delete_pdf_annotation(changed_ann)
                self._viewer._add_pdf_annotation(changed_ann)

            # Now insert the annotation with the original number
            self._viewer.insert_annotation_at(pdf_x, pdf_y, number)
            self._viewer.refresh_page()
            self._refresh_annotation_panel()
            self._statusbar.showMessage(f"{tr('Inserted')} #{number}, {tr('advanced')} {len(changes)} {tr('others')}")

        elif msg.clickedButton() == sub_btn:
            # Use next available sub-number
            main, _ = parse_number(number)
            sub_num = annotations.get_next_sub_number(str(main))
            self._viewer.insert_annotation_at(pdf_x, pdf_y, sub_num)
            self._statusbar.showMessage(f"{tr('Inserted')} #{sub_num}")

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
            self, tr("Change Number"),
            f"{tr('Enter new number for')} #{current_num}:",
            text=current_num
        )

        if not ok or not new_num.strip():
            return

        new_num = new_num.strip()

        # Validate the number format
        try:
            parse_number(new_num)
        except (ValueError, IndexError):
            QMessageBox.warning(self, tr("Invalid Number"),
                                tr("Please enter a valid number (e.g., 67 or 67.1)"))
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
        msg.setWindowTitle(tr("Number Already Exists"))
        msg.setText(f"{tr('Number')} {new_num} {tr('already exists.')}")
        msg.setInformativeText(tr("What would you like to do?"))

        advance_btn = msg.addButton(tr("Auto-advance others"), QMessageBox.ButtonRole.ActionRole)
        sub_btn = msg.addButton(tr("Use sub-number"), QMessageBox.ButtonRole.ActionRole)
        cancel_btn = msg.addButton(QMessageBox.StandardButton.Cancel)

        msg.exec()

        if msg.clickedButton() == advance_btn:
            # Auto-advance all numbers >= new_num
            old_num = annotation.number
            changes = annotations.advance_numbers_from(new_num, 1)

            # Update PDF annotations for all changed numbers
            for changed_ann, _, _ in changes:
                self._viewer._delete_pdf_annotation(changed_ann)
                self._viewer._add_pdf_annotation(changed_ann)

            annotation.number = new_num
            self._viewer._delete_pdf_annotation(annotation)
            self._viewer._add_pdf_annotation(annotation)

            self._viewer.refresh_page()
            self._refresh_annotation_panel()
            self._update_title()
            self._statusbar.showMessage(f"{tr('Changed')} #{old_num} {tr('to')} #{new_num}, {tr('advanced')} {len(changes)} {tr('others')}")

        elif msg.clickedButton() == sub_btn:
            # Use next available sub-number
            main, _ = parse_number(new_num)
            sub_num = annotations.get_next_sub_number(str(main))
            self._do_change_number(annotation, sub_num)

    def _do_change_number(self, annotation: NumberAnnotation, new_num: str):
        """Actually change an annotation's number."""
        old_num = annotation.number
        annotation.number = new_num

        # Update PDF annotation (delete old, create new with new number)
        self._viewer._delete_pdf_annotation(annotation)
        self._viewer._add_pdf_annotation(annotation)
        self._viewer.get_annotations().modified = True

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

        self._statusbar.showMessage(f"{tr('Changed:')} #{old_num} {tr('to')} #{new_num}")

    def _restore_number(self, annotation: NumberAnnotation, number: str):
        """Restore an annotation's number (for undo/redo)."""
        annotation.number = number

        # Update PDF annotation
        self._viewer._delete_pdf_annotation(annotation)
        self._viewer._add_pdf_annotation(annotation)

        self._viewer.refresh_page()
        self._refresh_annotation_panel()

    def _delete_annotation_with_options(self, annotation: NumberAnnotation):
        """Delete an annotation with option to auto-decrease following numbers."""
        annotations = self._viewer.get_annotations()
        main, sub = parse_number(annotation.number)

        # Only offer auto-decrease for whole numbers
        if sub == 0:
            msg = QMessageBox(self)
            msg.setWindowTitle(tr("Delete Annotation"))
            msg.setText(f"{tr('Delete annotation')} #{annotation.number}?")
            msg.setInformativeText(tr("Do you want to auto-decrease following numbers?"))

            decrease_btn = msg.addButton(tr("Delete && decrease others"), QMessageBox.ButtonRole.ActionRole)
            delete_btn = msg.addButton(tr("Delete only"), QMessageBox.ButtonRole.ActionRole)
            cancel_btn = msg.addButton(QMessageBox.StandardButton.Cancel)

            msg.exec()

            if msg.clickedButton() == cancel_btn:
                return

            if msg.clickedButton() == decrease_btn:
                # First collect changes, then delete and apply
                changes = annotations.decrease_numbers_from(annotation.number, 1)

                # Update PDF annotations for all changed numbers
                for changed_ann, _, _ in changes:
                    self._viewer._delete_pdf_annotation(changed_ann)
                    self._viewer._add_pdf_annotation(changed_ann)

                self._viewer.delete_annotation(annotation)
                self._viewer.refresh_page()
                self._refresh_annotation_panel()
                self._update_title()
                self._statusbar.showMessage(f"{tr('Deleted')} #{annotation.number}, {tr('decreased')} {len(changes)} {tr('others')}")
                return

            # Fall through to regular delete
            if msg.clickedButton() == delete_btn:
                self._viewer.delete_annotation(annotation)
        else:
            # Sub-numbers: just confirm deletion
            result = QMessageBox.question(
                self, tr("Delete Annotation"),
                f"{tr('Delete annotation')} #{annotation.number}?",
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
