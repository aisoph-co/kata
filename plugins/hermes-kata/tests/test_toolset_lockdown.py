"""Spec §5: "read `config.yaml` after `apply-config.sh` runs and assert
`platform_toolsets` for every configured platform is a subset of
`{learning, clarify, web}`" — a config-file assertion, not a live-agent
probe, so this actually runs `apply-config.sh` against a stubbed `hermes`
on `PATH` and reads back the `config.yaml` it wrote, with no live Hermes
process required. A shell-quoting or `set --` bug in the script would
still show up here, unlike a regex over the script's own source.
"""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
# One canonical copy under deploy/kata/hermes/ — see its own header for why
# it now also carries the instance-level keys (KATA-17).
APPLY_CONFIG = REPO_ROOT / "deploy" / "kata" / "hermes" / "apply-config.sh"

ALLOWED_LEARNER_TOOLSETS = {"learning", "clarify", "web"}
DISALLOWED_TOOLSETS = {"terminal", "file", "code_execution", "browser", "computer_use", "delegation"}

# Fake `hermes` binary: persists each `config set --force <key> <value>` call
# into the YAML file named by $FAKE_HERMES_CONFIG (dotted keys become nested
# mappings, mirroring `hermes config set`'s real behaviour), and answers
# `config get <key>` from that same file so apply-config.sh's closing
# `hermes config get terminal.backend` has something to read.
FAKE_HERMES = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import os
    import sys
    import yaml

    CONFIG_PATH = os.environ["FAKE_HERMES_CONFIG"]


    def load():
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}


    def save(data):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f)


    def main(args):
        if args[:2] == ["config", "set"]:
            rest = args[2:]
            if rest and rest[0] == "--force":
                rest = rest[1:]
            key, value = rest[0], rest[1]
            data = load()
            node = data
            parts = key.split(".")
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = yaml.safe_load(value)
            save(data)
            return 0
        if args[:2] == ["config", "get"]:
            data = load()
            node = data
            for part in args[2].split("."):
                node = node.get(part, {}) if isinstance(node, dict) else {}
            print(node)
            return 0
        print(f"fake hermes: unsupported args {args}", file=sys.stderr)
        return 1


    if __name__ == "__main__":
        sys.exit(main(sys.argv[1:]))
    """
)


@pytest.fixture()
def config_yaml(tmp_path: Path) -> dict:
    """Run apply-config.sh for real against the stubbed `hermes` above and
    return the resulting config.yaml — the read-back the issue's done check
    asks for, not a static parse of the script."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_hermes = bin_dir / "hermes"
    fake_hermes.write_text(FAKE_HERMES, encoding="utf-8")
    fake_hermes.chmod(0o755)

    config_path = tmp_path / "config.yaml"
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    env["FAKE_HERMES_CONFIG"] = str(config_path)

    result = subprocess.run(
        ["sh", str(APPLY_CONFIG)],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"apply-config.sh failed:\n{result.stderr}"

    return yaml.safe_load(config_path.read_text(encoding="utf-8"))


def test_apply_config_script_exists():
    assert APPLY_CONFIG.is_file()


def test_every_platform_toolset_is_a_subset_of_learning_clarify_web(config_yaml):
    platform_toolsets = config_yaml.get("platform_toolsets") or {}
    assert platform_toolsets, "apply-config.sh wrote no platform_toolsets to config.yaml"

    for platform, toolset in platform_toolsets.items():
        toolset = set(toolset)
        assert toolset <= ALLOWED_LEARNER_TOOLSETS, (
            f"platform_toolsets.{platform} = {toolset} exceeds {ALLOWED_LEARNER_TOOLSETS}"
        )
        assert toolset.isdisjoint(DISALLOWED_TOOLSETS)


def test_every_learner_facing_platform_from_the_spec_is_covered(config_yaml):
    platforms = set((config_yaml.get("platform_toolsets") or {}).keys())
    # KATA-14: api_server is the web popup's Hermes surface, locked down
    # exactly like every other platform (no "web" search toolset — that
    # stays Slack-only, KATA-15).
    assert platforms == {"slack", "telegram", "discord", "whatsapp_cloud", "signal", "api_server"}


def test_session_pruning_is_on_with_a_short_retention(config_yaml):
    assert config_yaml["sessions"]["auto_prune"] is True
    assert config_yaml["sessions"]["retention_days"] <= 14


def test_slack_alone_gets_web_search(config_yaml):
    """KATA-15: the Slack bot may check content freshness; the other four
    learner-facing platforms stay on {learning, clarify}."""
    platform_toolsets = config_yaml["platform_toolsets"]
    assert "web" in set(platform_toolsets["slack"])
    for platform in ("telegram", "discord", "whatsapp_cloud", "signal", "api_server"):
        assert "web" not in set(platform_toolsets[platform])


def test_web_search_is_pinned_to_the_exa_backend(config_yaml):
    """Without this, Hermes falls back to its keyless free tier and the
    EXA_API_KEY on this service is never used."""
    assert config_yaml["web"]["backend"] == "exa"
