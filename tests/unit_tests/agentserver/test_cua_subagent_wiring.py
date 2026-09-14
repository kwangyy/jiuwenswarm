# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Wiring tests for the cua (desktop automation) sub-agent.

cua_agent drives the host desktop through the cua-driver MCP server, so it is
opt-in everywhere: only an explicit ``react.subagents.cua_agent.enabled: true``
mounts it, in the single-agent, code and team paths alike. It must also stay on
the synchronous ``task_tool`` when the persistent subagent runtime is on,
because agent-core's TaskTool owns its explicit resume / ``cua_result`` handling.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from openjiuwen.core.single_agent.schema.agent_card import AgentCard
from openjiuwen.harness.schema.deep_agent_spec import SubAgentConfig
from openjiuwen.harness.subagents.cua_agent import (
    CUA_AGENT_FACTORY_NAME,
    DEFAULT_CUA_AGENT_DESCRIPTION,
)

from jiuwenswarm.agents.harness.common.cua_defaults import (
    CUA_AGENT_CARD_DESCRIPTION,
    DEFAULT_CUA_AGENT_MAX_ITERATIONS,
    DEFAULT_CUA_SNAPSHOT_KEEP_LAST_K,
    resolve_cua_factory_options,
)
from jiuwenswarm.agents.harness.common.prompt.cua_task_prompt import (
    build_cua_task_prompt,
)
from jiuwenswarm.agents.harness.common.rails.browser_task_prompt_rail import (
    BrowserTaskPromptRail,
)
from jiuwenswarm.agents.swarm import registry
from jiuwenswarm.agents.swarm.config_specs import build_member_subagent_specs
from jiuwenswarm.agents.swarm.context import SwarmBuildContext
from jiuwenswarm.agents.swarm.providers.code_subagents import (
    SWARM_CUA_AGENT,
    build_swarm_cua_agent,
)
from jiuwenswarm.agents.swarm.registry import register_swarm_providers
from jiuwenswarm.server.runtime.agent_adapter.interface_code import (
    JiuwenSwarmCodeAdapter,
)
from jiuwenswarm.server.runtime.agent_adapter.interface_deep import (
    JiuWenSwarmDeepAdapter,
)


def _names(subagents) -> list[str]:
    return [spec.agent_card.name for spec in (subagents or [])]


def _cua_spec(subagents):
    return next(spec for spec in subagents if spec.agent_card.name == "cua_agent")


# ── single-agent (agent mode) path ───────────────────────────────────────


def _deep_adapter(monkeypatch, tmp_path) -> JiuWenSwarmDeepAdapter:
    adapter = JiuWenSwarmDeepAdapter()
    adapter._workspace_dir = str(tmp_path)
    adapter._sys_operation = MagicMock()
    monkeypatch.setattr(adapter, "_browser_runtime_enabled", lambda: False)
    return adapter


def test_single_agent_mounts_cua_agent_only_when_explicitly_enabled(monkeypatch, tmp_path):
    adapter = _deep_adapter(monkeypatch, tmp_path)

    subagents, _ = adapter._build_configured_subagents(
        MagicMock(),
        {"subagents": {"cua_agent": {"enabled": True, "max_iterations": 7}}},
        {},
    )

    spec = _cua_spec(subagents)
    assert spec.factory_name == CUA_AGENT_FACTORY_NAME
    assert spec.max_iterations == 7
    # Shares the parent's filesystem boundary like every other built-in spec.
    assert spec.sys_operation is adapter._sys_operation
    assert spec.workspace == str(tmp_path)


def test_single_agent_skips_cua_agent_when_absent_or_disabled(monkeypatch, tmp_path):
    adapter = _deep_adapter(monkeypatch, tmp_path)

    absent, _ = adapter._build_configured_subagents(MagicMock(), {"subagents": {}}, {})
    disabled, _ = adapter._build_configured_subagents(
        MagicMock(), {"subagents": {"cua_agent": {"enabled": False}}}, {}
    )
    # An entry with only max_iterations must not count as opt-in.
    params_only, _ = adapter._build_configured_subagents(
        MagicMock(), {"subagents": {"cua_agent": {"max_iterations": 7}}}, {}
    )

    for subagents in (absent, disabled, params_only):
        assert "cua_agent" not in _names(subagents)


