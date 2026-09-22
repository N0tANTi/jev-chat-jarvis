"""Exercise event handling without screen capture, native windows or API calls."""
import queue
import unittest
from unittest.mock import MagicMock

from desktop.app import App
from desktop.service import Generation


class AppStateTests(unittest.TestCase):
    def make_app(self):
        app = App.__new__(App)
        app.generation = Generation()
        app.closed = False
        app.events = queue.Queue()
        app.root = MagicMock()
        app.status = MagicMock()
        app.insight = MagicMock()
        app.transcript = MagicMock()
        app.reviewed = MagicMock()
        app.cards = [(MagicMock(), MagicMock()) for _ in range(3)]
        app.replies = []
        app.suppress_edit = False
        app.update_buttons = MagicMock()
        return app

    def test_edit_disables_old_replies_and_cancels_request(self):
        app = self.make_app()
        old_cancel = app.generation.cancel
        app.replies = ["old reply"]
        app.transcript.edit_modified.return_value = True
        app.on_edit()
        self.assertTrue(old_cancel.is_set())
        self.assertEqual(app.replies, [])
        app.reviewed.set.assert_called_with(False)
        for _, button in app.cards:
            button.configure.assert_called_with(state="disabled")

    def test_late_result_cannot_restore_copy_buttons(self):
        app = self.make_app()
        revision = app.generation.revision
        app.invalidate()
        app.events.put((revision, "analysis", {"candidates": ["old"] * 3, "best_index": 0, "answers": {}}))
        app.poll()
        self.assertEqual(app.replies, [])
        for _, button in app.cards:
            button.configure.assert_called_with(state="disabled")

    def test_current_result_displays_three_candidates(self):
        app = self.make_app()
        app.events.put((app.generation.revision, "analysis", {"candidates": ["a", "b", "c"], "best_index": 1, "answers": {}}))
        app.poll()
        self.assertEqual(app.replies, ["a", "b", "c"])
        app.cards[1][0].configure.assert_called_with(text="推荐  b")

    def test_copy_is_clipboard_only(self):
        app = self.make_app()
        app.replies = ["reply"]
        app.copy_reply(0)
        self.assertEqual([c[0] for c in app.root.mock_calls], ["clipboard_clear", "clipboard_append"])
        app.root.clipboard_append.assert_called_with("reply")


if __name__ == "__main__":
    unittest.main()
