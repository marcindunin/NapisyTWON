"""Undo/Redo manager for annotation operations."""

from dataclasses import dataclass
from typing import Any, Callable, Optional
from PySide6.QtCore import QObject, Signal


@dataclass
class UndoAction:
    """Represents a single undoable action."""
    description: str
    undo_data: Any
    redo_data: Any
    undo_func: Callable[[Any], None]
    redo_func: Callable[[Any], None]


class UndoManager(QObject):
    """Manages undo/redo stack for annotations."""

    state_changed = Signal()  # Emitted when undo/redo availability changes

    def __init__(self, max_history: int = 50):
        super().__init__()
        self._undo_stack: list[UndoAction] = []
        self._redo_stack: list[UndoAction] = []
        self._max_history = max_history

    def push(self, action: UndoAction) -> None:
        """Push a new action onto the undo stack."""
        self._undo_stack.append(action)
        self._redo_stack.clear()  # Clear redo on new action

        # Limit history size
        if len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)

        self.state_changed.emit()

    def undo(self) -> Optional[str]:
        """Undo the last action. Returns action description or None."""
        if not self._undo_stack:
            return None

        action = self._undo_stack.pop()
        action.undo_func(action.undo_data)
        self._redo_stack.append(action)
        self.state_changed.emit()
        return action.description

    def redo(self) -> Optional[str]:
        """Redo the last undone action. Returns action description or None."""
        if not self._redo_stack:
            return None

        action = self._redo_stack.pop()
        action.redo_func(action.redo_data)
        self._undo_stack.append(action)
        self.state_changed.emit()
        return action.description

    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def undo_description(self) -> Optional[str]:
        """Get description of next undo action."""
        if self._undo_stack:
            return self._undo_stack[-1].description
        return None

    def redo_description(self) -> Optional[str]:
        """Get description of next redo action."""
        if self._redo_stack:
            return self._redo_stack[-1].description
        return None

    def clear(self) -> None:
        """Clear all undo/redo history."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.state_changed.emit()
