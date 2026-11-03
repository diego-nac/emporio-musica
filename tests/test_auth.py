from src.data.repositories import DemoIdentity
from src.domain.session import (
    AppRole,
    authenticate_session,
    can_view_metrics,
    clear_session,
    get_demo_identity,
)
from src.security.auth import authenticate


def test_authentication_fails_closed_for_missing_or_equal_keys() -> None:
    assert authenticate("admin-secret", {}) is None
    assert authenticate("admin-secret", {"ADMIN_ACCESS_KEY": "admin-secret"}) is None
    assert (
        authenticate(
            "same",
            {"ADMIN_ACCESS_KEY": "same", "DEMO_ACCESS_KEY": "same"},
        )
        is None
    )


def test_session_login_roles_and_fixed_separate_demo_identity() -> None:
    keys = {"ADMIN_ACCESS_KEY": "admin-ação", "DEMO_ACCESS_KEY": "demo-ação"}
    admin_session: dict[str, object] = {}
    demo_session: dict[str, object] = {}

    assert authenticate_session(admin_session, "admin-ação", keys) is AppRole.ADMIN
    assert authenticate_session(demo_session, "demo-ação", keys) is AppRole.DEMO
    assert can_view_metrics(admin_session["auth_role"]) is True
    assert can_view_metrics(demo_session["auth_role"]) is False
    assert "admin-ação" not in admin_session.values()
    assert get_demo_identity() == DemoIdentity(customer_id="3")
    assert get_demo_identity() == get_demo_identity()


def test_failed_login_does_not_change_session_and_logout_clears_all() -> None:
    session: dict[str, object] = {"messages": ["old"], "tool_context": "private"}
    keys = {"ADMIN_ACCESS_KEY": "admin-key", "DEMO_ACCESS_KEY": "demo-key"}

    assert authenticate_session(session, "wrong", keys) is None
    assert session == {"messages": ["old"], "tool_context": "private"}
    assert authenticate_session(session, "demo-key", keys) is AppRole.DEMO
    assert "demo-key" not in session.values()
    clear_session(session)
    assert session == {}
