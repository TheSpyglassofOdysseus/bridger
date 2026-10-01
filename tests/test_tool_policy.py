from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "selfhosted"))

import bridge_tool_policy as policy


class ToolPolicyTests(unittest.TestCase):
    def test_current_desktop_commander_surface_is_classified(self):
        expected = {
            "get_config", "set_config_value", "read_file", "read_multiple_files",
            "write_file", "write_pdf", "create_directory", "list_directory",
            "move_file", "start_search", "get_more_search_results", "stop_search",
            "list_searches", "get_file_info", "edit_block", "start_process",
            "read_process_output", "interact_with_process", "force_terminate",
            "list_sessions", "list_processes", "kill_process", "get_usage_stats",
            "get_recent_tool_calls", "give_feedback_to_desktop_commander", "get_prompts",
        }
        self.assertEqual(policy.SUPPORTED_TOOLS, expected)
        self.assertFalse(policy.READ_ONLY_TOOLS & policy.CONSEQUENTIAL_TOOLS)

    def test_native_schema_features_are_not_silently_narrowed(self):
        args = policy.validate_direct_tool_arguments(
            "read_file", {"path": "/tmp/example", "offset": -20, "options": {"raw": True}}
        )
        self.assertEqual(args["offset"], -20)
        with self.assertRaisesRegex(ValueError, "unsupported"):
            policy.validate_direct_tool_arguments("not_a_real_tool", {})


if __name__ == "__main__":
    unittest.main()
