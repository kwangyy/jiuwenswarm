"""Shared jiuwenswarm defaults and config parsing for the cua (desktop) sub-agent."""

from __future__ import annotations

import logging
from typing import Any

from openjiuwen.core.single_agent.schema.agent_card import AgentCard

logger = logging.getLogger(__name__)

# Mirrors agent-core's ``create_cua_agent`` default: a perceive-act-verify loop
# re-snapshots before every element action, so tighter budgets run dry mid-task.
DEFAULT_CUA_AGENT_MAX_ITERATIONS = 25

# agent-core default: window snapshots kept in full in the sub-agent context.
# 3 suits two-window tasks; 1 halves the context for single-window tasks.
DEFAULT_CUA_SNAPSHOT_KEEP_LAST_K = 3

_DELIVERY_MODES = ("background", "foreground")

# Replaces agent-core's one-line card description. The parent's task-tool
# prompt tells the model to skip delegation for tasks "not related to the
# subagent descriptions", so the card has to name the kinds of tasks it takes.
CUA_AGENT_CARD_DESCRIPTION = {
    "cn": (
        "专用桌面子代理，通过 cua-driver MCP 工具操作本机应用窗口：启动应用、"
        "在原生窗口（Office、IDE、聊天客户端、系统对话框等）内点击/输入/按快捷键/滚动、"
        "读取窗口当前内容、查看已打开的应用与窗口。凡是要在本机图形界面上执行的操作，"
        "都应交给它，而不是自行用脚本驱动界面。"
    ),
    "en": (
        "Dedicated desktop subagent that controls host application windows through "
        "cua-driver MCP tools: launching apps, clicking / typing / pressing hotkeys / "
        "scrolling inside native windows (Office, IDEs, chat clients, system dialogs), "
        "reading what a window currently shows, and listing open apps and windows. "
        "Use it for any action on this machine's GUI instead of scripting the UI yourself."
    ),
}


def build_cua_agent_card(language: str = "cn") -> AgentCard:
    """Return the ``cua_agent`` card with the task-oriented description."""

    return AgentCard(
        name="cua_agent",
        description=CUA_AGENT_CARD_DESCRIPTION.get(language, CUA_AGENT_CARD_DESCRIPTION["cn"]),
    )


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
    "CUA_AGENT_CARD_DESCRIPTION",
    "DEFAULT_CUA_AGENT_MAX_ITERATIONS",
    "DEFAULT_CUA_SNAPSHOT_KEEP_LAST_K",
    "build_cua_agent_card",
    "resolve_cua_factory_options",
]
