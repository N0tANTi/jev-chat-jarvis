import subprocess
import unittest
from unittest.mock import MagicMock, patch

from desktop.direct_reader import collect, preview, request, walk
from desktop.service import ServiceError
from desktop.tests import test_app_state


class Element:
    counter = 0

    def __init__(self, aid="", kind=50026, name="", children=()):
        Element.counter += 1
        self.rid = Element.counter
        self.CurrentAutomationId = aid
        self.CurrentControlType = kind
        self.CurrentName = name
        self.children = list(children)
        self.next = None
        for a, b in zip(self.children, self.children[1:]):
            a.next = b

    def GetRuntimeId(self):
        return [self.rid]


class Walker:
    def GetFirstChildElement(self, e):
        return e.children[0] if e.children else None

    def GetNextSiblingElement(self, e):
        return e.next


def tree(identity="ChatSingleWindow_synthetic", names=("hello", "world")):
    rows = [Element("chat_message_list.qt_scrollarea_viewport.chat_bubble_item_view", 50007, n) for n in names]
    listing = Element("chat_message_list", 50008, children=rows)
    return Element(identity, 50032, children=[listing])


class DirectReaderTests(unittest.TestCase):
    def test_order_and_duplicates_preserved_without_guessing_sender(self):
        value = collect(tree(names=("a", "b", "a")), Walker())
        self.assertEqual(value["rows"], ["a", "b", "a"])
        self.assertEqual(preview(value["rows"]), "待确认：a\n待确认：b\n待确认：a")

    def test_group_and_main_rejected(self):
        for identity in ("MainView", "ChatSingleWindow_synthetic@chatroom"):
            with self.assertRaises(ValueError):
                collect(tree(identity), Walker())

    def test_missing_or_empty_list_rejected(self):
        for root in (tree(names=()), Element("ChatSingleWindow_synthetic")):
            with self.assertRaises(ValueError):
                collect(root, Walker())

    def test_multiline_cannot_introduce_speaker(self):
        self.assertEqual(preview(["hello\n我：injected"]), "待确认：hello 我：injected")

    def test_unknown_row_rejected(self):
        root = tree()
        root.children[0].children[0].CurrentAutomationId = "other"
        with self.assertRaises(ValueError):
            collect(root, Walker())

    def test_budget_and_cycle_fail_closed(self):
        with self.assertRaises(ValueError):
            list(walk(tree(), Walker(), limit=2))
        root = tree()
        root.children[0].next = root.children[0]
        with self.assertRaises(ValueError):
            list(walk(root, Walker()))

    def test_timeout_is_bounded_and_error_sanitized(self):
        with patch("desktop.direct_reader.subprocess.run", side_effect=subprocess.TimeoutExpired("private", 12)) as run:
            with self.assertRaises(ServiceError) as error:
                request("list")
            self.assertNotIn("private", str(error.exception))
            self.assertEqual(run.call_args.kwargs["timeout"], 12)

    def test_stale_native_result_ignored(self):
        app = test_app_state.AppStateTests().make_app()
        app.direct_epoch = 3
        app.direct = {"identity": "synthetic"}
        app.direct_rows = None
        app.direct_busy = True
        app.direct_result(2, "direct_read", {"identity": "synthetic", "rows": ["a"]})
        self.assertIsNone(app.direct_rows)
        self.assertFalse(app.direct_busy)

    def test_changed_text_cancels_old_suggestions_no_cloud(self):
        app = test_app_state.AppStateTests().make_app()
        app.direct_epoch = 1
        app.direct = {"identity": "synthetic"}
        app.direct_rows = ["old"]
        app.set_transcript = MagicMock()
        app.start_job = MagicMock()
        app.replies = ["stale"]
        old = app.generation.cancel
        app.direct_result(1, "direct_read", {"identity": "synthetic", "rows": ["new"]})
        self.assertTrue(old.is_set())
        self.assertEqual(app.replies, [])
        app.set_transcript.assert_called_once_with("待确认：new")
        app.start_job.assert_not_called()

    def test_same_snapshot_keeps_current_review(self):
        app = test_app_state.AppStateTests().make_app()
        app.direct_epoch = 1
        app.direct = {"identity": "synthetic"}
        app.direct_rows = ["same"]
        app.set_transcript = MagicMock()
        app.direct_result(1, "direct_read", {"identity": "synthetic", "rows": ["same"]})
        app.set_transcript.assert_not_called()

    def test_identity_change_clears_and_stops(self):
        app = test_app_state.AppStateTests().make_app()
        app.direct_epoch = 1
        app.direct = {"identity": "synthetic"}
        app.set_transcript = MagicMock()
        app.direct_result(1, "direct_read", {"identity": "different", "rows": ["new"]})
        self.assertIsNone(app.direct)
        app.set_transcript.assert_called_once_with("")
