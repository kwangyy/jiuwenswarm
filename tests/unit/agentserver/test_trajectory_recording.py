"""Trajectory-recording wiring: config gating, shared recorder, fail-safety.

Recording must be strictly opt-in (a stock install has no config block and
must pay zero cost), every agent in the process must land in ONE recorder
(separate recorders would fragment the on-disk layout and double-register
tracer handlers), and a recording failure must never break agent
construction — trajectory capture is observability, not a dependency.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from jiuwenswarm.server.runtime import trajectory_recording as tr

pytest.importorskip(
    "openjiuwen.core.session.trajectory",
    reason="installed openjiuwen lacks the trajectory module (trajectory-observability branch)",
)


def _fake_agent(name: str) -> SimpleNamespace:
    return SimpleNamespace(card=SimpleNamespace(name=name, id=f"{name}-id"))


@pytest.fixture(autouse=True)
def _isolated_recorder(monkeypatch):
    """Reset module state and unregister tracer handlers after each test."""
    monkeypatch.setattr(tr, "_recorder", None)
    monkeypatch.setattr(tr, "_unavailable_warned", False)
    yield
    asyncio.run(tr.close_trajectory_recorder())


def _set_config(monkeypatch, block):
    import jiuwenswarm.common.config as config_mod

    monkeypatch.setattr(config_mod, "get_config", lambda: {"trajectory_recording": block})


def test_disabled_by_default_creates_nothing(monkeypatch):
    import jiuwenswarm.common.config as config_mod

    monkeypatch.setattr(config_mod, "get_config", lambda: {})
    tr.maybe_attach_trajectory_recorder(_fake_agent("main"))
    assert tr._recorder is None


def test_enabled_attaches_all_agents_to_one_recorder(monkeypatch, tmp_path):
    _set_config(monkeypatch, {"enabled": True, "output_dir": str(tmp_path / "traj")})
    tr.maybe_attach_trajectory_recorder(_fake_agent("main"))
    first = tr._recorder
    assert first is not None
    assert str(first.root) == str(tmp_path / "traj")

    tr.maybe_attach_trajectory_recorder(_fake_agent("code"))
    assert tr._recorder is first


def test_default_output_dir_is_sibling_of_agent_logs(monkeypatch, tmp_path):
    """Trajectories belong with the other run diagnostics: agent/.trajectories
    next to agent/.logs, not a top-level workspace directory."""
    import jiuwenswarm.common.utils as utils

    monkeypatch.setattr(utils, "get_agent_root_dir", lambda: tmp_path / "agent")
    _set_config(monkeypatch, {"enabled": True})
    tr.maybe_attach_trajectory_recorder(_fake_agent("main"))
    assert str(tr._recorder.root) == str(tmp_path / "agent" / ".trajectories")


def test_heartbeat_sessions_excluded_by_default(monkeypatch, tmp_path):
    """Gateway heartbeat probes run full turns through the recorded main
    agent under heartbeat_* session ids — without a default exclusion every
    tick would land a trajectory folder next to real chats."""
    _set_config(monkeypatch, {"enabled": True, "output_dir": str(tmp_path / "traj")})
    tr.maybe_attach_trajectory_recorder(_fake_agent("main"))
    assert tr._recorder._config.exclude_session_prefixes == ("heartbeat_",)


def test_exclude_prefixes_config_override(monkeypatch, tmp_path):
    _set_config(
        monkeypatch,
        {"enabled": True, "output_dir": str(tmp_path / "traj"), "exclude_session_prefixes": []},
    )
    tr.maybe_attach_trajectory_recorder(_fake_agent("main"))
    assert tr._recorder._config.exclude_session_prefixes == ()


def test_sync_pauses_recorder_when_config_turns_off(monkeypatch, tmp_path):
    """The frontend toggle writes config.yaml; the per-request sync must
    silence an already-attached recorder without a server restart."""
    _set_config(monkeypatch, {"enabled": True, "output_dir": str(tmp_path / "traj")})
    tr.maybe_attach_trajectory_recorder(_fake_agent("main"))
    assert tr._recorder._collector.recording_enabled is True

    _set_config(monkeypatch, {"enabled": False})
    tr.sync_trajectory_recording_enabled()
    assert tr._recorder._collector.recording_enabled is False

    _set_config(monkeypatch, {"enabled": True})
    tr.sync_trajectory_recording_enabled()
    assert tr._recorder._collector.recording_enabled is True


def test_sync_without_recorder_is_a_noop(monkeypatch):
    _set_config(monkeypatch, {"enabled": True})
    tr.sync_trajectory_recording_enabled()
    assert tr._recorder is None


def test_attach_clears_stale_pause(monkeypatch, tmp_path):
    """Toggle off → new agent built while off is not attached; toggle back on
    → the next attach must clear the pause or it would record nothing."""
    _set_config(monkeypatch, {"enabled": True, "output_dir": str(tmp_path / "traj")})
    tr.maybe_attach_trajectory_recorder(_fake_agent("main"))
    tr._recorder.set_enabled(False)
    tr.maybe_attach_trajectory_recorder(_fake_agent("code"))
    assert tr._recorder._collector.recording_enabled is True


def test_attach_failure_does_not_raise(monkeypatch, tmp_path):
    """An agent without card name/id is rejected by the recorder — the
    wiring must swallow that so create_instance still succeeds."""
    _set_config(monkeypatch, {"enabled": True, "output_dir": str(tmp_path / "traj")})
    cardless = SimpleNamespace(card=SimpleNamespace(name=None, id=None))
    tr.maybe_attach_trajectory_recorder(cardless)


def test_close_resets_state_for_clean_shutdown(monkeypatch, tmp_path):
    _set_config(monkeypatch, {"enabled": True, "output_dir": str(tmp_path / "traj")})
    tr.maybe_attach_trajectory_recorder(_fake_agent("main"))
    assert tr._recorder is not None
    asyncio.run(tr.close_trajectory_recorder())
    assert tr._recorder is None
