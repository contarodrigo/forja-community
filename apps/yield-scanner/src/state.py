"""Módulo de gestão de estado persistente — substitui /tmp/ por data/."""

import json
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"


class StateManager:
    """Gerencia estado JSON persistente no diretório data/."""

    def __init__(self, name: str):
        self.path = DATA_DIR / f"{name}.json"
        self._data: dict = {}
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                with open(self.path, "r") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"[StateManager] Aviso: erro a carregar {self.path}: {e}")
                self._data = {}
        else:
            self._data = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any):
        self._data[key] = value
        self._save()

    def update(self, updates: dict):
        self._data.update(updates)
        self._save()

    def all(self) -> dict:
        return dict(self._data)

    def _save(self):
        try:
            DATA_DIR.mkdir(exist_ok=True)
            with open(self.path, "w") as f:
                json.dump(self._data, f, indent=2, default=str)
        except IOError as e:
            print(f"[StateManager] Erro a gravar {self.path}: {e}")

    def reset(self):
        self._data = {}
        if self.path.exists():
            self.path.unlink()


def get_state(name: str) -> StateManager:
    """Factory para StateManager."""
    return StateManager(name)
