"""Tests for data models: parsing, validation, sorting, and serialization."""

import json
import pytest
from src.models import (
    parse_number, format_number, compare_numbers, sort_key,
    NumberStyle, NumberAnnotation, AnnotationStore, StylePresets,
)


# --- parse_number ---

class TestParseNumber:
    def test_whole_number(self):
        assert parse_number("67") == (67, 0)

    def test_sub_number(self):
        assert parse_number("67.1") == (67, 1)

    def test_with_p_suffix(self):
        assert parse_number("67p") == (67, 0)

    def test_sub_with_p_suffix(self):
        assert parse_number("67.1p") == (67, 1)

    def test_single_digit(self):
        assert parse_number("1") == (1, 0)

    def test_large_number(self):
        assert parse_number("999") == (999, 0)

    def test_integer_input(self):
        assert parse_number(1) == (1, 0)

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_number("abc")


# --- format_number ---

class TestFormatNumber:
    def test_whole(self):
        assert format_number(67) == "67"

    def test_sub(self):
        assert format_number(67, 1) == "67.1"

    def test_zero_sub(self):
        assert format_number(5, 0) == "5"


# --- compare_numbers ---

class TestCompareNumbers:
    def test_equal(self):
        assert compare_numbers("5", "5") == 0

    def test_less(self):
        assert compare_numbers("5", "10") == -1

    def test_greater(self):
        assert compare_numbers("10", "5") == 1

    def test_sub_numbers(self):
        assert compare_numbers("5.1", "5.2") == -1

    def test_whole_vs_sub(self):
        assert compare_numbers("5", "5.1") == -1

    def test_p_suffix_ignored(self):
        assert compare_numbers("5p", "5") == 0


# --- sort_key ---

class TestSortKey:
    def test_returns_tuple(self):
        assert sort_key("67.1") == (67, 1)

    def test_sorting(self):
        nums = ["10", "2", "1.1", "1", "3.2", "3"]
        result = sorted(nums, key=sort_key)
        assert result == ["1", "1.1", "2", "3", "3.2", "10"]


# --- NumberStyle ---

class TestNumberStyle:
    def test_defaults(self):
        s = NumberStyle()
        assert s.font_family == "Arial"
        assert s.font_size == 24
        assert s.bg_opacity == 1.0

    def test_to_dict_roundtrip(self):
        s = NumberStyle(font_size=48, text_color="#FF0000")
        d = s.to_dict()
        s2 = NumberStyle.from_dict(d)
        assert s2.font_size == 48
        assert s2.text_color == "#FF0000"

    def test_from_dict_missing_keys(self):
        s = NumberStyle.from_dict({"font_size": 36})
        assert s.font_size == 36
        assert s.font_family == "Arial"  # default preserved

    def test_from_dict_extra_keys_ignored(self):
        s = NumberStyle.from_dict({"font_size": 36, "nonexistent": True})
        assert s.font_size == 36


# --- NumberAnnotation ---

class TestNumberAnnotation:
    def test_number_coerced_to_string(self):
        a = NumberAnnotation(number=42)
        assert a.number == "42"

    def test_sort_key(self):
        a = NumberAnnotation(number="5.2")
        assert a.sort_key() == (5, 2)

    def test_display_number(self):
        a = NumberAnnotation(number="5p")
        assert a.display_number() == "5p"

    def test_to_dict_roundtrip(self):
        a = NumberAnnotation(page=2, x=10.5, y=20.3, number="7")
        d = a.to_dict()
        a2 = NumberAnnotation.from_dict(d)
        assert a2.page == 2
        assert a2.x == 10.5
        assert a2.number == "7"

    def test_from_dict_number_coerced(self):
        d = {"id": "test", "page": 0, "x": 0, "y": 0, "number": 5,
             "pdf_annot_xref": 0, "pdf_tail_xref": 0, "pdf_p_xref": 0}
        a = NumberAnnotation.from_dict(d)
        assert a.number == "5"


# --- AnnotationStore ---