def test_single_agent_cua_default_iteration_budget(monkeypatch, tmp_path):
    adapter = _deep_adapter(monkeypatch, tmp_path)

    subagents, _ = adapter._build_configured_subagents(
        MagicMock(), {"subagents": {"cua_agent": {"enabled": True}}}, {}
    )

    assert _cua_spec(subagents).max_iterations == DEFAULT_CUA_AGENT_MAX_ITERATIONS


# ── code mode path ───────────────────────────────────────────────────────


def _code_adapter(monkeypatch, tmp_path) -> JiuwenSwarmCodeAdapter:
    adapter = JiuwenSwarmCodeAdapter()
    adapter._workspace_dir = str(tmp_path)
    adapter._project_dir = str(tmp_path)
    adapter._coding_memory_rail = None
    adapter._sys_operation = MagicMock()
    monkeypatch.setattr(adapter, "_browser_runtime_enabled", lambda: False)
    return adapter


def test_code_mode_mounts_cua_agent_when_enabled(monkeypatch, tmp_path):
    adapter = _code_adapter(monkeypatch, tmp_path)

    subagents, _ = adapter._build_configured_subagents(
        MagicMock(), {"subagents": {"cua_agent": {"enabled": True}}}, {}
    )

    spec = _cua_spec(subagents)
    assert spec.factory_name == CUA_AGENT_FACTORY_NAME
    assert spec.sys_operation is adapter._sys_operation
    # Code mode never lets sub-agents create their own workspace.
    assert spec.factory_kwargs["auto_create_workspace"] is False


def test_code_mode_skips_cua_agent_when_absent(monkeypatch, tmp_path):
    adapter = _code_adapter(monkeypatch, tmp_path)

    subagents, _ = adapter._build_configured_subagents(MagicMock(), {"subagents": {}}, {})

    assert "cua_agent" not in _names(subagents)


# ── swarm / team path ────────────────────────────────────────────────────


def test_team_specs_mount_cua_agent_in_every_mode_when_enabled():
    config = {"react": {"subagents": {"cua_agent": {"enabled": True, "max_iterations": 9}}}}

    for mode in ("code.team", "team"):
        specs = build_member_subagent_specs(config, mode, "leader")
        cua = [s for s in specs if s.factory_name == registry.SWARM_CUA_AGENT]
        assert len(cua) == 1, mode
        assert cua[0].agent_card.name == "cua_agent"
        assert cua[0].factory_kwargs["max_iterations"] == 9


def test_team_specs_skip_cua_agent_when_absent_or_disabled():
    for config in (
        {},
        {"react": {"subagents": {"cua_agent": {"enabled": False}}}},
        {"react": {"subagents": {"cua_agent": {"max_iterations": 9}}}},
    ):
        specs = build_member_subagent_specs(config, "code.team", "leader")
        assert all(s.factory_name != registry.SWARM_CUA_AGENT for s in specs)


def test_team_specs_cua_default_iteration_budget():
    specs = build_member_subagent_specs(
        {"react": {"subagents": {"cua_agent": {"enabled": True}}}}, "code.team", "leader"
    )
    cua = next(s for s in specs if s.factory_name == SWARM_CUA_AGENT)

    assert cua.factory_kwargs["max_iterations"] == DEFAULT_CUA_AGENT_MAX_ITERATIONS


def test_swarm_cua_provider_skips_without_parent_model():
    register_swarm_providers()
    ctx = SwarmBuildContext(
        mode="code.team", role="leader", member_name="leader", session_id="s", config={}
    )

    assert build_swarm_cua_agent({}, ctx) is None


def test_swarm_cua_provider_builds_cua_factory_spec():
    register_swarm_providers()
    ctx = SwarmBuildContext(
        mode="code.team", role="leader", member_name="leader", session_id="s", config={}
    )
    ctx.extras["_parent_model"] = MagicMock()

    spec = build_swarm_cua_agent({"max_iterations": 11}, ctx)

    assert spec is not None
    assert spec.factory_name == CUA_AGENT_FACTORY_NAME
    assert spec.agent_card.name == "cua_agent"
    assert spec.max_iterations == 11
    # agent-core's cua_* kwargs survive; the swarm only adds the workspace flag.
    assert spec.factory_kwargs["auto_create_workspace"] is False
    assert "cua_capabilities" in spec.factory_kwargs


# ── snapshot retention / delivery mode knobs ─────────────────────────────


def test_cua_knobs_map_onto_agent_core_factory_kwargs():
    assert resolve_cua_factory_options(
        {"snapshot_keep_last_k": 1, "delivery_mode": "Foreground"}
    ) == {"cua_snapshot_keep_last_k": 1, "cua_delivery_mode": "foreground"}
    # Absent knobs leave agent-core's defaults in charge.
    assert resolve_cua_factory_options({"enabled": True}) == {}


