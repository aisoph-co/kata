#!/usr/bin/env python3
"""A stand-in `hermes` CLI for testing `apply-config.sh` without a real
Hermes install: understands only `config set <key> <value>`, writes into a
nested dict at `$HERMES_CONFIG_PATH`, JSON-encoded (valid YAML too, since
JSON is a YAML subset — so this doubles as a `config.yaml` stand-in with no
extra dependency)."""
import json
import os
import sys


def main() -> None:
    args = sys.argv[1:]
    if args[:2] != ["config", "set"]:
        raise SystemExit(f"fake hermes: unsupported command: {args}")
    key, value = args[2], args[3]

    config_path = os.environ["HERMES_CONFIG_PATH"]
    if os.path.exists(config_path):
        with open(config_path) as f:
            config = json.load(f)
    else:
        config = {}

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = value  # a bare string, e.g. "modal"

    node = config
    parts = key.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = parsed

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)


if __name__ == "__main__":
    main()
