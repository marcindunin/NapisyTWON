"""Data models for annotations and styles."""

from dataclasses import dataclass, field, asdict
from typing import Optional
import json
import uuid
import re


def parse_number(num_str: str) -> tuple[int, int]:
    """Parse a number string like '67' or '67.1' into (main, sub) tuple.

    Returns (67, 0) for '67' and (67, 1) for '67.1'
    """
    if '.' in str(num_str):
        parts = str(num_str).split('.')
        return (int(parts[0]), int(parts[1]))
    return (int(num_str), 0)


def format_number(main: int, sub: int = 0) -> str:
    """Format a number tuple back to string."""
    if sub == 0:
        return str(main)
    return f"{main}.{sub}"


def compare_numbers(a: str, b: str) -> int:
    """Compare two number strings. Returns -1, 0, or 1."""
    pa = parse_number(a)
    pb = parse_number(b)
    if pa < pb:
        return -1
    elif pa > pb:
        return 1
    return 0


def sort_key(num_str: str) -> tuple[int, int]:
    """Return sort key for a number string."""
    return parse_number(num_str)


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
    border_enabled: bool = False
    border_width: int = 2

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
    number: str = "1"  # String to support decimals like "67.1"
    style: NumberStyle = field(default_factory=NumberStyle)
    pdf_annot_xref: int = 0  # PDF annotation xref for direct editing

    def __post_init__(self):
        # Ensure number is always a string
        self.number = str(self.number)

    def to_dict(self) -> dict:
        data = asdict(self)
        data['style'] = self.style.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "NumberAnnotation":
        style_data = data.pop('style', {})
        style = NumberStyle.from_dict(style_data) if style_data else NumberStyle()
        # Ensure number is string
        if 'number' in data:
            data['number'] = str(data['number'])
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

    def sort_key(self) -> tuple[int, int]:
        """Return sort key for ordering."""
        return parse_number(self.number)

    def display_number(self) -> str:
        """Return display string for the number."""
        return self.number


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

    def get_by_number(self, number: str) -> Optional[NumberAnnotation]:
        """Find annotation by number."""
        for a in self._annotations.values():
            if a.number == str(number):
                return a
        return None

    def get_for_page(self, page: int) -> list[NumberAnnotation]:
        return [a for a in self._annotations.values() if a.page == page]

    def all(self) -> list[NumberAnnotation]:
        return list(self._annotations.values())

    def all_sorted(self) -> list[NumberAnnotation]:
        """Return all annotations sorted by number."""
        return sorted(self._annotations.values(), key=lambda a: a.sort_key())

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

    def get_next_number(self) -> str:
        """Get the next whole number to use (max + 1)."""
        if not self._annotations:
            return "1"
        # Find max whole number
        max_main = 0
        for a in self._annotations.values():
            main, _ = parse_number(a.number)
            if main > max_main:
                max_main = main
        return str(max_main + 1)

    def has_number(self, number: str) -> bool:
        """Check if a number already exists."""
        return any(a.number == str(number) for a in self._annotations.values())

    def get_numbers_from(self, number: str) -> list[NumberAnnotation]:
        """Get all annotations with number >= given number (whole numbers only)."""
        target_main, _ = parse_number(number)
        result = []
        for a in self._annotations.values():
            main, sub = parse_number(a.number)
            # Only include whole numbers (sub == 0) that are >= target
            if sub == 0 and main >= target_main:
                result.append(a)
        return sorted(result, key=lambda a: a.sort_key())

    def advance_numbers_from(self, from_number: str, delta: int = 1) -> list[tuple[NumberAnnotation, str, str]]:
        """Advance all whole numbers >= from_number by delta.

        Returns list of (annotation, old_number, new_number) for undo.
        """
        changes = []
        target_main, _ = parse_number(from_number)

        for a in self._annotations.values():
            main, sub = parse_number(a.number)
            # Only advance whole numbers
            if sub == 0 and main >= target_main:
                old_num = a.number
                new_num = str(main + delta)
                a.number = new_num
                changes.append((a, old_num, new_num))

        if changes:
            self._modified = True
        return changes

    def decrease_numbers_from(self, from_number: str, delta: int = 1) -> list[tuple[NumberAnnotation, str, str]]:
        """Decrease all whole numbers > from_number by delta.

        Returns list of (annotation, old_number, new_number) for undo.
        """
        changes = []
        target_main, _ = parse_number(from_number)

        for a in self._annotations.values():
            main, sub = parse_number(a.number)
            # Only decrease whole numbers that are greater than target
            if sub == 0 and main > target_main:
                old_num = a.number
                new_num = str(main - delta)
                a.number = new_num
                changes.append((a, old_num, new_num))

        if changes:
            self._modified = True
        return changes

    def get_next_sub_number(self, base: str) -> str:
        """Get next available sub-number (e.g., 67.1, 67.2)."""
        base_main, _ = parse_number(base)
        max_sub = 0

        for a in self._annotations.values():
            main, sub = parse_number(a.number)
            if main == base_main and sub > max_sub:
                max_sub = sub

        return f"{base_main}.{max_sub + 1}"

    def find_gaps(self) -> list[int]:
        """Find missing whole numbers in sequence.

        Returns list of missing numbers.
        """
        if not self._annotations:
            return []

        # Get all whole numbers
        whole_numbers = set()
        for a in self._annotations.values():
            main, sub = parse_number(a.number)
            if sub == 0:
                whole_numbers.add(main)

        if not whole_numbers:
            return []

        min_num = min(whole_numbers)
        max_num = max(whole_numbers)

        expected = set(range(min_num, max_num + 1))
        missing = sorted(expected - whole_numbers)

        return missing

    def validate_sequence(self) -> tuple[bool, str]:
        """Validate the number sequence.

        Returns (is_valid, message).
        """
        gaps = self.find_gaps()
        if gaps:
            if len(gaps) == 1:
                return False, f"Missing number: {gaps[0]}"
            elif len(gaps) <= 5:
                return False, f"Missing numbers: {', '.join(map(str, gaps))}"
            else:
                return False, f"Missing {len(gaps)} numbers: {gaps[0]}...{gaps[-1]}"
        return True, "Sequence OK"


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
