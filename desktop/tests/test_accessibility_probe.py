"""Test synthetic accessibility objects only; no live Windows API calls."""
import subprocess
import unittest
from unittest.mock import patch

from desktop.accessibility_probe import summarize, summarize_uia, run_bounded, partial_report, probe


class Element:
    def __init__(self, identity, control_type=50033, children=()):
        self.identity, self.CurrentControlType, self.children = identity, control_type, list(children)

    def GetRuntimeId(self):
        return (self.identity,)


class Walker:
    def __init__(self, root):
        self.next = {}
        pending, visited = [root], set()
        while pending:
            obj = pending.pop()
            if obj.identity in visited:
                continue
            visited.add(obj.identity)
            for i, child in enumerate(obj.children):
                self.next[child.identity] = obj.children[i+1] if i+1 < len(obj.children) else None
            pending.extend(obj.children)

    def GetFirstChildElement(self, obj):
        return next(iter(obj.children), None)

    def GetNextSiblingElement(self, obj):
        return self.next.get(obj.identity)


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
    def test_uia_counts_types_without_name_or_value(self):
        root = Element(1, children=[Element(2, 50008), Element(3, 50020)])
        result = summarize_uia(root, Walker(root))
        self.assertEqual(result["nodes"], 3)
        self.assertEqual(result["control_types"], {"50033": 1, "50008": 1, "50020": 1})
        self.assertEqual(result["errors"], 0)

    def test_uia_depth_limit_and_cycle(self):
        root = Element(1, children=[Element(2)])
        self.assertTrue(summarize_uia(root, Walker(root), max_depth=0)["truncated"])
        root.children = [root]
        self.assertEqual(summarize_uia(root, Walker(root))["nodes"], 1)

    def test_uia_sibling_cycle_does_not_hang(self):
        child = Element(2)
        root = Element(1, children=[child])
        walker = Walker(root)
        walker.next[2] = child
        self.assertEqual(summarize_uia(root, walker)["errors"], 1)

    def test_uia_node_budget_and_query_error(self):
        root = Element(1, children=[Element(i) for i in range(2, 30)])
        result = summarize_uia(root, Walker(root), limit=8)
        self.assertEqual(result["nodes"], 8)
        self.assertTrue(result["truncated"])
        with patch.object(Walker, "GetFirstChildElement", side_effect=RuntimeError("private")):
            result = summarize_uia(root, Walker(root))
        self.assertEqual(result["errors"], 1)
        self.assertNotIn("private", str(result))

    def test_partial_timeout_preserves_completed_samples(self):
        data = (b'{"event":"inventory","visible_windows":2}\n'
                b'{"event":"sample","sample":{"nodes":3}}\n'
                b'{"event":"attempt","target":{"api":"uia","view":"raw"}}\n'
                b'{"incomplete":')
        result = partial_report(data)
        self.assertEqual(result["visible_windows"], 2)
        self.assertEqual(result["samples"], [{"nodes": 3}])
        self.assertEqual(result["pending_target"]["view"], "raw")
        with patch("desktop.accessibility_probe.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("probe", 45, output=data)):
            self.assertEqual(run_bounded()["status"], "partial_timeout")

    def test_all_views_and_descendants_scheduled_without_live_apis(self):
        from unittest.mock import MagicMock
        msaa, uia = MagicMock(), MagicMock()
        uia.measure.return_value = {"nodes": 1}
        with patch("desktop.accessibility_probe.Msaa", return_value=msaa), \
             patch("desktop.accessibility_probe.Uia", return_value=uia), \
             patch("desktop.accessibility_probe.weixin_windows", return_value=[100]), \
             patch("desktop.accessibility_probe.child_windows", return_value=([(101, False)], False)), \
             patch("desktop.accessibility_probe.summarize", return_value={"nodes": 1}):
            result = probe()
        self.assertEqual(len(result["samples"]), 10)
        self.assertEqual(uia.measure.call_count, 6)
        self.assertEqual({call.args[1] for call in uia.measure.call_args_list}, {"raw", "control", "content"})
        self.assertEqual(result["schema_version"], 2)
        self.assertFalse(result["message_reading_verified"])

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
