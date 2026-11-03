"""Fail-closed authentication for the two application roles."""

from __future__ import annotations

import hmac
from collections.abc import Mapping
from enum import Enum


class AppRole(str, Enum):
    ADMIN = "admin"
    DEMO = "demo"


ADMIN_KEY_NAME = "ADMIN_ACCESS_KEY"
DEMO_KEY_NAME = "DEMO_ACCESS_KEY"


def authenticate(candidate: str, configured_keys: Mapping[str, object]) -> AppRole | None:
    """Return a role only when both distinct configured secrets are present."""
    admin_key = configured_keys.get(ADMIN_KEY_NAME)
    demo_key = configured_keys.get(DEMO_KEY_NAME)
    if (
        not isinstance(candidate, str)
        or not isinstance(admin_key, str)
        or not isinstance(demo_key, str)
        or not candidate
        or not admin_key
        or not demo_key
        or admin_key == demo_key
    ):
        return None

    candidate_bytes = candidate.encode("utf-8")
    admin_match = hmac.compare_digest(candidate_bytes, admin_key.encode("utf-8"))
    demo_match = hmac.compare_digest(candidate_bytes, demo_key.encode("utf-8"))
    if admin_match:
        return AppRole.ADMIN
    if demo_match:
        return AppRole.DEMO
    return None
