"""Helpers shared by staff console pages."""
from __future__ import annotations

from fastapi import Request

from ... import auth, config_store, fees as fee_mod, payments
from ...web import render


def staff_render(request: Request, template: str, conn, user: dict, **ctx):
    policy = config_store.get(conn, "payments")
    try:
        test_mode = payments.get(policy.get("processor") or "test").is_test
    except KeyError:
        test_mode = False
    return render(request, template, conn, user=user, can=lambda *roles: auth.has_role(user, *roles),
                  test_mode=test_mode, unconfirmed_fees=fee_mod.unconfirmed_count(conn), **ctx)
