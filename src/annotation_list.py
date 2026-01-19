"""Annotation list panel for navigation and management."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QMenu, QInputDialog, QMessageBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush
from typing import Optional

from .models import NumberAnnotation, AnnotationStore


class AnnotationListItem(QListWidgetItem):
    """List item representing an annotation."""

    def __init__(self, annotation: NumberAnnotation):
        super().__init__()
        self.annotation = annotation
        self.update_display()

    def update_display(self):
        self.setText(f"#{self.annotation.number} - Page {self.annotation.page + 1}")


class AnnotationListPanel(QWidget):
    """Panel showing list of all annotations."""

    # Signals
    annotation_selected = Signal(object)  # NumberAnnotation
    jump_to_annotation = Signal(object)  # NumberAnnotation
    change_number_requested = Signal(object)  # NumberAnnotation
    delete_requested = Signal(object)  # NumberAnnotation

    def __init__(self, parent=None):
        super().__init__(parent)
        self._annotations: Optional[AnnotationStore] = None
        self._items: dict[str, AnnotationListItem] = {}

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header
        header = QLabel("Annotations")
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)

        # List
        self._list = QListWidget()
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_context_menu)
        self._list.itemDoubleClicked.connect(self._on_double_click)
        self._list.itemClicked.connect(self._on_click)
        layout.addWidget(self._list)

        # Status label
        self._status_label = QLabel("0 items")
        self._status_label.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(self._status_label)

        # Buttons
        btn_layout = QHBoxLayout()

        self._jump_btn = QPushButton("Go to")
        self._jump_btn.setEnabled(False)
        self._jump_btn.clicked.connect(self._on_jump)
        btn_layout.addWidget(self._jump_btn)

        self._edit_btn = QPushButton("Edit #")
        self._edit_btn.setEnabled(False)
        self._edit_btn.clicked.connect(self._on_edit)
        btn_layout.addWidget(self._edit_btn)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._on_delete)
        btn_layout.addWidget(self._delete_btn)

        layout.addLayout(btn_layout)

    def set_annotations(self, annotations: AnnotationStore):
        """Set the annotation store to display."""
        self._annotations = annotations
        self.refresh()

    def refresh(self):
        """Refresh the list from the annotation store."""
        self._list.clear()
        self._items.clear()

        if not self._annotations:
            self._status_label.setText("0 items")
            return

        # Add items sorted by number
        for annotation in self._annotations.all_sorted():
            item = AnnotationListItem(annotation)
            self._list.addItem(item)
            self._items[annotation.id] = item

        # Update status
        count = self._annotations.count()
        valid, msg = self._annotations.validate_sequence()

        if valid:
            self._status_label.setText(f"{count} items")
            self._status_label.setStyleSheet("color: #666; font-size: 10px;")
        else:
            self._status_label.setText(f"{count} items - {msg}")
            self._status_label.setStyleSheet("color: #CC0000; font-size: 10px;")

    def select_annotation(self, annotation_id: str):
        """Select an annotation in the list."""
        if annotation_id in self._items:
            item = self._items[annotation_id]
            self._list.setCurrentItem(item)
            self._list.scrollToItem(item)
            self._update_buttons()

    def deselect(self):
        """Clear selection."""
        self._list.clearSelection()
        self._update_buttons()

    def _update_buttons(self):
        """Update button states based on selection."""
        has_selection = self._list.currentItem() is not None
        self._jump_btn.setEnabled(has_selection)
        self._edit_btn.setEnabled(has_selection)
        self._delete_btn.setEnabled(has_selection)

    def _get_selected_annotation(self) -> Optional[NumberAnnotation]:
        """Get currently selected annotation."""
        item = self._list.currentItem()
        if isinstance(item, AnnotationListItem):
            return item.annotation
        return None

    def _on_click(self, item):
        """Handle single click - select."""
        self._update_buttons()
        if isinstance(item, AnnotationListItem):
            self.annotation_selected.emit(item.annotation)

    def _on_double_click(self, item):
        """Handle double click - jump to annotation."""
        if isinstance(item, AnnotationListItem):
            self.jump_to_annotation.emit(item.annotation)

    def _on_jump(self):
        """Jump to selected annotation."""
        annotation = self._get_selected_annotation()
        if annotation:
            self.jump_to_annotation.emit(annotation)

    def _on_edit(self):
        """Edit selected annotation's number."""
        annotation = self._get_selected_annotation()
        if annotation:
            self.change_number_requested.emit(annotation)

    def _on_delete(self):
        """Delete selected annotation."""
        annotation = self._get_selected_annotation()
        if annotation:
            self.delete_requested.emit(annotation)

    def _show_context_menu(self, pos):
        """Show context menu for annotation."""
        item = self._list.itemAt(pos)
        if not isinstance(item, AnnotationListItem):
            return

        annotation = item.annotation
        menu = QMenu(self)

        jump_action = menu.addAction(f"Go to #{annotation.number}")
        jump_action.triggered.connect(lambda: self.jump_to_annotation.emit(annotation))

        menu.addSeparator()

        edit_action = menu.addAction("Change number...")
        edit_action.triggered.connect(lambda: self.change_number_requested.emit(annotation))

        menu.addSeparator()

        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(lambda: self.delete_requested.emit(annotation))

        menu.exec(self._list.mapToGlobal(pos))
