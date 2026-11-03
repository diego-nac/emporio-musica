"""Session helpers; application role and order identity remain separate."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping

from src.data.repositories import DemoIdentity
from src.security.auth import AppRole, authenticate


# This ID is a backend fixture selector, never supplied by the model or login form.
_DEMO_CUSTOMER_ID = "3"


def authenticate_session(
    session: MutableMapping[str, object],
    candidate: str,
    configured_keys: Mapping[str, object],
) -> AppRole | None:
    role = authenticate(candidate, configured_keys)
    if role is not None:
        session["auth_role"] = role
        session["authenticated"] = True
    return role


def can_view_metrics(role: object) -> bool:
    return role == AppRole.ADMIN or role == AppRole.ADMIN.value


def get_demo_identity() -> DemoIdentity:
    """Return the fixed backend demo identity independently of the app role."""
    return DemoIdentity(customer_id=_DEMO_CUSTOMER_ID)


def clear_session(session: MutableMapping[str, object]) -> None:
    """Remove all app state on logout, including chat and metrics context."""
    session.clear()
