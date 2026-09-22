import threading
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image
from desktop.incremental import MessageState, IncrementalWorker, crop_new
from desktop.service import ServiceError


def snapshot(*pairs):
    return {"identity": "synthetic", "rows": [t for _, t in pairs],
            "items": [{"id": [n], "text": t, "box": [0, n*50, 1000, n*50+40]} for n, t in pairs],
            "message_box": [0, 0, 1000, 1000]}


class IncrementalTests(unittest.TestCase):
    def seed(self):
        return snapshot((1, "first"), (2, "reply"))

    def test_known_rows_need_no_ocr(self):
        state = MessageState(self.seed(), ["我", "对方"])
        self.assertEqual(state.pending(self.seed()), [])
        self.assertEqual(state.messages(self.seed())[-1]["from"], "other")

    def test_duplicate_text_new_id_is_new_message(self):
        state = MessageState(self.seed(), ["我", "对方"])
        new = state.pending(snapshot((1, "first"), (2, "reply"), (3, "reply")))
        self.assertEqual([i["id"] for i in new], [[3]])

    def test_old_scroll_does_not_become_new_message(self):
        state = MessageState(self.seed(), ["我", "对方"])
        self.assertIsNone(state.pending(snapshot((1, "first"))))
        with self.assertRaises(ServiceError):
            state.pending(snapshot((9, "history"), (1, "first"), (2, "reply")))

    def test_recycled_ids_and_lost_anchor_pause(self):
        state = MessageState(self.seed(), ["我", "对方"])
        for value in (snapshot((2, "different")), snapshot((3, "new")), snapshot((1, "first"), (1, "first"))):
            with self.assertRaises(ServiceError):
                state.pending(value)

    def test_unknown_speaker_not_cached(self):
        state = MessageState(self.seed(), ["我", "对方"])
        new_snapshot = snapshot((2, "reply"), (3, "new"))
        new = state.pending(new_snapshot)
        with self.assertRaises(ServiceError):
            state.accept(new_snapshot, new, ["待确认"])
        self.assertNotIn((3,), state.known)

    def test_crop_only_new_band_preserves_horizontal_geometry(self):
        image = Image.new("RGB", (1000, 1000), "white")
        cropped = crop_new(image, [0, 0, 1000, 1000], snapshot((3, "new"))["items"])
        self.assertEqual(cropped.size, (1000, 40))
        bad = snapshot((30, "offscreen"))["items"]
        with self.assertRaises(ServiceError):
            crop_new(image, [0, 0, 1000, 1000], bad)

    def worker(self):
        binding = MagicMock()
        binding.ready.return_value = True
        binding.message_box = (0, 0, 1000, 1000)
        title = Image.new("RGB", (100, 20), "white")
        binding.grab.return_value = title
        binding.capture.return_value = Image.new("RGB", (1000, 1000), "white")
        worker = IncrementalWorker({}, self.seed(), ["我", "对方"], binding, title,
                                   {"MINERU_API_TOKEN": "synthetic"}, "friend", {}, MagicMock())
        return worker

    def test_unchanged_list_no_capture_or_ocr_and_only_one_generation(self):
        worker = self.worker()
        with patch("desktop.incremental.request", return_value=self.seed()), patch("desktop.incremental.recognize") as ocr, patch("desktop.incremental.analyze", return_value={}) as generate:
            for _ in range(4):
                worker.step()
            worker.binding.capture.assert_not_called()
            ocr.assert_not_called()
            generate.assert_called_once()

    def test_new_batch_one_small_ocr_and_reuse_on_later_polls(self):
        worker = self.worker()
        value = snapshot((1, "first"), (2, "reply"), (3, "new"))
        with patch("desktop.incremental.request", return_value=value), patch("desktop.incremental.recognize", return_value=[]) as ocr, patch("desktop.incremental.to_transcript", return_value="对方：new"), patch("desktop.incremental.analyze", return_value={}) as generate:
            for _ in range(4):
                worker.step()
            self.assertEqual(ocr.call_count, 1)
            self.assertEqual(ocr.call_args.args[0].size, (1000, 40))
            generate.assert_called_once()

    def test_background_never_reads_or_calls_cloud(self):
        worker = self.worker()
        worker.binding.ready.return_value = False
        with patch("desktop.incremental.request") as read, patch("desktop.incremental.recognize") as ocr:
            worker.step()
            read.assert_not_called()
            ocr.assert_not_called()

    def test_changed_during_generation_drops_result(self):
        worker = self.worker()
        worker.latest = ("synthetic", (((1,), "first"), ((2,), "reply")))
        newer = snapshot((1, "first"), (2, "reply"), (3, "new"))
        with patch("desktop.incremental.request", side_effect=[self.seed(), self.seed(), newer]), patch("desktop.incremental.analyze", return_value={}):
            worker.step()
        self.assertFalse(any(c.args[0] == "result" for c in worker.emit.call_args_list))

    def test_stop_cancels_thread_before_any_work(self):
        worker = self.worker()
        worker.cancel.set()
        worker.step = MagicMock()
        worker.run()
        worker.step.assert_not_called()

    def test_manual_invalidation_cancels_incremental_session(self):
        from desktop.tests import test_watcher
        app = test_watcher.WatcherTests().app()
        engine = self.worker()
        app.watch = {"incremental": engine}
        app.invalidate()
        self.assertTrue(engine.cancel.is_set())
        self.assertIsNone(app.watch)

    def test_source_invalidation_keeps_session_but_clears_suggestions(self):
        from desktop.tests import test_watcher
        app = test_watcher.WatcherTests().app()
        engine = self.worker()
        app.watch = {"incremental": engine}
        app.replies = ["old"]
        app.invalidate(keep_incremental=True)
        self.assertFalse(engine.cancel.is_set())
        self.assertEqual(app.replies, [])

    def test_late_results_from_stopped_session_are_ignored(self):
        from desktop.tests import test_watcher
        app = test_watcher.WatcherTests().app()
        app.direct_epoch = 4
        app.watch = {"incremental": self.worker()}
        app.incremental_result(3, "incremental_result", {"candidates": ["stale"]})
        self.assertTrue(app.events.empty())

    def test_outgoing_new_message_does_not_generate(self):
        worker = self.worker()
        value = snapshot((2, "reply"), (3, "new"))
        with patch("desktop.incremental.request", return_value=value), patch("desktop.incremental.recognize", return_value=[]), patch("desktop.incremental.to_transcript", return_value="我：new"), patch("desktop.incremental.analyze") as generate:
            worker.step()
            worker.step()
            generate.assert_not_called()