def test_pause_on_user_input_knob_maps_and_validates():
    assert resolve_cua_factory_options({"pause_on_user_input": False}) == {"cua_pause_on_user_input": False}
    assert resolve_cua_factory_options({"pause_on_user_input": "true"}) == {"cua_pause_on_user_input": True}
    assert resolve_cua_factory_options({"pause_on_user_input": "maybe"}) == {}


def test_team_specs_carry_pause_on_user_input_to_the_provider():
    register_swarm_providers()
    specs = build_member_subagent_specs(
        {"react": {"subagents": {"cua_agent": {"enabled": True, "pause_on_user_input": False}}}},
        "code.team",
        "leader",
    )
    cua = next(s for s in specs if s.factory_name == SWARM_CUA_AGENT)
    assert cua.factory_kwargs["pause_on_user_input"] is False

    ctx = SwarmBuildContext(
        mode="code.team", role="leader", member_name="leader", session_id="s", config={}
    )
    ctx.extras["_parent_model"] = MagicMock()
    spec = build_swarm_cua_agent(dict(cua.factory_kwargs), ctx)
    assert spec.factory_kwargs["cua_pause_on_user_input"] is False


def test_invalid_cua_knobs_are_dropped_instead_of_aborting_the_build():
    # agent-core raises ValueError on these; the adapter must not pass them on.
    assert resolve_cua_factory_options(
        {"snapshot_keep_last_k": 0, "delivery_mode": "sideways"}
    ) == {}
    assert resolve_cua_factory_options({"snapshot_keep_last_k": True}) == {}


def test_single_agent_passes_cua_knobs_to_the_factory(monkeypatch, tmp_path):
    adapter = _deep_adapter(monkeypatch, tmp_path)

    subagents, _ = adapter._build_configured_subagents(
        MagicMock(),
        {"subagents": {"cua_agent": {"enabled": True, "snapshot_keep_last_k": 1, "delivery_mode": "foreground"}}},
        {},
    )

    kwargs = _cua_spec(subagents).factory_kwargs
    assert kwargs["cua_snapshot_keep_last_k"] == 1
    assert kwargs["cua_delivery_mode"] == "foreground"


def test_single_agent_cua_knob_defaults(monkeypatch, tmp_path):
    adapter = _deep_adapter(monkeypatch, tmp_path)

    subagents, _ = adapter._build_configured_subagents(
        MagicMock(), {"subagents": {"cua_agent": {"enabled": True}}}, {}
    )

    kwargs = _cua_spec(subagents).factory_kwargs
    assert kwargs["cua_snapshot_keep_last_k"] == DEFAULT_CUA_SNAPSHOT_KEEP_LAST_K
    assert kwargs["cua_delivery_mode"] is None


def test_team_specs_carry_cua_knobs_to_the_provider():
    register_swarm_providers()
    specs = build_member_subagent_specs(
        {"react": {"subagents": {"cua_agent": {"enabled": True, "snapshot_keep_last_k": 1, "delivery_mode": "foreground"}}}},
        "code.team",
        "leader",
    )
    cua = next(s for s in specs if s.factory_name == SWARM_CUA_AGENT)
    assert cua.factory_kwargs["snapshot_keep_last_k"] == 1
    assert cua.factory_kwargs["delivery_mode"] == "foreground"

    ctx = SwarmBuildContext(
        mode="code.team", role="leader", member_name="leader", session_id="s", config={}
    )
    ctx.extras["_parent_model"] = MagicMock()
    spec = build_swarm_cua_agent(dict(cua.factory_kwargs), ctx)
    assert spec.factory_kwargs["cua_snapshot_keep_last_k"] == 1
    assert spec.factory_kwargs["cua_delivery_mode"] == "foreground"


# ── synchronous delegation ───────────────────────────────────────────────


def test_cua_agent_stays_synchronous_under_subagent_runtime():
    rail = BrowserTaskPromptRail(enable_subagent_runtime=True)

    assert "cua_agent" in rail.synchronous_subagent_types
    assert "browser_agent" in rail.synchronous_subagent_types


# ── parent-side routing prompt ───────────────────────────────────────────
#
# The generic task-tool prompt tells the model to skip the task tool for
# tasks "not related to the subagent descriptions", and never says when a
# desktop task should be delegated. Without an explicit routing section the
# model handles GUI requests itself (or refuses), so cua_agent never fires.


