"""Thumbnail panel for PDF page navigation."""

import fitz
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QLabel, QFrame,
    QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QPen
from typing import Optional


class ThumbnailWidget(QFrame):
    """Single page thumbnail."""

    clicked = Signal(int)  # page index

    def __init__(self, page_index: int, parent=None):
        super().__init__(parent)
        self.page_index = page_index
        self._selected = False

        self.setFixedSize(120, 160)
        self.setFrameStyle(QFrame.Shape.Box)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet("background-color: white;")
        layout.addWidget(self._image_label, 1)

        self._page_label = QLabel(f"{page_index + 1}")
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page_label.setStyleSheet("font-size: 10px;")
        layout.addWidget(self._page_label)

        self._update_style()

    def set_thumbnail(self, pixmap: QPixmap):
        """Set the thumbnail image."""
        scaled = pixmap.scaled(
            self._image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self._image_label.setPixmap(scaled)

    def set_selected(self, selected: bool):
        """Set selection state."""
        self._selected = selected
        self._update_style()

    def set_has_annotations(self, has_annotations: bool):
        """Show indicator if page has annotations."""
        if has_annotations:
            self._page_label.setText(f"{self.page_index + 1} •")
        else:
            self._page_label.setText(f"{self.page_index + 1}")

    def _update_style(self):
        if self._selected:
            self.setStyleSheet("""
                ThumbnailWidget {
                    border: 2px solid #0078D7;
                    background-color: #E5F1FB;
                }
            """)
        else:
            self.setStyleSheet("""
                ThumbnailWidget {
                    border: 1px solid #CCCCCC;
                    background-color: #F5F5F5;
                }
                ThumbnailWidget:hover {
                    border: 1px solid #0078D7;
                    background-color: #F0F0F0;
                }
            """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.page_index)
        super().mousePressEvent(event)


class ThumbnailPanel(QScrollArea):
    """Panel showing page thumbnails for navigation."""

    page_selected = Signal(int)  # page index

    def __init__(self, parent=None):
        super().__init__(parent)
        self._doc: Optional[fitz.Document] = None
        self._thumbnails: list[ThumbnailWidget] = []
        self._current_page = 0

        # Setup scroll area
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMinimumWidth(140)
        self.setMaximumWidth(160)

        # Container widget
        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self._layout.setSpacing(8)
        self._layout.setContentsMargins(8, 8, 8, 8)

        self.setWidget(self._container)

        # Placeholder
        self._placeholder = QLabel("No document\nloaded")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("color: #888888;")
        self._layout.addWidget(self._placeholder)

    def set_document(self, doc: fitz.Document):
        """Set the PDF document and generate thumbnails."""
        self._doc = doc
        self._clear_thumbnails()

        if not doc:
            self._placeholder.setVisible(True)
            return

        self._placeholder.setVisible(False)

        # Generate thumbnails
        for i in range(doc.page_count):
            thumb = ThumbnailWidget(i)
            thumb.clicked.connect(self._on_thumbnail_clicked)
            self._layout.addWidget(thumb)
            self._thumbnails.append(thumb)

            # Render thumbnail
            self._render_thumbnail(i)

        # Select first page
        if self._thumbnails:
            self._thumbnails[0].set_selected(True)
            self._current_page = 0

    def _clear_thumbnails(self):
        """Remove all thumbnail widgets."""
        for thumb in self._thumbnails:
            self._layout.removeWidget(thumb)
            thumb.deleteLater()
        self._thumbnails.clear()
        self._placeholder.setVisible(True)

    def _render_thumbnail(self, page_index: int):
        """Render a single page thumbnail."""
        if not self._doc or page_index >= len(self._thumbnails):
            return

        page = self._doc.load_page(page_index)

        # Calculate scale for thumbnail
        thumb_width = 100
        scale = thumb_width / page.rect.width

        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat)

        # Convert to QPixmap
        if pix.alpha:
            fmt = QImage.Format.Format_RGBA8888
        else:
            fmt = QImage.Format.Format_RGB888

        img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
        pixmap = QPixmap.fromImage(img)

        self._thumbnails[page_index].set_thumbnail(pixmap)

    def _on_thumbnail_clicked(self, page_index: int):
        """Handle thumbnail click."""
        self.set_current_page(page_index)
        self.page_selected.emit(page_index)

    def set_current_page(self, page_index: int):
        """Set the currently selected page."""
        if page_index < 0 or page_index >= len(self._thumbnails):
            return

        # Deselect previous
        if 0 <= self._current_page < len(self._thumbnails):
            self._thumbnails[self._current_page].set_selected(False)

        # Select new
        self._current_page = page_index
        self._thumbnails[page_index].set_selected(True)

        # Scroll to visible
        self.ensureWidgetVisible(self._thumbnails[page_index])

    def update_annotation_indicators(self, annotations_by_page: dict[int, int]):
        """Update annotation indicators on thumbnails.

        Args:
            annotations_by_page: dict mapping page index to annotation count
        """
        for i, thumb in enumerate(self._thumbnails):
            thumb.set_has_annotations(annotations_by_page.get(i, 0) > 0)

    def refresh_thumbnail(self, page_index: int):
        """Refresh a specific thumbnail."""
        self._render_thumbnail(page_index)

    def clear(self):
        """Clear all thumbnails."""
        self._doc = None
        self._clear_thumbnails()
