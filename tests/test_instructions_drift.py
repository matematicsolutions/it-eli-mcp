"""Drift test - INSTRUCTIONS consistent with registered tools and ITError codes.

Adapted from the eu-legal-mcp production line (de-eli-mcp), itself cherry-picked
from dograh-hq/dograh v1.31.0 (BSD-2).

Fails if:
  1. A tool name in INSTRUCTIONS (backtick) is not registered in mcp
  2. An ErrorCode in ITError.VALID_CODES is not documented in INSTRUCTIONS
  3. A tool references an ITError code not in VALID_CODES
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from it_eli_mcp.server import INSTRUCTIONS, ITError, mcp

SRC = (Path(__file__).parent.parent / "src" / "it_eli_mcp" / "server.py").read_text(
    encoding="utf-8"
)


def _registered_tool_names() -> set[str]:
    if hasattr(mcp, "_tool_manager"):
        tools_dict = getattr(mcp._tool_manager, "_tools", {})
        if tools_dict:
            return set(tools_dict.keys())
    # Non-greedy across nested parens: `@mcp.tool(..., output_schema=Model.model_json_schema())`
    return set(re.findall(r"@mcp\.tool\(.*?\)\s*\nasync def (\w+)", SRC, re.DOTALL))


def _referenced_tool_names_in_instructions() -> set[str]:
    out: set[str] = set()
    for m in re.finditer(r"`([a-z][a-z0-9_]{3,})`", INSTRUCTIONS):
        token = m.group(1)
        if "_" in token:
            out.add(token)
    return out


def test_instructions_only_reference_registered_tools():
    registered = _registered_tool_names()
    referenced = _referenced_tool_names_in_instructions()
    referenced_tools = {r for r in referenced if r.startswith("it_")}
    orphan = referenced_tools - registered
    assert not orphan, (
        f"INSTRUCTIONS reference tools not in mcp: {orphan}. Registered: {sorted(registered)}."
    )


def test_all_registered_tools_documented():
    registered = _registered_tool_names()
    referenced = _referenced_tool_names_in_instructions()
    missing = registered - referenced
    assert not missing, f"Registered tools missing from INSTRUCTIONS: {missing}."


def test_error_codes_documented_in_instructions():
    undocumented = {
        code for code in ITError.VALID_CODES
        if not re.search(r"\b" + re.escape(code) + r"\b", INSTRUCTIONS)
    }
    assert not undocumented, f"ErrorCodes not documented in INSTRUCTIONS: {undocumented}."


def test_raised_error_codes_in_valid_codes():
    raised = set(re.findall(r'ITError\(\s*"(\w+)"\s*,', SRC))
    invalid = raised - ITError.VALID_CODES
    assert not invalid, f"ITError uses codes not in VALID_CODES: {invalid}."


def test_it_error_format():
    err = ITError("invalid_arg", "bad ref")
    assert str(err).startswith("[invalid_arg] ")


def test_it_error_rejects_unknown_code():
    with pytest.raises(ValueError, match="Unknown ITError code"):
        ITError("nope", "x")

def test_all_registered_tools_mentioned_in_instructions():
    """Every registered tool must be reachable from INSTRUCTIONS.

    The weak direction (instructions naming tools that do not exist) catches stale docs.
    This is the other direction: a tool the instructions never mention is registered but
    not routed, so the model has no reason to reach for it. That is how a capability
    ships without the behaviour change it was meant to deliver.
    """
    registered = _registered_tool_names()
    # a tool may be named bare (`tool`) or with a call example (`tool(arg=...)`) - both route the model
    missing = {
        t for t in registered
        if f"`{t}`" not in INSTRUCTIONS and f"`{t}(" not in INSTRUCTIONS
    }
    assert not missing, f"Registered tools absent from INSTRUCTIONS: {missing}"
