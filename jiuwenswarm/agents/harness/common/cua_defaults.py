"""Shared jiuwenswarm defaults and config parsing for the cua (desktop) sub-agent."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Mirrors agent-core's ``create_cua_agent`` default: a perceive-act-verify loop
# re-snapshots before every element action, so tighter budgets run dry mid-task.
DEFAULT_CUA_AGENT_MAX_ITERATIONS = 25

# agent-core default: window snapshots kept in full in the sub-agent context.
# 3 suits two-window tasks; 1 halves the context for single-window tasks.
DEFAULT_CUA_SNAPSHOT_KEEP_LAST_K = 3

_DELIVERY_MODES = ("background", "foreground")


def resolve_cua_factory_options(sub_cfg: Any) -> dict[str, Any]:
    """Map ``react.subagents.cua_agent`` knobs onto ``build_cua_agent_config`` kwargs.

    agent-core raises ``ValueError`` at config time on a bad value, which would
    abort the whole agent build; invalid entries are therefore dropped here
    with a warning and the agent-core default applies.
    """
    cfg = sub_cfg if isinstance(sub_cfg, dict) else {}
    options: dict[str, Any] = {}

    raw_k = cfg.get("snapshot_keep_last_k")
    if raw_k is not None:
        keep = None
        if isinstance(raw_k, int) and not isinstance(raw_k, bool):
            keep = raw_k
        elif isinstance(raw_k, str) and raw_k.strip().isdigit():
            keep = int(raw_k.strip())
        if keep is not None and keep >= 1:
            options["cua_snapshot_keep_last_k"] = keep
        else:
            logger.warning(
                "[cua_agent] ignoring snapshot_keep_last_k=%r (need an int >= 1); using %s",
                raw_k, DEFAULT_CUA_SNAPSHOT_KEEP_LAST_K,
            )

    raw_pause = cfg.get("pause_on_user_input")
    if raw_pause is not None:
        if isinstance(raw_pause, bool):
            options["cua_pause_on_user_input"] = raw_pause
        elif isinstance(raw_pause, str) and raw_pause.strip().lower() in ("true", "false"):
            options["cua_pause_on_user_input"] = raw_pause.strip().lower() == "true"
        else:
            logger.warning(
                "[cua_agent] ignoring pause_on_user_input=%r (need true/false); keeping the default (on)",
                raw_pause,
            )

    raw_mode = cfg.get("delivery_mode")
    if raw_mode is not None:
        mode = str(raw_mode).strip().lower()
        if mode in _DELIVERY_MODES:
            options["cua_delivery_mode"] = mode
        elif mode:
            logger.warning(
                "[cua_agent] ignoring delivery_mode=%r (expected one of %s); leaving unpinned",
                raw_mode, _DELIVERY_MODES,
            )

    return options


__all__ = [
    "DEFAULT_CUA_AGENT_MAX_ITERATIONS",
    "DEFAULT_CUA_SNAPSHOT_KEEP_LAST_K",
    "resolve_cua_factory_options",
]
