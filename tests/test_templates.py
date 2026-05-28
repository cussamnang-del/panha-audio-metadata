"""Tests for the template store.

These tests focus on the *user* side of the store — JSON persistence,
upsert / delete semantics, corrupt-file handling. The bundled factory
presets that :class:`TemplateStore` normally merges in are switched
off here so the assertions can talk about user templates in isolation;
factory-preset integration is covered separately in
``test_presets.py``.
"""

from __future__ import annotations

from pathlib import Path

from panha.templates import TemplateStore


def _user_store(path: Path) -> TemplateStore:
    """Build a :class:`TemplateStore` that doesn't merge factory presets."""
    return TemplateStore(path, include_factory=False)


def test_load_returns_empty_when_file_missing(tmp_path: Path):
    store = _user_store(tmp_path / "templates.json")
    assert store.load() == {}
    assert store.names() == []
    assert store.get("nope") is None


def test_upsert_creates_then_overwrites(tmp_path: Path):
    store = _user_store(tmp_path / "templates.json")
    store.upsert("rock", {"genre": "Rock"})
    assert store.names() == ["rock"]
    assert store.get("rock") == {"genre": "Rock"}
    store.upsert("rock", {"genre": "Hard Rock"})
    assert store.get("rock") == {"genre": "Hard Rock"}


def test_names_are_sorted(tmp_path: Path):
    store = _user_store(tmp_path / "templates.json")
    for name in ("zeta", "alpha", "beta"):
        store.upsert(name, {})
    assert store.names() == ["alpha", "beta", "zeta"]


def test_delete_returns_false_when_missing(tmp_path: Path):
    store = _user_store(tmp_path / "templates.json")
    store.upsert("rock", {})
    assert store.delete("missing") is False
    assert store.delete("rock") is True
    assert store.names() == []


def test_corrupt_file_falls_back_to_empty(tmp_path: Path):
    path = tmp_path / "templates.json"
    path.write_text("{not valid json", encoding="utf-8")
    store = _user_store(path)
    assert store.load() == {}


def test_non_dict_top_level_falls_back_to_empty(tmp_path: Path):
    path = tmp_path / "templates.json"
    path.write_text('["templates", "must", "be", "a", "dict"]', encoding="utf-8")
    store = _user_store(path)
    assert store.load() == {}
