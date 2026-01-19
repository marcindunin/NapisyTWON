"""PDF viewer widget with zoom, pan, and annotation support."""

import fitz
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsRectItem, QGraphicsTextItem, QApplication
)
from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QColor, QFont, QBrush, QPen,
    QWheelEvent, QMouseEvent, QKeyEvent
)
from typing import Optional, Callable
from .models import NumberAnnotation, NumberStyle, AnnotationStore, parse_number


class AnnotationItem(QGraphicsRectItem):
    """Graphics item for a number annotation."""

    def __init__(self, annotation: NumberAnnotation, scale: float = 1.0):
        super().__init__()
        self.annotation = annotation
        self._scale = scale
        self._selected = False
        self._hovered = False
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_display()

    def update_display(self):
        """Update the visual representation."""
        style = self.annotation.style
        text = str(self.annotation.number)

        # Calculate size based on font
        font = QFont(style.font_family, style.font_size)
        from PySide6.QtGui import QFontMetrics
        metrics = QFontMetrics(font)
        text_rect = metrics.boundingRect(text)

        padding = style.padding
        width = text_rect.width() + padding * 2
        height = text_rect.height() + padding * 2

        # Position in scene coordinates
        x = self.annotation.x * self._scale
        y = self.annotation.y * self._scale
        w = width * self._scale
        h = height * self._scale

        self.setRect(0, 0, w, h)
        self.setPos(x, y)

        # Store original size for PDF export
        self._pdf_width = width
        self._pdf_height = height

    def set_scale(self, scale: float):
        self._scale = scale
        self.update_display()

    def paint(self, painter, option, widget):
        style = self.annotation.style
        rect = self.rect()

        # Background
        bg_color = QColor(style.bg_color)
        bg_color.setAlphaF(style.bg_opacity)
        painter.fillRect(rect, bg_color)

        # Border if selected or hovered
        if self._selected:
            painter.setPen(QPen(QColor("#FF0000"), 2))
            painter.drawRect(rect)
        elif self._hovered:
            painter.setPen(QPen(QColor("#0078D7"), 1))
            painter.drawRect(rect)

        # Text
        font = QFont(style.font_family, int(style.font_size * self._scale))
        painter.setFont(font)
        painter.setPen(QColor(style.text_color))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(self.annotation.number))

    def set_selected(self, selected: bool):
        self._selected = selected
        self.update()

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()


class NumberPreviewItem(QGraphicsRectItem):
    """Preview item shown at cursor when inserting numbers."""

    def __init__(self, style: NumberStyle, number: str, scale: float = 1.0):
        super().__init__()
        self.style = style
        self.number = str(number)
        self._scale = scale
        self.setOpacity(0.7)
        self.update_display()

    def update_display(self):
        text = str(self.number)
        font = QFont(self.style.font_family, self.style.font_size)
        from PySide6.QtGui import QFontMetrics
        metrics = QFontMetrics(font)
        text_rect = metrics.boundingRect(text)

        padding = self.style.padding
        width = (text_rect.width() + padding * 2) * self._scale
        height = (text_rect.height() + padding * 2) * self._scale

        self.setRect(-width / 2, -height / 2, width, height)

    def set_style(self, style: NumberStyle, number: str):
        self.style = style
        self.number = str(number)
        self.update_display()
        self.update()

    def set_scale(self, scale: float):
        self._scale = scale
        self.update_display()

    def paint(self, painter, option, widget):
        rect = self.rect()

        # Background
        bg_color = QColor(self.style.bg_color)
        bg_color.setAlphaF(self.style.bg_opacity * 0.7)
        painter.fillRect(rect, bg_color)

        # Text
        font = QFont(self.style.font_family, int(self.style.font_size * self._scale))
        painter.setFont(font)
        text_color = QColor(self.style.text_color)
        text_color.setAlphaF(0.7)
        painter.setPen(text_color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(self.number))


