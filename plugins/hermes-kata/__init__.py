"""Hermes plugin loader entrypoint (`plugin.yaml`'s package).

Wires the jobs this build ships (spec §1, §2, §4, §6, §8) into a live
`PluginContext`: identity binding (`pre_gateway_dispatch`), the `tools.json`
tool catalog, the mcq/msq `clarify`-rendering system-prompt section, the
Socratic guardrails system-prompt text, the digest cron jobs (due-rep,
team-quiz, teach-back), and — last, and unable to take any of the above down
if it fails — the `socratic-debate` skill (see
`_register_socratic_debate_skill_safely`).

Loaded by Hermes as `import plugins.hermes-kata` would be if the package name
were a valid identifier — in practice, via `importlib` against this file's
own `submodule_search_locations`, same as the plugin loader documents (see
`tests/test_plugin_register.py`). `from hermes_kata import ...` here resolves
against the `hermes_kata/` package sitting next to this file, not a globally
installed one.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from hermes_kata.client import LearningServiceClient
from hermes_kata.digest import create_digest_jobs, load_digest_roster, team_recipient_from_env
from hermes_kata.guardrails import register_guardrails_section, register_socratic_debate_skill
from hermes_kata.identity import SessionIdentityCache, SessionStoreHandle, register_identity_hook
from hermes_kata.mcq import register_mcq_rendering_section
from hermes_kata.quiz import ensure_quiz_thread_identity
from hermes_kata.tools import JobIdentityRegistry, make_identity_resolver, register_tools


def register(ctx: Any) -> None:
    client = LearningServiceClient.from_env()
    cache = SessionIdentityCache()
    store_handle = SessionStoreHandle()
    job_identities = JobIdentityRegistry()

    register_identity_hook(ctx, client, cache, store_handle)
    register_tools(
        ctx,
        client,
        resolve_identity=make_identity_resolver(cache, job_identities, store_handle),
    )
    register_mcq_rendering_section(ctx)
    register_guardrails_section(ctx)
    _register_digest_jobs(ctx, client, job_identities)
    _register_socratic_debate_skill_safely(ctx)


def _register_digest_jobs(ctx: Any, client: LearningServiceClient, job_identities: JobIdentityRegistry) -> None:
    """Best-effort, config-driven (spec §6): `KATA_DIGEST_ROSTER` unset is a
    no-op — same convention as `LEARNING_SERVICE_SRC` elsewhere in this
    plugin — not a failure, since the roster-import-with-chat-IDs step this
    depends on may not have run yet in a given environment.

    Links every learner's `slack_thread` quiz-answer identity (AGCTM-69
    fix-round 2) whenever a roster is configured, independent of whether
    `ctx` exposes `.cron` — that identity link is what makes a quiz answer
    resolvable at all, cron support or not. Digest cron job creation still
    needs both a roster *and* `ctx.cron` *and* a team recipient.
    """
    roster_path = os.environ.get("KATA_DIGEST_ROSTER")
    if not roster_path:
        return
    learners = load_digest_roster(Path(roster_path))

    for learner in learners:
        ensure_quiz_thread_identity(client, learner.external_id)

    cron = getattr(ctx, "cron", None)
    if cron is None:
        return
    team_recipient = team_recipient_from_env()
    if team_recipient is None:
        return
    create_digest_jobs(cron, job_identities, learners=learners, team_recipient=team_recipient)


def _register_socratic_debate_skill_safely(ctx: Any) -> None:
    """`ctx.register_skill` is unverified against the real Hermes plugin API
    (review round on this issue) — unlike `register_tool`/`register_hook`/
    `register_system_prompt_section`, which each already run in production
    via `tools.py`/`identity.py`/`mcq.py`, nothing else in this plugin calls
    `register_skill` yet, and this build has no real Hermes install or
    `hermes-v3` access to confirm its signature against (`hermes` is a
    separate team's service; out of reach here).

    So this call is ordered last in `register()`, after everything already
    proven to work, and any failure — wrong signature, `SKILL_PATH` missing
    at deploy time, `ctx` not exposing `register_skill` at all — is swallowed
    here rather than raised, so it can't take down the identity hook, tool
    catalog, mcq section, or digest jobs registered above it. This is a
    reduced-blast-radius mitigation, not a substitute for the real signature
    check the next person with `hermes-v3` access should still do.
    """
    register_skill = getattr(ctx, "register_skill", None)
    if register_skill is None:
        return
    try:
        register_socratic_debate_skill(ctx)
    except Exception:
        pass
