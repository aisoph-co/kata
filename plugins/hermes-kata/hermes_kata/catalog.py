"""Loads the frozen, framework-neutral tool catalog and builds the Hermes
tool registrations from it (spec §1).

The catalog is never hand-copied: this module vendors a snapshot of
`learning_service/tools.json` (frozen contract, v1.1.0) at
`hermes_kata/tools.json`, but always prefers the path in `KATA_TOOLS_JSON`
when set, so a real `learning/learning_service/tools.json` checkout (once
Stage 1 core lands one in this repo) is a drop-in override with no code
change — "adding a tool means editing tools.json once" is only true if this
loader stays a loader, not a transcription.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from .forwarder import make_forwarder

_VENDORED_CATALOG_PATH = Path(__file__).parent / "tools.json"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    method: str
    path: str
    parameters: dict[str, Any]


def catalog_path() -> Path:
    override = os.environ.get("KATA_TOOLS_JSON")
    return Path(override) if override else _VENDORED_CATALOG_PATH


def load_tool_catalog(path: Path | None = None) -> list[ToolSpec]:
    path = path or catalog_path()
    data = json.loads(path.read_text())
    return [
        ToolSpec(
            name=entry["name"],
            description=entry["description"],
            method=entry["endpoint"]["method"],
            path=entry["endpoint"]["path"],
            parameters=entry["parameters"],
        )
        for entry in data["tools"]
    ]


def register_tools(
    ctx,
    client,
    catalog: list[ToolSpec] | None = None,
    *,
    is_quiz_item: Optional[Callable[[Any], bool]] = None,
    on_review: Optional[Callable[..., None]] = None,
) -> list[str]:
    """Register one Hermes tool per catalog entry via `ctx.register_tool`.

    Returns the registered tool names, so the contract test can assert the
    generated set equals the catalog exactly — the catalog is the whole
    surface, not a floor.

    `is_quiz_item` and `on_review` (issue G1) are only ever wired onto
    `submit_review` — every other tool is registered exactly as before.
    """
    catalog = catalog if catalog is not None else load_tool_catalog()
    registered: list[str] = []
    for tool in catalog:
        is_submit_review = tool.name == "submit_review"
        ctx.register_tool(
            name=tool.name,
            toolset="learning",
            schema=tool.parameters,
            handler=make_forwarder(
                client,
                tool.method,
                tool.path,
                is_quiz_item=is_quiz_item if is_submit_review else None,
                on_review=on_review if is_submit_review else None,
            ),
            description=tool.description,
        )
        registered.append(tool.name)
    return registered
