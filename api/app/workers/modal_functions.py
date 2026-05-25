"""Helpers for resolving Modal function handles from worker code."""

from __future__ import annotations

from typing import Any


def get_modal_function(name: str) -> Any:
    """Return a Modal function handle.

    In a deployed Modal app, ``modal_app.py`` injects direct handles for sibling
    functions so workers do not need workspace-level lookup permissions. Local
    callers still fall back to ``Function.from_name``.
    """
    try:
        from app.modal_handles import MODAL_FUNCTIONS  # type: ignore
    except Exception:
        MODAL_FUNCTIONS = {}

    function = MODAL_FUNCTIONS.get(name)
    if function is not None:
        return function

    import modal

    return modal.Function.from_name("lenai-platform", name)
