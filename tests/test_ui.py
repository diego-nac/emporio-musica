from __future__ import annotations

import sqlite3
from pathlib import Path

from streamlit.testing.v1 import AppTest
import pytest

from src.ui import runtime


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture(autouse=True)
def isolate_streamlit_secrets(monkeypatch):
    monkeypatch.setattr(runtime, "_secret_value", lambda _name: None)


def set_access_env(monkeypatch, db_path: Path, admin: str = "test-admin-key", demo: str = "test-demo-key") -> None:
    monkeypatch.setenv("ADMIN_ACCESS_KEY", admin)
    monkeypatch.setenv("DEMO_ACCESS_KEY", demo)
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)


def login(at: AppTest, key: str) -> AppTest:
    at.text_input[0].set_value(key)
    at.button[0].click()
    return at.run()


def test_login_fails_closed_when_keys_are_missing_or_equal(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ADMIN_ACCESS_KEY", raising=False)
    monkeypatch.delenv("DEMO_ACCESS_KEY", raising=False)
    at = AppTest.from_file(str(APP_PATH)).run()
    assert not at.exception
    assert len(at.text_input) == 0
    assert any("Configure as duas chaves" in item.value for item in at.warning)

    set_access_env(monkeypatch, tmp_path / "equal.db", admin="same-test-key", demo="same-test-key")
    at = AppTest.from_file(str(APP_PATH)).run()
    assert not at.exception
    assert len(at.text_input) == 0


def test_demo_login_faq_source_and_logout_clears_session(monkeypatch, tmp_path: Path) -> None:
    set_access_env(monkeypatch, tmp_path / "demo.db")
    at = AppTest.from_file(str(APP_PATH)).run()

    at = login(at, "test-demo-key")
    assert not at.exception
    assert at.session_state["auth_role"].value == "demo"
    assert "test-demo-key" not in str(dict(at.session_state))
    assert "test-admin-key" not in str(dict(at.session_state))
    assert len(at.metric) == 0
    with sqlite3.connect(tmp_path / "demo.db") as connection:
        assert connection.execute("SELECT count(*) FROM products").fetchone()[0] == 65
        assert connection.execute("SELECT order_id FROM orders ORDER BY order_id").fetchall() == [
            ("DEMO-001",),
            ("DEMO-002",),
        ]

    at.chat_input[0].set_value("Qual é o horário da loja?")
    at.run()

    assert not at.exception
    assert any("Segunda a Sexta-feira" in item.value for item in at.markdown)
    assert any("seção 2" in item.value and "página(s) 2" in item.value for item in at.caption)
    assert len(at.metric) == 0

    at.button[0].click().run()
    assert "authenticated" not in at.session_state
    assert "auth_role" not in at.session_state
    assert "messages" not in at.session_state
    assert "session_metrics" not in at.session_state


def test_admin_sees_session_metrics_and_safe_missing_gemini_error(monkeypatch, tmp_path: Path) -> None:
    set_access_env(monkeypatch, tmp_path / "admin.db")
    at = login(AppTest.from_file(str(APP_PATH)).run(), "test-admin-key")
    assert not at.exception

    at.chat_input[0].set_value("Quanto custa o Yamaha C40?")
    at.run()

    assert not at.exception
    assert any("configure GEMINI_API_KEY" in item.value for item in at.markdown)
    metrics = {item.label: item.value for item in at.metric}
    assert metrics["Consultas"] == "1"
    assert metrics["Erros / configuração"] == "1"
    assert "Última latência" in metrics
    assert "Cache FAQ - hits" in metrics
    assert "Cache FAQ - misses" in metrics


def test_chat_history_and_branch_preserve_original(monkeypatch, tmp_path: Path) -> None:
    set_access_env(monkeypatch, tmp_path / "history.db")
    at = login(AppTest.from_file(str(APP_PATH)).run(), "test-admin-key")
    at.chat_input[0].set_value("garantia").run()
    original_id = at.session_state["active_chat"]
    assert len(at.session_state["chats"][original_id]["messages"]) == 2
    next(b for b in at.button if b.label == "Nova conversa").click().run()
    assert at.session_state["active_chat"] != original_id
    next(b for b in at.button if b.label.startswith("garantia - ")).click().run()
    assert at.session_state["active_chat"] == original_id
    next(b for b in at.button if b.label == "Continuar a partir deste turno").click().run()
    assert at.session_state["active_chat"] != original_id
    assert len(at.session_state["chats"][original_id]["messages"]) == 2
    assert len(at.session_state["chats"][at.session_state["active_chat"]]["messages"]) == 2
