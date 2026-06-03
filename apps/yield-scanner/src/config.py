"""Módulo de configuração partilhado — carrega YAMLs e helpers."""

import os
import yaml
from pathlib import Path
from typing import Any, Optional

BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"


def load_yaml(name: str) -> dict:
    """Carrega um ficheiro YAML de config/."""
    path = CONFIG_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Config não encontrada: {path}")
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def load_assets() -> dict:
    return load_yaml("assets")


def load_pools() -> dict:
    return load_yaml("pools")


def load_telegram_config() -> dict:
    return load_yaml("telegram")


def get_telegram_creds() -> tuple[Optional[str], Optional[str]]:
    """Devolve (bot_token, chat_id) lidos das variáveis de ambiente."""
    try:
        cfg = load_telegram_config()
        bot_token = os.environ.get(cfg["telegram"]["bot_token_env"])
        chat_id = os.environ.get(cfg["telegram"]["chat_id_env"])
        return bot_token, chat_id
    except Exception:
        return None, None


def get_env_or_default(key: str, default: Any) -> Any:
    """Lê variável de ambiente ou devolve default."""
    return os.environ.get(key, default)


def get_db_path() -> Path:
    """Devolve path do banco de dados SQLite."""
    return DATA_DIR / "defillama_yields.db"


def ensure_data_dir() -> Path:
    """Cria e devolve o diretório de estado local."""
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR


def get_log_path() -> Path:
    """Devolve path do ficheiro de log."""
    return DATA_DIR / "scanner.log"
