#!/usr/bin/env python3
"""Shared policy for Passrail-authorized local host execution.

The native MCP server remains responsible for each tool's detailed JSON schema.
This layer deliberately validates only the stable security boundary: which host
tools may cross Passrail, JSON-serializability, and an overall argument-size cap.
That avoids silently narrowing Desktop Commander's capabilities as its schemas evolve.
"""
from __future__ import annotations

import json
from typing import Any

MAX_DIRECT_ARGUMENT_BYTES = 240 * 1024

READ_ONLY_TOOLS = {
    "get_config",
    "read_file",
    "read_multiple_files",
    "list_directory",
    "start_search",
    "get_more_search_results",
    "list_searches",
    "get_file_info",
    "read_process_output",
    "list_sessions",
    "list_processes",
    "get_usage_stats",
    "get_recent_tool_calls",
    "get_prompts",
}

CONSEQUENTIAL_TOOLS = {
    "set_config_value",
    "write_file",
    "write_pdf",
    "create_directory",
    "move_file",
    "stop_search",
    "edit_block",
    "start_process",
    "interact_with_process",
    "force_terminate",
    "kill_process",
    "give_feedback_to_desktop_commander",
}

SUPPORTED_TOOLS = READ_ONLY_TOOLS | CONSEQUENTIAL_TOOLS


def validate_direct_tool_arguments(tool: str, arguments: Any) -> dict[str, Any]:
    if tool not in SUPPORTED_TOOLS:
        raise ValueError("unsupported Bridger host tool")
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")
    try:
        encoded = json.dumps(
            arguments,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"arguments must be finite standard JSON: {exc}") from exc
    if len(encoded) > MAX_DIRECT_ARGUMENT_BYTES:
        raise ValueError("arguments exceed direct Bridger limit")
    return dict(arguments)
