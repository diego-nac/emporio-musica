"""Session helpers; application role and order identity remain separate."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping

from src.data.repositories import DemoIdentity
from src.security.auth import AppRole, authenticate


                                                                                   
_DEMO_PROFILES = {
    "Cliente Demonstração": DemoIdentity(customer_id="3"),
    "Visitante sem pedidos": DemoIdentity(customer_id="__demo_no_orders__"),
}


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


def demo_profile_labels() -> tuple[str, ...]:
    return tuple(_DEMO_PROFILES)


def get_demo_identity(profile: str = "Cliente Demonstração") -> DemoIdentity:
    """Resolve an allowlisted UI label to a backend identity; never accept a raw ID."""
    try:
        return _DEMO_PROFILES[profile]
    except KeyError as exc:
        raise ValueError("unknown demonstration profile") from exc


def clear_session(session: MutableMapping[str, object]) -> None:
    """Remove all app state on logout, including chat and metrics context."""
    session.clear()
