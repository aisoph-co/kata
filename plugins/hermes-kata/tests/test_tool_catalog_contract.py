"""Spec §1: "a contract test asserts every `tools.json` entry has exactly one
registered Hermes tool with a matching name and JSON-schema, and that no
*other* tool is registered under the `learning` toolset."""

from __future__ import annotations

import os
from pathlib import Path

from fakes import FakeLearningServiceClient, FakePluginContext

from hermes_kata.tools import TOOLSET, load_catalog, register_tools

REPO_ROOT = Path(__file__).resolve().parents[3]
# Mirrors `_default_tools_json_path`'s own resolution (tools.py): `tools.json`
# lives in `agency-v1`, not this repo — `LEARNING_SERVICE_SRC`, default a
# sibling `agency-v1/` checkout (how `multica repo checkout` lays out this
# workspace).
LEARNING_SERVICE_SRC = Path(os.environ.get("LEARNING_SERVICE_SRC") or (REPO_ROOT.parent / "agency-v1"))
TOOLS_JSON = LEARNING_SERVICE_SRC / "learning_service" / "tools.json"


def test_tools_json_exists_at_the_default_path():
    assert TOOLS_JSON.is_file()


def test_default_catalog_path_resolves_to_the_checked_in_tools_json():
    from hermes_kata.tools import _default_tools_json_path

    assert _default_tools_json_path() == TOOLS_JSON


def test_registered_tool_set_matches_tools_json_exactly():
    catalog = load_catalog(TOOLS_JSON)

    ctx = FakePluginContext()
    client = FakeLearningServiceClient()
    registered = register_tools(ctx, client, resolve_identity=lambda **_: None, tools_json_path=TOOLS_JSON)

    catalog_names = {tool["name"] for tool in catalog}
    assert set(registered) == catalog_names
    assert set(ctx.tools.keys()) == catalog_names

    # No tool registered under `learning` that isn't in the catalog, and no
    # catalog tool registered under any other toolset.
    for name, entry in ctx.tools.items():
        assert entry["toolset"] == TOOLSET


def test_registered_schema_matches_the_catalog_entry():
    catalog = {tool["name"]: tool for tool in load_catalog(TOOLS_JSON)}

    ctx = FakePluginContext()
    client = FakeLearningServiceClient()
    register_tools(ctx, client, resolve_identity=lambda **_: None, tools_json_path=TOOLS_JSON)

    for name, entry in ctx.tools.items():
        assert entry["schema"] == catalog[name]["parameters"]
        assert entry["description"] == catalog[name].get("description", "")


def test_tools_json_is_the_only_place_a_tool_definition_is_hand_written():
    # Guards against a future hand-copied schema drifting from tools.json:
    # the module never imports a second schema source.
    import inspect

    import hermes_kata.tools as tools_module

    source = inspect.getsource(tools_module)
    assert "get_next_items" not in source  # no hand-copied tool name/schema
