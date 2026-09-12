"""Hermes plugin loader entrypoint (`plugin.yaml`'s package).

Wires the jobs this build ships (spec §1, §2, §4, §6, §8) into a live
`PluginContext`: identity binding (`pre_gateway_dispatch`), the `tools.json`
tool catalog, the mcq/msq `clarify`-rendering system-prompt section, the
Socratic guardrails system-prompt text, the digest cron jobs (due-rep,
team-quiz, teach-back), and — last, and unable to take any of the above down
if it fails — the `socratic-debate` skill (see
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
    from .hermes_kata.identity import (
        SessionIdentityCache,
        SessionStoreHandle,
        install_api_server_identity_gate,
        register_identity_hook,
        with_api_server_fallback,
    )
    from .hermes_kata.mcq import register_mcq_rendering_section
    from .hermes_kata.quiz import ensure_quiz_thread_identity
    from .hermes_kata.tools import JobIdentityRegistry, make_identity_resolver, register_tools
except ImportError:
    from hermes_kata.client import LearningServiceClient
    from hermes_kata.digest import create_digest_jobs, load_digest_roster, team_recipient_from_env
    from hermes_kata.guardrails import register_guardrails_section, register_socratic_debate_skill
    from hermes_kata.identity import (
        SessionIdentityCache,
        SessionStoreHandle,
        install_api_server_identity_gate,
        register_identity_hook,
        with_api_server_fallback,
    )
    from hermes_kata.mcq import register_mcq_rendering_section
    from hermes_kata.quiz import ensure_quiz_thread_identity
    from hermes_kata.tools import JobIdentityRegistry, make_identity_resolver, register_tools


def register(ctx: Any) -> None:
    client = LearningServiceClient.from_env()
    cache = SessionIdentityCache()
    store_handle = SessionStoreHandle()
    job_identities = JobIdentityRegistry()
    # KATA-14: a second, independent cache for the web popup's platform —
    # api_server never touches the gateway's own SessionStore at all (see
    # identity.py's module docstring), so it can't share `cache` above.
    api_server_cache = SessionIdentityCache()

    register_identity_hook(ctx, client, cache, store_handle)
    # No-op (returns False, logs why) when the api_server platform isn't
    # even loaded in this process — e.g. a Slack-only/CLI-only Hermes.
    install_api_server_identity_gate(client, api_server_cache)
    register_tools(
        ctx,
        client,
        resolve_identity=with_api_server_fallback(
            make_identity_resolver(cache, job_identities, store_handle), api_server_cache
        ),
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
