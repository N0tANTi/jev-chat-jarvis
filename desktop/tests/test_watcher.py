"""Synthetic frames and mocked bindings only; never capture the user's desktop."""
import queue
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

from desktop.app import App
from desktop.service import Generation, ServiceError
from desktop.watcher import SettledFrames, WindowBinding, header_matches, signature


class WatcherTests(unittest.TestCase):
    def test_settle_debounce_and_cooldown(self):
        frames = SettledFrames()
        self.assertFalse(frames.observe("a", 0))
        self.assertFalse(frames.observe("b", 1))
        self.assertFalse(frames.observe("b", 2))
        self.assertTrue(frames.observe("b", 2.5))
        frames.submitted("b", 2.5)
        self.assertFalse(frames.observe("b", 20))
        self.assertFalse(frames.observe("c", 3))
        self.assertFalse(frames.observe("c", 5))
        self.assertTrue(frames.observe("c", 7.5))

    def test_title_change_or_resize_is_rejected(self):
        title = Image.new("RGB", (20, 10), "white")
        self.assertTrue(header_matches(title, title.copy()))
        changed = title.copy()
        changed.putpixel((3, 3), (0, 0, 0))
        self.assertFalse(header_matches(title, changed))
        self.assertFalse(header_matches(title, title.resize((10, 20))))

    def binding(self):
        binding = WindowBinding.__new__(WindowBinding)
        binding.title_box, binding.message_box = (0, 0, 20, 10), (0, 10, 20, 40)
        binding.ready = MagicMock(return_value=True)
        binding.grab = MagicMock()
        return binding

    def test_background_window_does_not_capture(self):
        binding = self.binding()
        binding.ready.return_value = False
        self.assertIsNone(binding.capture(Image.new("RGB", (20, 10))))
        binding.grab.assert_not_called()

    def test_title_switch_during_capture_discards_frame(self):
        binding = self.binding()
        title = Image.new("RGB", (20, 10), "white")
        binding.grab.side_effect = [title, Image.new("RGB", (20, 30)), Image.new("RGB", (20, 10), "black")]
        with self.assertRaises(ServiceError):
            binding.capture(title)

    def app(self):
        app = App.__new__(App)
        app.generation = Generation()
        app.auto_revision = app.generation.revision
        app.closed = False
        app.events = queue.Queue()
        for name in ("root", "status", "insight", "watch_btn", "transcript", "reviewed", "store", "relationship"):
            setattr(app, name, MagicMock())
        app.cards = [(MagicMock(), MagicMock()) for _ in range(3)]
        app.replies = []
        app.update_buttons = MagicMock()
        app.worker = None
        app.contact_id = "test-contact"
        app.keys = {}
        frame = Image.new("RGB", (20, 30))
        binding = MagicMock()
        binding.capture.return_value = frame
        app.watch = {"binding": binding, "title": Image.new("RGB", (20, 10)),
                     "last_seen": signature(frame), "frames": SettledFrames()}
        app.transcript.get.return_value = "对方：晚上吃饭吗？"
        app.relationship.get.return_value = "friend"
        return app

    def test_late_auto_result_rechecks_source(self):
        app = self.app()
        app.watch["binding"].capture.return_value = Image.new("RGB", (20, 30), "white")
        app.events.put((app.generation.revision, "auto_analysis", {"candidates": ["wrong"] * 3}))
        app.poll()
        self.assertEqual(app.replies, [])
        self.assertIsNone(app.auto_revision)

    def test_auto_generation_uses_memory_but_never_appends_history(self):
        app = self.app()
        app.start_job = MagicMock()
        app.generate_automatic(app.generation.revision)
        self.assertEqual(app.start_job.call_args.args[0], "auto_analysis")
        operation = app.start_job.call_args.args[1]
        with patch("desktop.app.analyze", return_value={}) as analyze:
            operation(MagicMock(), MagicMock())
            self.assertEqual(analyze.call_args.kwargs["memory"], app.store.context.return_value)
        app.store.append.assert_not_called()

    def test_background_at_next_cloud_stage_prevents_submission(self):
        app = self.app()
        app.watch["binding"].capture.return_value = None
        app.start_job = MagicMock()
        app.generate_automatic(app.generation.revision)
        app.start_job.assert_not_called()

    def test_error_stops_automatic_retries(self):
        app = self.app()
        app.events.put((app.generation.revision, "error", "OCR failed"))
        app.poll()
        self.assertIsNone(app.watch)
        app.status.set.assert_called_with("OCR failed")

    def test_switching_contact_or_manual_edit_stops_watch(self):
        app = self.app()
        app.suppress_edit = False
        app.transcript.edit_modified.return_value = True
        app.on_edit()
        self.assertIsNone(app.watch)
        self.assertEqual(app.replies, [])


if __name__ == "__main__":
    unittest.main()
