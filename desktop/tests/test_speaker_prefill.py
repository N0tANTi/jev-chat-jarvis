import threading
import unittest
from unittest.mock import patch

from desktop.service import ServiceError
from desktop.speaker_prefill import match_speakers, predict, same_snapshot


class SpeakerPrefillTests(unittest.TestCase):
    def test_unique_text_matches_preserving_native_content(self):
        rows = ["hello world", "hi", "[wave]"]
        self.assertEqual(match_speakers(rows, "我：hello  world\n对方：hi"), ["我", "对方", "待确认"])
        self.assertEqual(rows, ["hello world", "hi", "[wave]"])

    def test_duplicate_native_or_ocr_is_ambiguous(self):
        self.assertEqual(match_speakers(["OK", "OK"], "我：OK\n对方：OK"), ["待确认"] * 2)
        self.assertEqual(match_speakers(["OK"], "我：OK\n对方：OK"), ["待确认"])

    def test_no_fuzzy_guess_and_unknown_is_preserved(self):
        self.assertEqual(match_speakers(["cat", "dog", "图片"], "我：car\n待确认：dog"), ["待确认"] * 3)

    def test_conflicting_order_is_rejected(self):
        self.assertEqual(match_speakers(["a", "b"], "我：b\n对方：a"), ["待确认"] * 2)

    def snapshot(self):
        return {"identity": "synthetic", "rows": ["hello"], "message_box": [0, 10, 100, 100], "title_box": [0, 0, 100, 10]}

    def test_all_identity_layout_and_text_fields_are_required(self):
        expected = self.snapshot()
        self.assertTrue(same_snapshot(expected, dict(expected)))
        for key in expected:
            changed = dict(expected)
            changed[key] = None
            self.assertFalse(same_snapshot(expected, changed))

    def test_changed_chat_before_upload_calls_no_ocr(self):
        with patch("desktop.speaker_prefill.request", return_value={}), patch("desktop.speaker_prefill.recognize") as ocr:
            with self.assertRaises(ServiceError):
                predict({}, self.snapshot(), None, "synthetic", threading.Event())
            ocr.assert_not_called()

    def test_changed_chat_during_ocr_discards_suggestions(self):
        with patch("desktop.speaker_prefill.request", side_effect=[self.snapshot(), {}]), patch("desktop.speaker_prefill.recognize"), patch("desktop.speaker_prefill.to_transcript", return_value="我：hello"):
            with self.assertRaises(ServiceError):
                predict({}, self.snapshot(), None, "synthetic", threading.Event())

    def test_cancel_before_work_does_not_read_or_upload(self):
        cancel = threading.Event()
        cancel.set()
        with patch("desktop.speaker_prefill.request") as read:
            with self.assertRaises(ServiceError):
                predict({}, self.snapshot(), None, "synthetic", cancel)
            read.assert_not_called()

    def test_successful_guarded_prediction(self):
        with patch("desktop.speaker_prefill.request", return_value=self.snapshot()), patch("desktop.speaker_prefill.recognize"), patch("desktop.speaker_prefill.to_transcript", return_value="我：hello"):
            self.assertEqual(predict({}, self.snapshot(), None, "synthetic", threading.Event()), ["我"])
