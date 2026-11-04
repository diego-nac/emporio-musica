"""Runtime configuration and safe per-turn construction for the Streamlit app."""

from __future__ import annotations

import fcntl
import os
import threading
from pathlib import Path
from typing import Any

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from src.agent.gemini_client import DEFAULT_MODEL, create_gemini_client
from src.agent.service import AgentResult, AgentService
from src.data.db import ingest_csvs
from src.domain.session import get_demo_identity
from src.policies.catalog import PolicyService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DATABASE_INIT_LOCK = threading.Lock()


def _secret_value(name: str) -> Any:
    try:
        return st.secrets.get(name)
    except (FileNotFoundError, StreamlitSecretNotFoundError):
        return None


def _setting(name: str, default: Any = None) -> Any:
    value = os.environ.get(name)
    if value:
        return value
    value = _secret_value(name)
    return value if value is not None else default


def load_access_keys() -> dict[str, object]:
    return {
        "ADMIN_ACCESS_KEY": _setting("ADMIN_ACCESS_KEY"),
        "DEMO_ACCESS_KEY": _setting("DEMO_ACCESS_KEY"),
    }


def access_keys_are_configured(keys: dict[str, object]) -> bool:
    admin_key = keys.get("ADMIN_ACCESS_KEY")
    demo_key = keys.get("DEMO_ACCESS_KEY")
    return (
        isinstance(admin_key, str)
        and bool(admin_key)
        and isinstance(demo_key, str)
        and bool(demo_key)
        and admin_key != demo_key
    )


def load_gemini_key() -> str | None:
    value = _setting("GEMINI_API_KEY")
    return value if isinstance(value, str) and value else None


def load_model_name() -> str:
    value = _setting("GEMINI_MODEL", DEFAULT_MODEL)
    return value.strip() if isinstance(value, str) and value.strip() else DEFAULT_MODEL


def get_database_path() -> Path:
    configured = _setting("DB_PATH")
    if not isinstance(configured, str) or not configured.strip():
        return (PROJECT_ROOT / "work" / "app.db").resolve()
    path = Path(configured.strip()).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


@st.cache_resource(show_spinner=False)
def _initialize_database_resource(database_path: str, source_directory: str) -> str:
    path = Path(database_path)
    source = Path(source_directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".init.lock")
    with _DATABASE_INIT_LOCK:
        with lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                if not path.exists():
                    ingest_csvs(source, path)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    return str(path)


def ensure_database(database_path: Path | None = None) -> Path:
    path = database_path or get_database_path()
    if path.exists():
        return path
    source = PROJECT_ROOT / "data" / "demo"
    if not source.is_dir():
        raise FileNotFoundError("demonstration data is unavailable")
    _initialize_database_resource.clear()
    _initialize_database_resource(str(path), str(source))
    if not path.exists():
        raise FileNotFoundError("database initialization did not create the database")
    return path


@st.cache_resource(show_spinner=False)
def get_policy_service(catalog_path: str) -> PolicyService:
    return PolicyService(Path(catalog_path))


def run_chat_turn(
    *,
    db_path: Path,
    policy_service: PolicyService,
    message: str,
    history: list[dict[str, str]],
    demo_profile: str = "Cliente Demonstração",
) -> AgentResult:
    """Build a client for one turn and close it immediately; credentials never enter session state."""
    api_key = load_gemini_key()
    client = create_gemini_client(api_key) if api_key else None
    try:
        service = AgentService(
            db_path=db_path,
            policy_service=policy_service,
            model_client=client,
            model_name=load_model_name(),
        )
        return service.ask(message, history=history, demo_identity=get_demo_identity(demo_profile))
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
