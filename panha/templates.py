"""Persistence for batch templates.

User templates are stored in the ``templates`` key of
``panha/metadata.json`` (the same file that holds ``last_state`` and
``last_template``).  The :class:`ConfigStore` handles document-level
read/write so unrelated keys are never clobbered.

Factory presets (bundled in :mod:`panha.presets` from
``panha/presets.json``) are *merged* into the same store at read time
so the existing Template combo / dropdown plumbing can list them next
to the user's saved templates without special casing. They are
read-only:

* :meth:`TemplateStore.names`/:meth:`TemplateStore.get` see them.
* :meth:`TemplateStore.delete` and :meth:`TemplateStore.upsert` cannot
  overwrite or remove them — see :meth:`TemplateStore.is_factory`.
"""

from __future__ import annotations

from pathlib import Path

from .config_store import CONFIG_PATH, ConfigStore
from .presets import is_factory_preset, load_factory_presets


class TemplateStore:
    """Thin read/write wrapper around the ``templates`` section of
    ``panha/metadata.json``."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        include_factory: bool = True,
    ) -> None:
        self._store = ConfigStore(path if path is not None else CONFIG_PATH)
        # Switchable so tests / advanced callers can opt out of the
        # bundled presets without monkey-patching the loader.
        self._include_factory = include_factory

    @property
    def path(self) -> Path:
        return self._store.path

    def load(self) -> dict[str, dict]:
        """Return ``{name: payload}`` for every template visible in the UI.

        User templates take precedence: a user-saved template with the
        same name as a factory preset shadows the factory entry. This
        lets advanced users "fork" a factory preset by saving over its
        name.
        """
        user = self._load_user()
        if not self._include_factory:
            return user
        merged: dict[str, dict] = dict(load_factory_presets())
        # User templates override factory entries with the same name.
        merged.update(user)
        return merged

    def _load_user(self) -> dict[str, dict]:
        return self._store.load_templates()

    def save(self, templates: dict[str, dict]) -> None:
        # Never write factory presets to the user file — the bundled
        # JSON is the source of truth for them, and persisting copies
        # would diverge silently on future app upgrades.
        user_only = {
            name: payload
            for name, payload in templates.items()
            if not is_factory_preset(name)
        }
        self._store.save_templates(user_only)

    def names(self) -> list[str]:
        return sorted(self.load().keys())

    def get(self, name: str) -> dict | None:
        return self.load().get(name)

    def upsert(self, name: str, payload: dict) -> None:
        if is_factory_preset(name):
            # Refuse to overwrite a bundled preset — protects the user
            # from accidentally clobbering a "Default" / "Modern Pop" /
            # ... entry by Save-As-ing on top of it.
            raise FactoryPresetReadOnlyError(name)
        templates = self._load_user()
        templates[name] = payload
        self.save(templates)

    def delete(self, name: str) -> bool:
        if is_factory_preset(name):
            return False  # silently refuse — factory presets are read-only
        templates = self._load_user()
        if name not in templates:
            return False
        del templates[name]
        self.save(templates)
        return True

    @staticmethod
    def is_factory(name: str) -> bool:
        """True when ``name`` is a bundled factory preset (read-only)."""
        return is_factory_preset(name)


class FactoryPresetReadOnlyError(ValueError):
    """Raised when a write would overwrite a bundled factory preset."""

    def __init__(self, name: str) -> None:
        super().__init__(
            f"'{name}' is a bundled factory preset and cannot be overwritten. "
            "Save with a different name to keep your changes."
        )
        self.name = name
