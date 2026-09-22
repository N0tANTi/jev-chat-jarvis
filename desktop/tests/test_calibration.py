import unittest
from unittest.mock import MagicMock, patch

from desktop.calibration import reviewed_rows, validate_first_frame, remove_ignored_first_frame
from desktop.service import ServiceError
from desktop.tests import test_watcher


class CalibrationTests(unittest.TestCase):
    def test_ignored_media_can_have_unknown_speaker_but_other_unknowns_remain(self):
        value = remove_ignored_first_frame("待确认：图片\n我：hello\n待确认：new", ["图片"])
        self.assertEqual(value, "我：hello\n待确认：new")

    def test_choices_build_transcript_and_drop_media(self):
        text, messages = reviewed_rows(["hello", "picture", "hi"], ["我", "忽略", "对方"])
        self.assertEqual(text, "我：hello\n对方：hi")
        self.assertEqual(len(messages), 2)

    def test_no_default_speaker(self):
        for choices in (["待确认"], []):
            with self.assertRaises(ServiceError):
                reviewed_rows(["hello"], choices)

    def test_both_sides_required(self):
        only = [{"from": "me", "text": "hello"}]
        with self.assertRaises(ServiceError):
            validate_first_frame(only, only, [])

    def test_calibration_compares_direction_order_and_duplicate_count(self):
        ref = [{"from": "me", "text": "hello"}, {"from": "other", "text": "hello"}]
        validate_first_frame(ref, ref, [])
        for actual in (ref[::-1], ref[:1], ref + ref, [dict(ref[0]), dict(ref[0])]):
            with self.assertRaises(ServiceError):
                validate_first_frame(ref, actual, [])

    def test_ignored_content_collision_is_rejected(self):
        ref = [{"from": "me", "text": "hello"}, {"from": "other", "text": "hi"}]
        with self.assertRaises(ServiceError):
            validate_first_frame(ref, ref, ["hello"])
        validate_first_frame(ref, ref + [{"from": "me", "text": "picture"}], ["picture"])

    def test_calibration_failure_never_schedules_generation(self):
        app = test_watcher.WatcherTests().app()
        app.watch.update(reference=[{"from": "me", "text": "hello"}, {"from": "other", "text": "hi"}], ignored=[])
        app.events.put((app.generation.revision, "auto_ocr", "对方：hello\n我：hi"))
        app.poll()
        self.assertIsNone(app.watch)
        self.assertEqual(app.replies, [])
        self.assertTrue(all(call.args[0] == 100 for call in app.root.after.call_args_list))

    def test_success_calibrates_once_then_new_text_needs_no_review(self):
        app = test_watcher.WatcherTests().app()
        app.watch.update(reference=[{"from": "me", "text": "hello"}, {"from": "other", "text": "hi"}], ignored=[])
        app.events.put((app.generation.revision, "auto_ocr", "我：hello\n对方：hi"))
        app.poll()
        self.assertTrue(app.watch["calibrated"])
        app.auto_revision = app.generation.revision
        app.events.put((app.generation.revision, "auto_ocr", "对方：new message"))
        app.poll()
        self.assertIsNotNone(app.watch)
        self.assertEqual(sum(c.args[0] == 150 for c in app.root.after.call_args_list), 2)

    def test_new_message_during_ocr_retries_without_review(self):
        app = test_watcher.WatcherTests().app()
        app.watch["frames"].processed = "old"
        app.events.put((app.generation.revision, "auto_ocr", None))
        app.poll()
        self.assertIsNotNone(app.watch)
        self.assertIsNone(app.watch["frames"].processed)

    def test_native_change_during_recognition_returns_retry(self):
        app = test_watcher.WatcherTests().app()
        app.keys = {"MINERU_API_TOKEN": "synthetic"}
        cancel = MagicMock()
        cancel.is_set.return_value = False
        with patch("desktop.direct_reader.request", side_effect=[{"rows": ["a"]}, {"rows": ["b"]}]), patch("desktop.app.recognize"), patch("desktop.app.to_transcript", return_value="对方：hi"):
            self.assertIsNone(app.recognize_watched({"native": {"hwnd": 1}}, None, cancel, MagicMock()))


if __name__ == "__main__":
    unittest.main()
