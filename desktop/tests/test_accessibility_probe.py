"""Test synthetic accessibility objects only; no live Windows API calls."""
import subprocess
import unittest
from unittest.mock import patch

from desktop.accessibility_probe import summarize, run_bounded


class Backend:
    def identity(self, obj):
        return id(obj)

    def role(self, obj, child):
        return obj["role"] if not child else 34

    def child_count(self, obj):
        return len(obj.get("children", []))

    def children(self, obj, count):
        return obj.get("children", [])[:count]

    def accessible(self, obj):
        return obj


class ProbeTests(unittest.TestCase):
    def test_mixed_child_ids_and_objects(self):
        root = {"role": 33, "children": [1, {"role": 42}]}
        result = summarize(root, Backend())
        self.assertEqual(result["nodes"], 3)
        self.assertEqual(result["roles"], {"33": 1, "34": 1, "42": 1})
        self.assertFalse(result["truncated"])

    def test_cycles_are_bounded(self):
        root = {"role": 10}
        root["children"] = [root]
        self.assertEqual(summarize(root, Backend())["nodes"], 1)

    def test_node_and_depth_limits_are_reported(self):
        root = {"role": 10, "children": list(range(1, 100))}
        self.assertEqual(summarize(root, Backend(), limit=8)["nodes"], 8)
        self.assertTrue(summarize(root, Backend(), limit=8)["truncated"])
        self.assertTrue(summarize(root, Backend(), max_depth=0)["truncated"])

    def test_custom_roles_and_exceptions_do_not_leak_text(self):
        root = {"role": "private title", "name": "private text"}
        self.assertNotIn("private", str(summarize(root, Backend())))
        class Broken(Backend):
            def role(self, obj, child):
                raise RuntimeError("private message")
        result = summarize(root, Broken())
        self.assertEqual(result["errors"], 1)
        self.assertNotIn("private", str(result))

    def test_timeout_is_not_reported_as_empty_tree(self):
        with patch("desktop.accessibility_probe.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("probe", 25)):
            self.assertEqual(run_bounded()["status"], "timeout")

    def test_failed_worker_output_is_not_exposed(self):
        with patch("desktop.accessibility_probe.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 1, b"private", b"private")):
            self.assertEqual(run_bounded(), {"status": "probe_failed"})


if __name__ == "__main__":
    unittest.main()