class TestAnnotationStore:
    def _make_store(self, numbers: list[str]) -> AnnotationStore:
        store = AnnotationStore()
        for n in numbers:
            store.add(NumberAnnotation(number=n))
        return store

    def test_add_and_count(self):
        store = self._make_store(["1", "2", "3"])
        assert store.count() == 3

    def test_remove(self):
        store = AnnotationStore()
        a = NumberAnnotation(number="1")
        store.add(a)
        removed = store.remove(a.id)
        assert removed is a
        assert store.count() == 0

    def test_remove_nonexistent(self):
        store = AnnotationStore()
        assert store.remove("nonexistent") is None

    def test_get_by_number(self):
        store = self._make_store(["5", "10"])
        a = store.get_by_number("5")
        assert a is not None
        assert a.number == "5"

    def test_get_by_number_with_p(self):
        store = self._make_store(["5p"])
        assert store.get_by_number("5") is not None

    def test_get_for_page(self):
        store = AnnotationStore()
        store.add(NumberAnnotation(number="1", page=0))
        store.add(NumberAnnotation(number="2", page=1))
        store.add(NumberAnnotation(number="3", page=0))
        assert len(store.get_for_page(0)) == 2
        assert len(store.get_for_page(1)) == 1

    def test_all_sorted(self):
        store = self._make_store(["3", "1", "2.1", "2"])
        nums = [a.number for a in store.all_sorted()]
        assert nums == ["1", "2", "2.1", "3"]

    def test_has_number(self):
        store = self._make_store(["5", "10"])
        assert store.has_number("5") is True
        assert store.has_number("7") is False

    def test_has_number_p_equivalence(self):
        store = self._make_store(["5p"])
        assert store.has_number("5") is True
        assert store.has_number("5p") is True

    def test_get_next_number_empty(self):
        store = AnnotationStore()
        assert store.get_next_number() == "1"

    def test_get_next_number(self):
        store = self._make_store(["3", "5", "1"])
        assert store.get_next_number() == "6"

    def test_get_next_sub_number(self):
        store = self._make_store(["5", "5.1", "5.2"])
        assert store.get_next_sub_number("5") == "5.3"

    def test_get_next_sub_number_none_existing(self):
        store = self._make_store(["5"])
        assert store.get_next_sub_number("5") == "5.1"

    def test_find_gaps(self):
        store = self._make_store(["1", "2", "5"])
        assert store.find_gaps() == [3, 4]

    def test_find_gaps_no_gaps(self):
        store = self._make_store(["1", "2", "3"])
        assert store.find_gaps() == []

    def test_find_gaps_empty(self):
        store = AnnotationStore()
        assert store.find_gaps() == []

    def test_validate_sequence_ok(self):
        store = self._make_store(["1", "2", "3"])
        valid, msg = store.validate_sequence()
        assert valid is True

    def test_validate_sequence_gaps(self):
        store = self._make_store(["1", "3"])
        valid, msg = store.validate_sequence()
        assert valid is False
        assert "2" in msg

    def test_advance_numbers(self):
        store = self._make_store(["1", "2", "3"])
        changes = store.advance_numbers_from("2", 1)
        nums = sorted([a.number for a in store.all()])
        assert "1" in nums
        assert "3" in nums
        assert "4" in nums
        assert len(changes) == 2

    def test_advance_preserves_p_suffix(self):
        store = self._make_store(["1", "2p", "3"])
        store.advance_numbers_from("2", 1)
        p_ann = [a for a in store.all() if a.number.endswith('p')]
        assert len(p_ann) == 1
        assert p_ann[0].number == "3p"

    def test_decrease_numbers(self):
        store = self._make_store(["1", "2", "3"])
        changes = store.decrease_numbers_from("1", 1)
        nums = sorted([a.number for a in store.all()], key=sort_key)
        assert nums == ["1", "1", "2"]
        assert len(changes) == 2

    def test_json_roundtrip(self):
        store = self._make_store(["1", "2.1", "3p"])
        json_str = store.to_json()
        store2 = AnnotationStore()
        store2.from_json(json_str)
        assert store2.count() == 3
        assert store2.has_number("2.1")
        assert store2.has_number("3")

    def test_modified_flag(self):
        store = AnnotationStore()
        store.modified = False
        store.add(NumberAnnotation(number="1"))
        assert store.modified is True
        store.modified = False
        assert store.modified is False


# --- StylePresets ---

class TestStylePresets:
    def test_default_preset_exists(self):
        p = StylePresets()
        assert "Default" in p.names()

    def test_save_and_get(self):
        p = StylePresets()
        s = NumberStyle(name="Big", font_size=100)
        p.save(s)
        loaded = p.get("Big")
        assert loaded is not None
        assert loaded.font_size == 100

    def test_get_returns_copy(self):
        p = StylePresets()
        s1 = p.get("Default")
        s2 = p.get("Default")
        assert s1 is not s2

    def test_delete(self):
        p = StylePresets()
        p.save(NumberStyle(name="Temp"))
        assert p.delete("Temp") is True
        assert p.get("Temp") is None

    def test_cannot_delete_default(self):
        p = StylePresets()
        assert p.delete("Default") is False

    def test_json_roundtrip(self):
        p = StylePresets()
        p.save(NumberStyle(name="Custom", font_size=72))
        json_str = p.to_json()
        p2 = StylePresets()
        p2.from_json(json_str)
        loaded = p2.get("Custom")
        assert loaded is not None
        assert loaded.font_size == 72