def _rail_agent(*names: str):
    subagents = [
        SubAgentConfig(agent_card=AgentCard(name=n, description=n), system_prompt=n)
        for n in names
    ]
    return SimpleNamespace(agent=SimpleNamespace(deep_config=SimpleNamespace(subagents=subagents)))


def test_desktop_routing_rules_injected_only_when_cua_agent_is_mounted():
    rail = BrowserTaskPromptRail()

    text = rail._task_prompt_extension(_rail_agent("cua_agent"), "en")

    assert text is not None
    assert "## Desktop Capability Routing Rules" in text
    assert 'set `subagent_type` to `"cua_agent"`' in text
    assert "Do not use `subagent_spawn` for cua_agent" in text
    # Overrides the generic "only delegate when asked" rule, like the browser one.
    assert "overrides generic subagent rules" in text
    # No browser text and no browser-vs-desktop choice when only cua is mounted.
    assert "Browser Capability Routing Rules" not in text
    assert "Choosing between browser and desktop" not in text
    assert "桌面能力路由规则" in build_cua_task_prompt("cn")


def test_no_routing_rules_without_browser_or_cua():
    rail = BrowserTaskPromptRail()

    assert rail._task_prompt_extension(_rail_agent("explore_agent"), "en") is None
    assert rail._task_prompt_extension(_rail_agent(), "en") is None


def test_browser_only_keeps_the_original_browser_section():
    rail = BrowserTaskPromptRail()

    text = rail._task_prompt_extension(_rail_agent("browser_agent"), "en")

    assert text is not None
    assert "## Browser Capability Routing Rules" in text
    assert "Desktop Capability Routing Rules" not in text


def test_both_mounted_adds_a_choice_rule_after_both_sections():
    rail = BrowserTaskPromptRail()

    text = rail._task_prompt_extension(_rail_agent("browser_agent", "cua_agent"), "en")

    assert text is not None
    browser_at = text.index("## Browser Capability Routing Rules")
    desktop_at = text.index("## Desktop Capability Routing Rules")
    choice_at = text.index("### Choosing between browser and desktop")
    assert browser_at < desktop_at < choice_at
    assert "use `browser_agent`" in text
    assert "use `cua_agent`" in text
    assert "浏览器与桌面能力的选择" in build_cua_task_prompt("cn", browser_available=True)


# ── card description ─────────────────────────────────────────────────────
#
# The card description is the only per-subagent text in the "Available
# subagent types" list, so it must name example desktop tasks rather than
# agent-core's one-liner.


def test_single_agent_cua_card_names_example_desktop_tasks(monkeypatch, tmp_path):
    adapter = _deep_adapter(monkeypatch, tmp_path)

    subagents, _ = adapter._build_configured_subagents(
        MagicMock(), {"subagents": {"cua_agent": {"enabled": True}}}, {}
    )

    desc = _cua_spec(subagents).agent_card.description
    assert desc in CUA_AGENT_CARD_DESCRIPTION.values()
    assert desc not in DEFAULT_CUA_AGENT_DESCRIPTION.values()


def test_code_mode_cua_card_names_example_desktop_tasks(monkeypatch, tmp_path):
    adapter = _code_adapter(monkeypatch, tmp_path)

    subagents, _ = adapter._build_configured_subagents(
        MagicMock(), {"subagents": {"cua_agent": {"enabled": True}}}, {}
    )

    desc = _cua_spec(subagents).agent_card.description
    assert desc in CUA_AGENT_CARD_DESCRIPTION.values()
    assert desc not in DEFAULT_CUA_AGENT_DESCRIPTION.values()


def test_cua_card_description_names_example_tasks_in_both_languages():
    assert "launching apps" in CUA_AGENT_CARD_DESCRIPTION["en"]
    assert "native windows" in CUA_AGENT_CARD_DESCRIPTION["en"]
    assert "启动应用" in CUA_AGENT_CARD_DESCRIPTION["cn"]


def test_swarm_cua_provider_uses_task_oriented_card():
    register_swarm_providers()
    ctx = SwarmBuildContext(
        mode="code.team", role="leader", member_name="leader", session_id="s", config={}
    )
    ctx.extras["_parent_model"] = MagicMock()

    spec = build_swarm_cua_agent({"language": "en"}, ctx)

    assert spec is not None
    assert spec.agent_card.description == CUA_AGENT_CARD_DESCRIPTION["en"]
