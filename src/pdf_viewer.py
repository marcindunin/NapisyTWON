"""PDF viewer widget with zoom, pan, and annotation support.

This version edits the PDF directly - annotations are added to the PDF document
and rendered as part of the page, ensuring consistency with other PDF readers.
"""

import fitz
from enum import Enum
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsRectItem, QApplication
)
from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QColor, QFont, QBrush, QPen,
    QWheelEvent, QMouseEvent, QKeyEvent
)
from typing import Optional
from .models import NumberAnnotation, NumberStyle, AnnotationStore, parse_number


class ToolMode(Enum):
    INSERT = "insert"
    SELECT = "select"


# Metadata key for storing our annotation data in PDF
NAPISY_METADATA_KEY = "NapisyTWON_Annotations"


class SelectionOverlay(QGraphicsRectItem):
    """Overlay to show selection/hover state on annotations."""

    def __init__(self):
        super().__init__()
        self._selected = False
        self._hovered = False
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))

    def set_selected(self, selected: bool):
        self._selected = selected
        self.update()

    def set_hovered(self, hovered: bool):
        self._hovered = hovered
        self.update()

    def paint(self, painter, option, widget):
        if self._selected:
            painter.setPen(QPen(QColor("#FF0000"), 2))
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            painter.drawRect(self.rect())
        elif self._hovered:
            painter.setPen(QPen(QColor("#0078D7"), 1, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            painter.drawRect(self.rect())


class PDFPreviewItem(QGraphicsPixmapItem):
    """Preview item that shows actual PDF-rendered annotation."""

    def __init__(self, style: NumberStyle, number: str, scale: float = 1.0):
        super().__init__()
        self.style = style
        self.number = str(number)
        self._scale = scale
        self._width = 0
        self._height = 0
        self.setOpacity(0.7)
        self._render_preview()

    def _render_preview(self):
        """Render a preview using actual PDF annotation."""
        text = str(self.number)
        style = self.style

        # Calculate dimensions
        font = fitz.Font("helv")
        text_width = font.text_length(text, fontsize=style.font_size)
        text_height = style.font_size
        padding = style.padding

        width = text_width + padding * 2
        height = text_height + padding * 2

        # Create temporary PDF with annotation
        doc = fitz.open()
        page = doc.new_page(width=width + 10, height=height + 10)

        rect = fitz.Rect(5, 5, 5 + width, 5 + height)

        def hex_to_rgb(hex_color):
            hex_color = hex_color.lstrip('#')
            return tuple(int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4))

        fg_rgb = hex_to_rgb(style.text_color)
        bg_rgb = hex_to_rgb(style.bg_color) if style.bg_opacity > 0 else None

        annot = page.add_freetext_annot(
            rect,
            text,
            fontsize=style.font_size,
            fontname="helv",
            text_color=fg_rgb,
            fill_color=bg_rgb,
            align=fitz.TEXT_ALIGN_CENTER,
        )

        if bg_rgb and style.bg_opacity < 1.0:
            annot.set_opacity(style.bg_opacity)

        annot.update()

        if style.border_enabled:
            annot_xref = annot.xref
            doc.xref_set_key(annot_xref, "Border", f"[0 0 {style.border_width}]")
            doc.xref_set_key(annot_xref, "BS", f"<</W {style.border_width}/S/S>>")
            annot.update()

        # Render to pixmap
        mat = fitz.Matrix(self._scale, self._scale)
        pix = page.get_pixmap(matrix=mat, clip=fitz.Rect(0, 0, width + 10, height + 10))

        if pix.alpha:
            fmt = QImage.Format.Format_RGBA8888
        else:
            fmt = QImage.Format.Format_RGB888

        img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
        pixmap = QPixmap.fromImage(img.copy())

        doc.close()

        self.setPixmap(pixmap)
        self._width = pixmap.width()
        self._height = pixmap.height()
        # Center the pixmap on the cursor position
        self.setOffset(-self._width / 2, -self._height / 2)

    def set_style(self, style: NumberStyle, number: str):
        self.style = style
        self.number = str(number)
        self._render_preview()

    def set_scale(self, scale: float):
        self._scale = scale
        self._render_preview()


class PDFViewer(QGraphicsView):
    """PDF viewer with direct PDF annotation editing."""

    # Signals
    page_changed = Signal(int)
    zoom_changed = Signal(float)
    annotation_selected = Signal(object)  # NumberAnnotation or None
    annotation_added = Signal(object)  # NumberAnnotation
    annotation_moved = Signal(object, float, float)  # annotation, old_x, old_y
    annotation_deleted = Signal(object)  # NumberAnnotation
    duplicate_number_requested = Signal(str, float, float)
    edit_annotation_requested = Signal(object)
    tool_changed = Signal(str)

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
        self._fit_mode = True

        # Interaction state
        self._panning = False
        self._pan_start = QPointF()
        self._dragging_annotation: Optional[NumberAnnotation] = None
        self._drag_start_pos = QPointF()
        self._drag_annotation_start = QPointF()

        # Annotations (our tracking, synced with PDF)
        self._annotations = AnnotationStore()
        self._selected_annotation: Optional[NumberAnnotation] = None
        self._selection_overlay: Optional[SelectionOverlay] = None

        # Preview
        self._preview_item: Optional[PDFPreviewItem] = None
        self._current_style = NumberStyle()
        self._next_number = "1"
        self._tool_mode = ToolMode.INSERT

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
            self._selected_annotation = None

            # Try to load our annotation metadata from PDF
            if self.load_metadata_from_pdf():
                print(f"Loaded {len(self._annotations.all())} annotations from PDF metadata")

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
        self._preview_item = None
        self._selection_overlay = None
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
        """Render the current page from PDF (includes annotations)."""
        if not self._doc:
            return

        page = self._doc.load_page(self._current_page)

        # Calculate zoom to fit if needed
        if self._fit_mode:
            view_rect = self.viewport().rect()
            page_rect = page.rect
            zoom_x = view_rect.width() / page_rect.width
            zoom_y = view_rect.height() / page_rect.height
            self._zoom = min(zoom_x, zoom_y) * 0.95

        # Render page WITH annotations
        mat = fitz.Matrix(self._zoom, self._zoom)
        pix = page.get_pixmap(matrix=mat)

        # Convert to QImage
        if pix.alpha:
            fmt = QImage.Format.Format_RGBA8888
        else:
            fmt = QImage.Format.Format_RGB888

        img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
        pixmap = QPixmap.fromImage(img)

        # Update scene
        self._scene.clear()
        self._preview_item = None
        self._selection_overlay = None
        self._page_pixmap = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(0, 0, pixmap.width(), pixmap.height())

        # Create selection overlay
        self._selection_overlay = SelectionOverlay()
        self._selection_overlay.setVisible(False)
        self._scene.addItem(self._selection_overlay)

        # Update selection overlay if we have a selected annotation
        if self._selected_annotation:
            self._update_selection_overlay(self._selected_annotation)

        # Re-create preview if in insert mode
        if self._tool_mode == ToolMode.INSERT:
            self._create_preview()

        self.zoom_changed.emit(self._zoom)

    def _update_selection_overlay(self, annotation: NumberAnnotation):
        """Update the selection overlay to match an annotation's position."""
        if not self._selection_overlay:
            return

        # Calculate rect from annotation
        style = annotation.style
        text = str(annotation.number)

        font = fitz.Font("helv")
        text_width = font.text_length(text, fontsize=style.font_size)
        text_height = style.font_size
        padding = style.padding

        x = annotation.x * self._zoom
        y = annotation.y * self._zoom
        w = (text_width + padding * 2) * self._zoom
        h = (text_height + padding * 2) * self._zoom

        self._selection_overlay.setRect(0, 0, w, h)
        self._selection_overlay.setPos(x, y)
        self._selection_overlay.set_selected(True)
        self._selection_overlay.setVisible(True)

    def _create_preview(self):
        """Create or update the preview item."""
        if self._preview_item:
            self._scene.removeItem(self._preview_item)
        self._preview_item = PDFPreviewItem(self._current_style, self._next_number, self._zoom)
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
        """Replace all annotations - rebuilds PDF annotations."""
        self._annotations = annotations
        # Rebuild all PDF annotations
        self._rebuild_pdf_annotations()
        self._render_page()

    def _rebuild_pdf_annotations(self):
        """Rebuild all PDF annotations from our annotation store."""
        if not self._doc:
            return

        # Remove all existing FreeText annotations
        for page_num in range(self._doc.page_count):
            page = self._doc.load_page(page_num)
            annots_to_delete = []
            for annot in page.annots():
                if annot.type[0] == fitz.PDF_ANNOT_FREE_TEXT:
                    annots_to_delete.append(annot)
            for annot in annots_to_delete:
                page.delete_annot(annot)

        # Add all annotations from store
        for annotation in self._annotations.all():
            self._add_pdf_annotation(annotation)

    def _add_pdf_annotation(self, annotation: NumberAnnotation) -> int:
        """Add an annotation to the PDF and return its xref."""
        if not self._doc:
            return 0

        page = self._doc.load_page(annotation.page)
        style = annotation.style
        text = str(annotation.number)

        # Calculate rect
        font = fitz.Font("helv")
        text_width = font.text_length(text, fontsize=style.font_size)
        text_height = style.font_size
        padding = style.padding

        rect = fitz.Rect(
            annotation.x,
            annotation.y,
            annotation.x + text_width + padding * 2,
            annotation.y + text_height + padding * 2
        )

        # Convert colors
        def hex_to_rgb(hex_color):
            hex_color = hex_color.lstrip('#')
            return tuple(int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4))

        fg_rgb = hex_to_rgb(style.text_color)
        bg_rgb = hex_to_rgb(style.bg_color) if style.bg_opacity > 0 else None

        # Create annotation
        annot = page.add_freetext_annot(
            rect,
            text,
            fontsize=style.font_size,
            fontname="helv",
            text_color=fg_rgb,
            fill_color=bg_rgb,
            align=fitz.TEXT_ALIGN_CENTER,
        )

        if bg_rgb and style.bg_opacity < 1.0:
            annot.set_opacity(style.bg_opacity)

        annot.update()

        annot_xref = annot.xref

        # Set annotation name (/NM) to our UUID for identification
        annot.set_name(annotation.id)

        # Explicitly set /Q (quadding) to 1 for center alignment
        # This helps ensure Acrobat respects the alignment when editing
        self._doc.xref_set_key(annot_xref, "Q", "1")

        # Set border if enabled
        if style.border_enabled:
            self._doc.xref_set_key(annot_xref, "Border", f"[0 0 {style.border_width}]")
            self._doc.xref_set_key(annot_xref, "BS", f"<</W {style.border_width}/S/S>>")
            annot.update()

        annotation.pdf_annot_xref = annot_xref
        return annot.xref

    def _delete_pdf_annotation(self, annotation: NumberAnnotation):
        """Delete an annotation from the PDF."""
        if not self._doc:
            return

        page = self._doc.load_page(annotation.page)

        # Calculate expected rect for position-based matching
        style = annotation.style
        text = str(annotation.number)
        font = fitz.Font("helv")
        text_width = font.text_length(text, fontsize=style.font_size)
        text_height = style.font_size
        padding = style.padding

        expected_rect = fitz.Rect(
            annotation.x,
            annotation.y,
            annotation.x + text_width + padding * 2,
            annotation.y + text_height + padding * 2
        )

        annot_to_delete = None

        # Try to find by xref first
        if annotation.pdf_annot_xref != 0:
            for annot in page.annots():
                if annot.xref == annotation.pdf_annot_xref:
                    annot_to_delete = annot
                    break

        # If not found by xref, try to find by position (within tolerance)
        if annot_to_delete is None:
            for annot in page.annots():
                if annot.type[0] == fitz.PDF_ANNOT_FREE_TEXT:
                    annot_rect = annot.rect
                    # Check if rectangles are close enough (within 2 pixels)
                    if (abs(annot_rect.x0 - expected_rect.x0) < 2 and
                        abs(annot_rect.y0 - expected_rect.y0) < 2 and
                        abs(annot_rect.x1 - expected_rect.x1) < 2 and
                        abs(annot_rect.y1 - expected_rect.y1) < 2):
                        annot_to_delete = annot
                        break

        if annot_to_delete:
            page.delete_annot(annot_to_delete)

    def _move_pdf_annotation(self, annotation: NumberAnnotation, old_x: float, old_y: float):
        """Move an annotation in the PDF by updating its rect (preserves appearance)."""
        if not self._doc:
            return False

        page = self._doc.load_page(annotation.page)

        # Calculate old rect to find the annotation
        style = annotation.style
        text = str(annotation.number)
        font = fitz.Font("helv")
        text_width = font.text_length(text, fontsize=style.font_size)
        text_height = style.font_size
        padding = style.padding

        width = text_width + padding * 2
        height = text_height + padding * 2

        old_rect = fitz.Rect(old_x, old_y, old_x + width, old_y + height)

        # Find the annotation
        annot_to_move = None

        # Try by xref first
        if annotation.pdf_annot_xref != 0:
            for annot in page.annots():
                if annot.xref == annotation.pdf_annot_xref:
                    annot_to_move = annot
                    break

        # Fallback to position matching
        if annot_to_move is None:
            for annot in page.annots():
                if annot.type[0] == fitz.PDF_ANNOT_FREE_TEXT:
                    annot_rect = annot.rect
                    if (abs(annot_rect.x0 - old_rect.x0) < 2 and
                        abs(annot_rect.y0 - old_rect.y0) < 2 and
                        abs(annot_rect.x1 - old_rect.x1) < 2 and
                        abs(annot_rect.y1 - old_rect.y1) < 2):
                        annot_to_move = annot
                        break

        if annot_to_move:
            # Calculate new rect
            new_rect = fitz.Rect(
                annotation.x,
                annotation.y,
                annotation.x + width,
                annotation.y + height
            )
            annot_to_move.set_rect(new_rect)
            annot_to_move.update()
            return True

        return False

    def set_tool_mode(self, mode: ToolMode):
        """Set the current tool mode."""
        self._tool_mode = mode
        if self._preview_item:
            self._preview_item.setVisible(False)
        if mode == ToolMode.SELECT:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.tool_changed.emit(mode.value)

    def get_tool_mode(self) -> ToolMode:
        return self._tool_mode

    def set_insert_mode(self, enabled: bool):
        self.set_tool_mode(ToolMode.INSERT if enabled else ToolMode.SELECT)

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
        self._zoom = max(self._min_zoom, min(self._max_zoom, zoom))
        self._fit_mode = False
        self._render_page()

    def get_zoom(self) -> float:
        return self._zoom

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())

            # Check if clicked on an annotation
            annotation = self._find_annotation_at(scene_pos)
            if annotation:
                self._select_annotation(annotation)
                self._dragging_annotation = annotation
                self._drag_start_pos = scene_pos
                self._drag_annotation_start = QPointF(annotation.x, annotation.y)
                event.accept()
                return

            # Clicked on empty space
            if self._selected_annotation:
                self._deselect_annotation()

            # Insert new annotation only in INSERT mode
            if self._tool_mode == ToolMode.INSERT and self._page_pixmap:
                page_rect = self._page_pixmap.boundingRect()
                if page_rect.contains(scene_pos):
                    self._insert_annotation(scene_pos)
                    event.accept()
                    return

        if event.button() == Qt.MouseButton.RightButton:
            if self._selected_annotation:
                self._deselect_annotation()
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            annotation = self._find_annotation_at(scene_pos)
            if annotation:
                self.edit_annotation_requested.emit(annotation)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

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
            scene_pos = self.mapToScene(event.position().toPoint())
            delta = scene_pos - self._drag_start_pos

            # Convert delta to PDF coordinates
            pdf_delta_x = delta.x() / self._zoom
            pdf_delta_y = delta.y() / self._zoom

            new_x = self._drag_annotation_start.x() + pdf_delta_x
            new_y = self._drag_annotation_start.y() + pdf_delta_y

            # Update annotation position (visual feedback via selection overlay)
            self._dragging_annotation.x = new_x
            self._dragging_annotation.y = new_y
            self._update_selection_overlay(self._dragging_annotation)
            event.accept()
            return

        # Update preview position
        if self._tool_mode == ToolMode.INSERT and self._preview_item is not None:
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
                self._preview_item = None

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton and self._dragging_annotation:
            old_x = self._drag_annotation_start.x()
            old_y = self._drag_annotation_start.y()
            ann = self._dragging_annotation

            if old_x != ann.x or old_y != ann.y:
                # Move PDF annotation in place (preserves appearance)
                if not self._move_pdf_annotation(ann, old_x, old_y):
                    # Fallback to delete/recreate if move failed
                    self._delete_pdf_annotation(ann)
                    self._add_pdf_annotation(ann)
                self._annotations.modified = True
                self._render_page()
                self._select_annotation(ann)  # Re-select after re-render
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

    def _find_annotation_at(self, scene_pos: QPointF) -> Optional[NumberAnnotation]:
        """Find annotation at the given scene position."""
        pdf_x = scene_pos.x() / self._zoom
        pdf_y = scene_pos.y() / self._zoom

        for annotation in self._annotations.get_for_page(self._current_page):
            style = annotation.style
            text = str(annotation.number)

            font = fitz.Font("helv")
            text_width = font.text_length(text, fontsize=style.font_size)
            text_height = style.font_size
            padding = style.padding

            rect = QRectF(
                annotation.x,
                annotation.y,
                text_width + padding * 2,
                text_height + padding * 2
            )

            if rect.contains(pdf_x, pdf_y):
                return annotation

        return None

    def _select_annotation(self, annotation: NumberAnnotation):
        """Select an annotation."""
        self._selected_annotation = annotation
        self._update_selection_overlay(annotation)
        self.annotation_selected.emit(annotation)

    def _deselect_annotation(self):
        """Deselect current annotation."""
        self._selected_annotation = None
        if self._selection_overlay:
            self._selection_overlay.setVisible(False)
        self.annotation_selected.emit(None)

    def _insert_annotation(self, scene_pos: QPointF):
        """Insert a new annotation at the given scene position."""
        pdf_x = scene_pos.x() / self._zoom
        pdf_y = scene_pos.y() / self._zoom

        # Center on click
        font = fitz.Font("helv")
        text_width = font.text_length(str(self._next_number), fontsize=self._current_style.font_size)
        text_height = self._current_style.font_size
        padding = self._current_style.padding

        width = text_width + padding * 2
        height = text_height + padding * 2

        pdf_x -= width / 2
        pdf_y -= height / 2

        # Check for duplicate
        if self._annotations.has_number(self._next_number):
            self.duplicate_number_requested.emit(self._next_number, pdf_x, pdf_y)
            return

        self._do_insert_annotation(pdf_x, pdf_y, self._next_number)

    def _do_insert_annotation(self, pdf_x: float, pdf_y: float, number: str):
        """Actually insert an annotation."""
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
                'border_enabled': self._current_style.border_enabled,
                'border_width': self._current_style.border_width,
            })
        )

        # Add to PDF and store
        self._add_pdf_annotation(annotation)
        self._annotations.add(annotation)

        # Re-render to show the annotation
        self._render_page()

        # Auto-increment
        main, sub = parse_number(number)
        if sub == 0:
            self._next_number = str(main + 1)
        else:
            self._next_number = f"{main}.{sub + 1}"

        if self._preview_item:
            self._preview_item.set_style(self._current_style, self._next_number)

        self.annotation_added.emit(annotation)

    def insert_annotation_at(self, pdf_x: float, pdf_y: float, number: str):
        """Insert an annotation at the given position with the given number."""
        self._do_insert_annotation(pdf_x, pdf_y, number)

    def _delete_selected_annotation(self):
        """Delete the currently selected annotation."""
        if not self._selected_annotation:
            return

        annotation = self._selected_annotation

        # Remove from PDF
        self._delete_pdf_annotation(annotation)

        # Remove from store
        self._annotations.remove(annotation.id)

        self._selected_annotation = None
        self._render_page()

        self.annotation_deleted.emit(annotation)
        self.annotation_selected.emit(None)

    def delete_annotation(self, annotation: NumberAnnotation):
        """Delete a specific annotation."""
        self._delete_pdf_annotation(annotation)
        self._annotations.remove(annotation.id)

        if self._selected_annotation == annotation:
            self._selected_annotation = None
            self.annotation_selected.emit(None)

        self._render_page()

    def add_annotation(self, annotation: NumberAnnotation):
        """Add an annotation (for undo/redo)."""
        self._add_pdf_annotation(annotation)
        self._annotations.add(annotation)
        self._render_page()

    def refresh_page(self):
        """Refresh the current page display."""
        self._render_page()

    def select_annotation(self, annotation: NumberAnnotation):
        """Select a specific annotation by its data."""
        self._select_annotation(annotation)

    def center_on_annotation(self, annotation: NumberAnnotation):
        """Center the view on an annotation."""
        x = annotation.x * self._zoom
        y = annotation.y * self._zoom
        self.centerOn(x, y)

    def get_page_image(self, page: int, scale: float = 2.0) -> Optional[QImage]:
        """Get a page as QImage (rendered from PDF with annotations)."""
        if not self._doc or page < 0 or page >= self._doc.page_count:
            return None

        pdf_page = self._doc.load_page(page)
        mat = fitz.Matrix(scale, scale)
        pix = pdf_page.get_pixmap(matrix=mat)

        if pix.alpha:
            fmt = QImage.Format.Format_RGBA8888
        else:
            fmt = QImage.Format.Format_RGB888

        return QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()

    def refresh_xrefs_after_save(self):
        """Refresh annotation xrefs after saving (xrefs may change during save)."""
        if not self._doc:
            return

        for annotation in self._annotations.all():
            # Calculate expected rect
            style = annotation.style
            text = str(annotation.number)
            font = fitz.Font("helv")
            text_width = font.text_length(text, fontsize=style.font_size)
            text_height = style.font_size
            padding = style.padding

            expected_rect = fitz.Rect(
                annotation.x,
                annotation.y,
                annotation.x + text_width + padding * 2,
                annotation.y + text_height + padding * 2
            )

            # Find matching annotation in PDF
            page = self._doc.load_page(annotation.page)
            for annot in page.annots():
                if annot.type[0] == fitz.PDF_ANNOT_FREE_TEXT:
                    annot_rect = annot.rect
                    # Check if rectangles match (within 2 pixels)
                    if (abs(annot_rect.x0 - expected_rect.x0) < 2 and
                        abs(annot_rect.y0 - expected_rect.y0) < 2 and
                        abs(annot_rect.x1 - expected_rect.x1) < 2 and
                        abs(annot_rect.y1 - expected_rect.y1) < 2):
                        annotation.pdf_annot_xref = annot.xref
                        break

    def save_metadata_to_pdf(self):
        """Save our annotation data as JSON in PDF metadata."""
        if not self._doc:
            return

        import json

        # Serialize annotation store to JSON
        annotations_json = self._annotations.to_json()

        # Get current metadata and add our data
        metadata = self._doc.metadata or {}
        metadata["keywords"] = f"{NAPISY_METADATA_KEY}:{annotations_json}"

        # Set metadata
        self._doc.set_metadata(metadata)

    def load_metadata_from_pdf(self) -> bool:
        """Load our annotation data from PDF metadata. Returns True if found."""
        if not self._doc:
            return False

        import json

        try:
            metadata = self._doc.metadata
            if not metadata:
                return False

            keywords = metadata.get("keywords", "")
            if not keywords or not keywords.startswith(f"{NAPISY_METADATA_KEY}:"):
                return False

            # Extract JSON after our marker
            json_str = keywords[len(f"{NAPISY_METADATA_KEY}:"):]

            # Parse and restore annotations
            self._annotations.from_json(json_str)

            # Match annotations to PDF annotation xrefs by name (/NM)
            self._sync_xrefs_by_name()

            return True

        except Exception as e:
            print(f"Error loading metadata: {e}")
            return False

    def _sync_xrefs_by_name(self):
        """Sync annotation xrefs by matching /NM field to our annotation IDs."""
        if not self._doc:
            return

        # Build a map of annotation ID -> annotation
        id_to_annotation = {a.id: a for a in self._annotations.all()}

        # Scan all pages for annotations with matching names
        for page_num in range(self._doc.page_count):
            page = self._doc.load_page(page_num)
            for annot in page.annots():
                if annot.type[0] == fitz.PDF_ANNOT_FREE_TEXT:
                    name = annot.info.get("name", "")
                    if name in id_to_annotation:
                        id_to_annotation[name].pdf_annot_xref = annot.xref
