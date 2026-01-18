"""Data models for annotations and styles."""

from dataclasses import dataclass, field, asdict
from typing import Optional
import json
import uuid


@dataclass
class NumberStyle:
    """Style settings for number annotations."""
    name: str = "Default"
    font_family: str = "Arial"
    font_size: int = 48
    text_color: str = "#000000"
    bg_color: str = "#FFFF00"
    bg_opacity: float = 1.0
    padding: int = 4

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "NumberStyle":
        return cls(**data)


@dataclass
class NumberAnnotation:
    """A number annotation on a PDF page."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    page: int = 0
    x: float = 0.0  # PDF coordinates
    y: float = 0.0
    number: int = 1
    style: NumberStyle = field(default_factory=NumberStyle)
    applied_to_pdf: bool = False  # Track if already saved to PDF

    def to_dict(self) -> dict:
        data = asdict(self)
        data['style'] = self.style.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "NumberAnnotation":
        style_data = data.pop('style', {})
        style = NumberStyle.from_dict(style_data) if style_data else NumberStyle()
        return cls(style=style, **data)

    def copy(self) -> "NumberAnnotation":
        """Create a deep copy of this annotation."""
        return NumberAnnotation(
            id=str(uuid.uuid4()),  # New ID for copy
            page=self.page,
            x=self.x,
            y=self.y,
            number=self.number,
            style=NumberStyle(**asdict(self.style)),
            applied_to_pdf=False
        )


class AnnotationStore:
    """Manages all annotations for a document."""

    def __init__(self):
        self._annotations: dict[str, NumberAnnotation] = {}
        self._modified = False

    def add(self, annotation: NumberAnnotation) -> None:
        self._annotations[annotation.id] = annotation
        self._modified = True

    def remove(self, annotation_id: str) -> Optional[NumberAnnotation]:
        self._modified = True
        return self._annotations.pop(annotation_id, None)

    def get(self, annotation_id: str) -> Optional[NumberAnnotation]:
        return self._annotations.get(annotation_id)

    def get_for_page(self, page: int) -> list[NumberAnnotation]:
        return [a for a in self._annotations.values() if a.page == page]

    def all(self) -> list[NumberAnnotation]:
        return list(self._annotations.values())

    def clear(self) -> None:
        self._annotations.clear()
        self._modified = True

    def count(self) -> int:
        return len(self._annotations)

    @property
    def modified(self) -> bool:
        return self._modified

    @modified.setter
    def modified(self, value: bool):
        self._modified = value

    def to_json(self) -> str:
        data = [a.to_dict() for a in self._annotations.values()]
        return json.dumps(data, indent=2)

    def from_json(self, json_str: str) -> None:
        data = json.loads(json_str)
        self._annotations.clear()
        for item in data:
            annotation = NumberAnnotation.from_dict(item)
            self._annotations[annotation.id] = annotation
        self._modified = True

    def get_next_number(self) -> int:
        """Get the next number to use (max + 1)."""
        if not self._annotations:
            return 1
        return max(a.number for a in self._annotations.values()) + 1


class StylePresets:
    """Manages saved style presets."""

    def __init__(self):
        self._presets: dict[str, NumberStyle] = {
            "Default": NumberStyle(),
            "Red on White": NumberStyle(
                name="Red on White",
                text_color="#FF0000",
                bg_color="#FFFFFF"
            ),
            "White on Black": NumberStyle(
                name="White on Black",
                text_color="#FFFFFF",
                bg_color="#000000"
            ),
            "Large Yellow": NumberStyle(
                name="Large Yellow",
                font_size=72,
                text_color="#000000",
                bg_color="#FFFF00"
            ),
            "Subtle Gray": NumberStyle(
                name="Subtle Gray",
                text_color="#333333",
                bg_color="#CCCCCC",
                bg_opacity=0.7
            ),
        }

    def get(self, name: str) -> Optional[NumberStyle]:
        preset = self._presets.get(name)
        if preset:
            # Return a copy
            return NumberStyle(**asdict(preset))
        return None

    def save(self, style: NumberStyle) -> None:
        self._presets[style.name] = style

    def delete(self, name: str) -> bool:
        if name in self._presets and name != "Default":
            del self._presets[name]
            return True
        return False

    def names(self) -> list[str]:
        return list(self._presets.keys())

    def to_json(self) -> str:
        data = {name: style.to_dict() for name, style in self._presets.items()}
        return json.dumps(data, indent=2)

    def from_json(self, json_str: str) -> None:
        data = json.loads(json_str)
        for name, style_data in data.items():
            self._presets[name] = NumberStyle.from_dict(style_data)
