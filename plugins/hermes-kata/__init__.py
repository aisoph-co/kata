"""Hermes plugin loader entrypoint (`plugin.yaml`'s package).

Wires the jobs this build ships (spec §1, §2, §4, §6, §8) into a live
`PluginContext`: identity binding (`pre_gateway_dispatch`), the `tools.json`
tool catalog, the mcq/msq `clarify`-rendering system-prompt section, the
Socratic guardrails system-prompt text, the `kata_reveal` team-results tool
and its rendering system-prompt section (`team_reveal.py` — AGCTM-69's
fallback until a live quiz exists to reveal instead), the digest cron jobs
(due-rep, team-quiz, teach-back), and — last, and unable to take any of the
above down if it fails — the `socratic-debate` skill (see
`_register_socratic_debate_skill_safely`).

Loaded by Hermes as `import plugins.hermes-kata` would be if the package name
were a valid identifier — in practice, the real plugin manager (`hermes_cli/
plugins_loader.py::_load_directory_module`) execs this file via `importlib`
as `hermes_plugins.<slug>`, with `submodule_search_locations` set to this
file's own directory. That only makes `hermes_kata` resolvable as a
*relative* sibling import (`.hermes_kata`) — the loader never puts this
plugin's directory on `sys.path`, so a bare `from hermes_kata import ...`
raises `ModuleNotFoundError: No module named 'hermes_kata'` there (confirmed
against a live `hermes-v3`, KATA-17 deploy verification: the plugin loaded
under `pip install -e` in every test run, since the editable install already
puts `hermes_kata` on `sys.path`, but silently failed to register at all in
production). The `try/except ImportError` below tries the relative form
first for the real loader, falling back to the absolute form for anything
that execs this file with no package context (e.g. a stray direct import).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    from .hermes_kata.client import LearningServiceClient
    from .hermes_kata.digest import create_digest_jobs, load_digest_roster, team_recipient_from_env
    from .hermes_kata.guardrails import register_guardrails_section, register_socratic_debate_skill
    from .hermes_kata.identity import SessionIdentityCache, SessionStoreHandle, register_identity_hook
    from .hermes_kata.mcq import register_mcq_rendering_section
    from .hermes_kata.quiz import ensure_quiz_thread_identity
    from .hermes_kata.team_reveal import register_team_reveal
    from .hermes_kata.tools import (
        JobIdentityRegistry,
        cron_job_recipient_lookup,
        job_identities_from_env,
        make_identity_resolver,
        register_tools,
    )
except ImportError:
    from hermes_kata.client import LearningServiceClient
    from hermes_kata.digest import create_digest_jobs, load_digest_roster, team_recipient_from_env
    from hermes_kata.guardrails import register_guardrails_section, register_socratic_debate_skill
    from hermes_kata.identity import SessionIdentityCache, SessionStoreHandle, register_identity_hook
    from hermes_kata.mcq import register_mcq_rendering_section
    from hermes_kata.quiz import ensure_quiz_thread_identity
    from hermes_kata.team_reveal import register_team_reveal
    from hermes_kata.tools import (
        JobIdentityRegistry,
        cron_job_recipient_lookup,
        job_identities_from_env,
        make_identity_resolver,
        register_tools,
    )


def register(ctx: Any) -> None:
    client = LearningServiceClient.from_env()
    cache = SessionIdentityCache()
    store_handle = SessionStoreHandle()
    job_identities = JobIdentityRegistry()
    # KATA-24 fix round 2: bind identity for a cron job this plugin never
    # itself created (e.g. a demo job made directly against Hermes's cron
    # API) from durable deploy config, so it resolves from first boot rather
    # than needing an in-process registration this plugin's own code never
    # gets a chance to run.
    for _name, _identity in job_identities_from_env(os.environ.get("KATA_JOB_IDENTITIES")).items():
        job_identities.set(_name, _identity)
    # KATA-24 fix round 3: a job neither this plugin nor KATA_JOB_IDENTITIES
    # ever named (made directly against Hermes's cron API) still has its own
    # recipient recorded there — fall back to reading it back, best-effort,
    # rather than failing closed on every job this deploy didn't anticipate.
    resolve_identity = make_identity_resolver(
        cache, job_identities, store_handle, job_recipient_lookup=cron_job_recipient_lookup(getattr(ctx, "cron", None))
    )

    register_identity_hook(ctx, client, cache, store_handle)
    register_tools(ctx, client, resolve_identity=resolve_identity)
    register_mcq_rendering_section(ctx)
    register_guardrails_section(ctx)
    register_team_reveal(ctx)
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
    """`ctx.register_skill(name, path, description="", frontmatter=None)` —
    confirmed against the real Hermes plugin API on a live `hermes-v3`
    (KATA-17 deploy verification; see `guardrails.register_socratic_debate_
    skill`'s docstring for the `path` vs. content mixup this caught).

    This call is still ordered last in `register()`, after everything else
    already proven to work, and any failure — `SKILL_PATH` missing at
    deploy time, `ctx` not exposing `register_skill` at all, a future Hermes
    signature change — is swallowed here rather than raised, so it can't
    take down the identity hook, tool catalog, mcq section, or digest jobs
    registered above it.
    """
    register_skill = getattr(ctx, "register_skill", None)
    if register_skill is None:
        return
    try:
        register_socratic_debate_skill(ctx)
    except Exception:
        pass
