# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Process-wide openjiuwen trajectory recording.

Off by default; enabled via the ``trajectory_recording`` config block:

    trajectory_recording:
      enabled: true
      output_dir: ""                  # default ~/.jiuwenswarm/agent/.trajectories
      record_llm_input_digest: false
      exclude_session_prefixes: ["heartbeat_"]   # the default; [] records everything

One recorder is shared by every agent constructed in this process
(``TrajectoryRecorder.attach`` is idempotent per agent identity). Attach must
happen after the agent is built and before its first session is created;
each run's trajectory finalizes on its own when the owning session closes,
so the recorder stays open for the server's lifetime and ``close`` at
shutdown only flushes still-open runs.

``openjiuwen.core.session.trajectory`` only exists on the
trajectory-observability branch of agent-core: on releases without it,
recording stays off and enabling the config logs one warning. Recording is
process-local — sessions in spawned child processes or behind remote agents
are not captured.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_RECORDER_SESSION_ID = "agentserver"

_recorder: Any = None
_unavailable_warned = False


def _load_settings() -> dict[str, Any]:
    """Best-effort read of the ``trajectory_recording`` config block."""
    try:
        from jiuwenswarm.common.config import get_config

        cfg = get_config().get("trajectory_recording", {})
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def _default_output_dir() -> str:
    # Sibling of agent/.logs so all run diagnostics live under agent/.
    from jiuwenswarm.common.utils import get_agent_root_dir

    return str(get_agent_root_dir() / ".trajectories")


def sync_trajectory_recording_enabled() -> None:
    """Re-read the config's ``enabled`` flag and pause/resume the recorder.

    Called on the request path so a frontend toggle (the Gateway writes
    config.yaml; ``get_config`` re-reads on file change) takes effect without
    a server restart. Turning OFF silences even sessions that are already
    recording. Turning back ON resumes agents attached earlier in this
    process; when the server started with recording off, no recorder exists
    yet and recording starts with the next newly built agent instead (agents
    attach at construction — see ``maybe_attach_trajectory_recorder``).
    Never raises.
    """
    if _recorder is None:
        return
    try:
        _recorder.set_enabled(bool(_load_settings().get("enabled", False)))
    except Exception as exc:
        logger.warning("[TrajectoryRecording] enabled-state sync failed: %s", exc)


def maybe_attach_trajectory_recorder(agent: Any) -> None:
    """Attach *agent* to the process-wide recorder when recording is enabled.

    No-op when the config block is absent/disabled or the installed
    openjiuwen has no trajectory module. Never raises: recording must not
    break agent construction.
    """
    global _recorder, _unavailable_warned
    settings = _load_settings()
    if not settings.get("enabled", False):
        return
    try:
        from openjiuwen.core.session.trajectory import TrajectoryConfig, TrajectoryRecorder
    except ImportError:
        if not _unavailable_warned:
            _unavailable_warned = True
            logger.warning(
                "[TrajectoryRecording] enabled in config but the installed openjiuwen "
                "has no core.session.trajectory module; recording stays off"
            )
        return
    try:
        if _recorder is None:
            exclude = settings.get("exclude_session_prefixes")
            if exclude is None:
                # Gateway heartbeat probes run full turns through the main
                # agent under heartbeat_* session ids (gateway/heartbeat);
                # recording them would clutter the output with system turns.
                exclude = ["heartbeat_"]
            config = TrajectoryConfig(
                root=settings.get("output_dir") or _default_output_dir(),
                # Long-lived host: many agent sessions per process, group runs
                # per owning agent session instead of one flat directory.
                group_by_agent_session=True,
                record_llm_input_digest=bool(settings.get("record_llm_input_digest", False)),
                exclude_session_prefixes=tuple(str(p) for p in exclude),
            )
            _recorder = TrajectoryRecorder(_RECORDER_SESSION_ID, config)
            logger.info("[TrajectoryRecording] recording enabled, root=%s", _recorder.root)
        _recorder.attach(agent)
        # The config says enabled — clear any pause left by a runtime toggle,
        # or this newly attached agent would record nothing.
        _recorder.set_enabled(True)
    except Exception as exc:
        logger.warning("[TrajectoryRecording] attach failed: %s", exc)


async def close_trajectory_recorder() -> None:
    """Flush and close the process-wide recorder at server shutdown."""
    global _recorder
    if _recorder is None:
        return
    recorder, _recorder = _recorder, None
    try:
        await recorder.close()
    except Exception as exc:
        logger.warning("[TrajectoryRecording] close failed: %s", exc)
