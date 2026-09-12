"""§5/§7 lockdown tests: after `apply-config.sh` runs, every configured
platform's `platform_toolsets` is a subset of {learning, clarify, web} and
`sessions.retention_days` <= 14 — a config-file assertion, not a live-agent
probe, so it runs in CI without a Hermes process (`fake_hermes.py` stands
in for the real `hermes` CLI)."""
import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
APPLY_CONFIG = REPO_ROOT / "deploy" / "kata" / "apply-config.sh"
FAKE_HERMES_SOURCE = Path(__file__).parent / "fake_hermes.py"


@pytest.fixture
def config_after_apply(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    hermes_stub = bin_dir / "hermes"
    hermes_stub.write_text(FAKE_HERMES_SOURCE.read_text())
    hermes_stub.chmod(hermes_stub.stat().st_mode | stat.S_IEXEC)

    config_path = tmp_path / "config.yaml"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HERMES_CONFIG_PATH": str(config_path),
    }
    subprocess.run(["bash", str(APPLY_CONFIG)], check=True, env=env)

    return json.loads(config_path.read_text())


def test_platform_toolsets_are_a_subset_of_learning_clarify_web(config_after_apply):
    allowed = {"learning", "clarify", "web"}
    toolsets = config_after_apply["platform_toolsets"]
    assert toolsets, "every configured platform must actually be set"
    for platform, toolset in toolsets.items():
        assert set(toolset) <= allowed, f"{platform} has {toolset}"


def test_session_retention_is_at_most_fourteen_days_and_auto_prune_is_on(config_after_apply):
    assert config_after_apply["sessions"]["retention_days"] <= 14
    assert config_after_apply["sessions"]["auto_prune"] is True


def test_no_learner_facing_platform_has_a_dangerous_toolset(config_after_apply):
    dangerous = {"terminal", "file", "code_execution", "browser", "computer_use", "delegation"}
    for platform, toolset in config_after_apply["platform_toolsets"].items():
        assert not (set(toolset) & dangerous), f"{platform} has {toolset}"


def test_instance_level_guardrails_are_set(config_after_apply):
    assert config_after_apply["memory"]["memory_enabled"] is False
    assert config_after_apply["memory"]["user_profile_enabled"] is False
    assert config_after_apply["security"]["redact_secrets"] is True
    assert config_after_apply["terminal"]["backend"] == "modal"


def test_model_provider_is_named_not_auto(config_after_apply):
    """`auto` resolves to an Anthropic key the Kata services do not carry."""
    assert config_after_apply["model"]["provider"] == "openrouter"
    assert config_after_apply["model"]["default"]