class PDFViewer(QGraphicsView):
    """PDF viewer with zoom, pan, and annotation support."""

    # Signals
    page_changed = Signal(int)  # current page index
    zoom_changed = Signal(float)  # zoom factor
    annotation_selected = Signal(object)  # NumberAnnotation or None
    annotation_added = Signal(object)  # NumberAnnotation
    annotation_moved = Signal(object, float, float)  # annotation, old_x, old_y
    annotation_deleted = Signal(object)  # NumberAnnotation
    duplicate_number_requested = Signal(str, float, float)  # number, pdf_x, pdf_y

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        # PDF state
        self._doc: Optional[fitz.Document] = None
        self._current_page = 0
        self._page_pixmap: Optional[QGraphicsPixmapItem] = None

        # View state
        self._zoom = 1.0
        self._min_zoom = 0.1
        self._max_zoom = 5.0
        self._fit_mode = True  # Fit to view on resize

        # Interaction state
        self._panning = False
        self._pan_start = QPointF()
        self._dragging_annotation: Optional[AnnotationItem] = None
        self._drag_start_pos = QPointF()
        self._drag_annotation_start = QPointF()

        # Annotations
        self._annotations = AnnotationStore()
        self._annotation_items: dict[str, AnnotationItem] = {}
        self._selected_annotation: Optional[AnnotationItem] = None

        # Preview
        self._preview_item: Optional[NumberPreviewItem] = None
        self._current_style = NumberStyle()
        self._next_number = "1"
        self._insert_mode = True

        # Setup
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setBackgroundBrush(QBrush(QColor("#404040")))
        self.setMouseTracking(True)

    def open_document(self, path: str) -> bool:
        """Open a PDF document."""
        try:
            self._doc = fitz.open(path)
            self._current_page = 0
            self._annotations.clear()
            self._annotation_items.clear()
            self._selected_annotation = None
            self._render_page()
            return True
        except Exception as e:
            print(f"Error opening PDF: {e}")
            return False

    def get_document(self) -> Optional[fitz.Document]:
        return self._doc

    def close_document(self):
        """Close the current document."""
        if self._doc:
            self._doc.close()
            self._doc = None
        self._scene.clear()
        self._page_pixmap = None
        self._preview_item = None  # Reset since scene.clear() deleted it
        self._annotation_items.clear()
        self._annotations.clear()
        self._selected_annotation = None

    def page_count(self) -> int:
        return self._doc.page_count if self._doc else 0

    def current_page(self) -> int:
        return self._current_page

    def go_to_page(self, page: int):
        """Navigate to a specific page."""
        if not self._doc:
            return
        if 0 <= page < self._doc.page_count:
            self._current_page = page
            self._render_page()
            self.page_changed.emit(page)

    def next_page(self):
        if self._current_page < self.page_count() - 1:
            self.go_to_page(self._current_page + 1)

    def prev_page(self):
        if self._current_page > 0:
            self.go_to_page(self._current_page - 1)

    def _render_page(self):
        """Render the current page."""
        if not self._doc:
            return

        page = self._doc.load_page(self._current_page)

        # Calculate zoom to fit if needed
        if self._fit_mode:
            view_rect = self.viewport().rect()
            page_rect = page.rect
            zoom_x = view_rect.width() / page_rect.width
            zoom_y = view_rect.height() / page_rect.height
            self._zoom = min(zoom_x, zoom_y) * 0.95  # 95% to leave margin

        # Render page
        mat = fitz.Matrix(self._zoom, self._zoom)
        pix = page.get_pixmap(matrix=mat)

        # Convert to QImage
        if pix.alpha:
            fmt = QImage.Format.Format_RGBA8888
        else:
            fmt = QImage.Format.Format_RGB888

        img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
        pixmap = QPixmap.fromImage(img)

        # Update scene (clear also deletes preview item)
        self._scene.clear()
        self._preview_item = None  # Reset reference since scene.clear() deleted it
        self._page_pixmap = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(0, 0, pixmap.width(), pixmap.height())

        # Re-add annotations
        self._annotation_items.clear()
        for annotation in self._annotations.get_for_page(self._current_page):
            self._add_annotation_item(annotation)

        # Re-create preview if in insert mode
        if self._insert_mode:
            self._create_preview()

        self.zoom_changed.emit(self._zoom)

    def _add_annotation_item(self, annotation: NumberAnnotation):
        """Add an annotation item to the scene."""
        item = AnnotationItem(annotation, self._zoom)
        self._scene.addItem(item)
        self._annotation_items[annotation.id] = item

    def _create_preview(self):
        """Create or update the preview item."""
        if self._preview_item:
            self._scene.removeItem(self._preview_item)
        self._preview_item = NumberPreviewItem(self._current_style, self._next_number, self._zoom)
        self._preview_item.setVisible(False)
        self._scene.addItem(self._preview_item)

    def set_style(self, style: NumberStyle):
        """Set the current style for new annotations."""
        self._current_style = style
        if self._preview_item:
            self._preview_item.set_style(style, self._next_number)

    def set_next_number(self, number: str):
        """Set the next number to insert."""
        self._next_number = str(number)
        if self._preview_item:
            self._preview_item.set_style(self._current_style, self._next_number)

    def get_annotations(self) -> AnnotationStore:
        return self._annotations

    def set_annotations(self, annotations: AnnotationStore):
        """Replace all annotations."""
        self._annotations = annotations
        self._render_page()

    def zoom_in(self):
        self.set_zoom(self._zoom * 1.25)

    def zoom_out(self):
        self.set_zoom(self._zoom / 1.25)

    def zoom_fit(self):
        self._fit_mode = True
        self._render_page()

    def zoom_100(self):
        self.set_zoom(1.0)

    def set_zoom(self, zoom: float):
        """Set zoom level."""
        self._zoom = max(self._min_zoom, min(self._max_zoom, zoom))
        self._fit_mode = False
        self._render_page()

    def get_zoom(self) -> float:
        return self._zoom

    def set_insert_mode(self, enabled: bool):
        """Enable/disable insert mode."""
        self._insert_mode = enabled
        if self._preview_item:
            self._preview_item.setVisible(False)
        if not enabled:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def wheelEvent(self, event: QWheelEvent):
        """Handle mouse wheel for zooming."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Zoom
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
        else:
            # Scroll
            super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton:
            # Start panning
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            item = self._scene.itemAt(scene_pos, self.transform())

            # Check if clicked on annotation
            if isinstance(item, AnnotationItem):
                # Start dragging or select
                self._select_annotation(item)
                self._dragging_annotation = item
                self._drag_start_pos = scene_pos
                self._drag_annotation_start = QPointF(
                    item.annotation.x,
                    item.annotation.y
                )
                event.accept()
                return

            # Clicked on empty space
            if self._selected_annotation:
                self._deselect_annotation()

            # Insert new annotation if in insert mode
            if self._insert_mode and self._page_pixmap:
                # Check if click is on the page
                page_rect = self._page_pixmap.boundingRect()
                if page_rect.contains(scene_pos):
                    self._insert_annotation(scene_pos)
                    event.accept()
                    return

        if event.button() == Qt.MouseButton.RightButton:
            # Deselect
            if self._selected_annotation:
                self._deselect_annotation()
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x())
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y())
            )
            event.accept()
            return

        if self._dragging_annotation:
            # Move annotation
            scene_pos = self.mapToScene(event.position().toPoint())
            delta = scene_pos - self._drag_start_pos

            # Convert delta to PDF coordinates
            pdf_delta_x = delta.x() / self._zoom
            pdf_delta_y = delta.y() / self._zoom

            new_x = self._drag_annotation_start.x() + pdf_delta_x
            new_y = self._drag_annotation_start.y() + pdf_delta_y

            # Update annotation position
            self._dragging_annotation.annotation.x = new_x
            self._dragging_annotation.annotation.y = new_y
            self._dragging_annotation.update_display()
            event.accept()
            return

        # Update preview position
        if self._insert_mode and self._preview_item is not None:
            try:
                scene_pos = self.mapToScene(event.position().toPoint())
                if self._page_pixmap and self._page_pixmap.boundingRect().contains(scene_pos):
                    self._preview_item.setPos(scene_pos)
                    self._preview_item.setVisible(True)
                    self.setCursor(Qt.CursorShape.CrossCursor)
                else:
                    self._preview_item.setVisible(False)
                    self.setCursor(Qt.CursorShape.ArrowCursor)
            except RuntimeError:
                # Item was deleted, reset reference
                self._preview_item = None

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton and self._dragging_annotation:
            # Emit move signal for undo
            old_x = self._drag_annotation_start.x()
            old_y = self._drag_annotation_start.y()
            ann = self._dragging_annotation.annotation

            if old_x != ann.x or old_y != ann.y:
                self._annotations.modified = True
                self.annotation_moved.emit(ann, old_x, old_y)

            self._dragging_annotation = None
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Delete:
            if self._selected_annotation:
                self._delete_selected_annotation()
                event.accept()
                return

        if event.key() == Qt.Key.Key_Escape:
            if self._selected_annotation:
                self._deselect_annotation()
                event.accept()
                return

        super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit_mode and self._doc:
            self._render_page()

    def _select_annotation(self, item: AnnotationItem):
        """Select an annotation."""
        if self._selected_annotation:
            self._selected_annotation.set_selected(False)
        self._selected_annotation = item
        item.set_selected(True)
        self.annotation_selected.emit(item.annotation)

    def _deselect_annotation(self):
        """Deselect current annotation."""
        if self._selected_annotation:
            self._selected_annotation.set_selected(False)
            self._selected_annotation = None
            self.annotation_selected.emit(None)

    def _insert_annotation(self, scene_pos: QPointF):
        """Insert a new annotation at the given scene position."""
        # Convert to PDF coordinates
        pdf_x = scene_pos.x() / self._zoom
        pdf_y = scene_pos.y() / self._zoom

        # Center on click
        # Get size from style
        font = QFont(self._current_style.font_family, self._current_style.font_size)
        from PySide6.QtGui import QFontMetrics
        metrics = QFontMetrics(font)
        text_rect = metrics.boundingRect(str(self._next_number))
        width = text_rect.width() + self._current_style.padding * 2
        height = text_rect.height() + self._current_style.padding * 2

        pdf_x -= width / 2
        pdf_y -= height / 2

        # Check for duplicate
        if self._annotations.has_number(self._next_number):
            # Emit signal for main window to handle
            self.duplicate_number_requested.emit(self._next_number, pdf_x, pdf_y)
            return

        self._do_insert_annotation(pdf_x, pdf_y, self._next_number)

    def _do_insert_annotation(self, pdf_x: float, pdf_y: float, number: str):
        """Actually insert an annotation at the given PDF coordinates."""
        # Create annotation
        annotation = NumberAnnotation(
            page=self._current_page,
            x=pdf_x,
            y=pdf_y,
            number=number,
            style=NumberStyle(**{
                'name': self._current_style.name,
                'font_family': self._current_style.font_family,
                'font_size': self._current_style.font_size,
                'text_color': self._current_style.text_color,
                'bg_color': self._current_style.bg_color,
                'bg_opacity': self._current_style.bg_opacity,
                'padding': self._current_style.padding,
            })
        )

        self._annotations.add(annotation)
        self._add_annotation_item(annotation)

        # Auto-increment (only for whole numbers)
        main, sub = parse_number(number)
        if sub == 0:
            self._next_number = str(main + 1)
        else:
            # For sub-numbers, just increment the sub
            self._next_number = f"{main}.{sub + 1}"

        if self._preview_item:
            self._preview_item.set_style(self._current_style, self._next_number)

        self.annotation_added.emit(annotation)

    def insert_annotation_at(self, pdf_x: float, pdf_y: float, number: str):
        """Insert an annotation at the given position with the given number.

        Used by main window when handling duplicate number resolution.
        """
        self._do_insert_annotation(pdf_x, pdf_y, number)

    def _delete_selected_annotation(self):
        """Delete the currently selected annotation."""
        if not self._selected_annotation:
            return

        annotation = self._selected_annotation.annotation

        # Remove from scene and store
        self._scene.removeItem(self._selected_annotation)
        del self._annotation_items[annotation.id]
        self._annotations.remove(annotation.id)

        self._selected_annotation = None
        self.annotation_deleted.emit(annotation)
        self.annotation_selected.emit(None)

    def delete_annotation(self, annotation: NumberAnnotation):
        """Delete a specific annotation."""
        if annotation.id in self._annotation_items:
            item = self._annotation_items[annotation.id]
            self._scene.removeItem(item)
            del self._annotation_items[annotation.id]

            if self._selected_annotation == item:
                self._selected_annotation = None
                self.annotation_selected.emit(None)

        self._annotations.remove(annotation.id)

    def add_annotation(self, annotation: NumberAnnotation):
        """Add an annotation (for undo/redo)."""
        self._annotations.add(annotation)
        if annotation.page == self._current_page:
            self._add_annotation_item(annotation)

    def get_page_image(self, page: int, scale: float = 2.0) -> Optional[QImage]:
        """Get a page as QImage with annotations rendered."""
        if not self._doc or page < 0 or page >= self._doc.page_count:
            return None

        pdf_page = self._doc.load_page(page)
        mat = fitz.Matrix(scale, scale)
        pix = pdf_page.get_pixmap(matrix=mat)

        if pix.alpha:
            fmt = QImage.Format.Format_RGBA8888
        else:
            fmt = QImage.Format.Format_RGB888

        img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()

        # Draw annotations
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for annotation in self._annotations.get_for_page(page):
            style = annotation.style
            text = str(annotation.number)

            # Calculate position and size
            font = QFont(style.font_family, int(style.font_size * scale))
            painter.setFont(font)
            metrics = painter.fontMetrics()
            text_rect = metrics.boundingRect(text)

            padding = int(style.padding * scale)
            x = int(annotation.x * scale)
            y = int(annotation.y * scale)
            w = text_rect.width() + padding * 2
            h = text_rect.height() + padding * 2

            rect = QRectF(x, y, w, h)

            # Background
            bg_color = QColor(style.bg_color)
            bg_color.setAlphaF(style.bg_opacity)
            painter.fillRect(rect, bg_color)

            # Text
            painter.setPen(QColor(style.text_color))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

        painter.end()
        return img

    def refresh_page(self):
        """Refresh the current page display."""
        self._render_page()

    def select_annotation(self, annotation: NumberAnnotation):
        """Select a specific annotation by its data."""
        if annotation.id in self._annotation_items:
            item = self._annotation_items[annotation.id]
            self._select_annotation(item)

    def center_on_annotation(self, annotation: NumberAnnotation):
        """Center the view on an annotation."""
        if annotation.id in self._annotation_items:
            item = self._annotation_items[annotation.id]
            self.centerOn(item)
