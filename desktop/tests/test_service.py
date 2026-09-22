import io
import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image, ImageDraw

from desktop.service import (Cancelled, Generation, ServiceError, analyze, content_from_zip,
                             load_keys, parse_candidates, parse_transcript, recognize, request, to_transcript)


class ServiceTests(unittest.TestCase):
    def test_env_allowlist_and_process_override(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / ".env"
            p.write_text('export DEEPSEEK_API_KEY="local-test"\nMINERU_API_TOKEN=ocr-test\nUNRELATED=secret\n', encoding="utf-8")
            with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "override-test"}, clear=True):
                keys = load_keys(p)
        self.assertEqual(keys["DEEPSEEK_API_KEY"], "override-test")
        self.assertEqual(keys["MINERU_API_TOKEN"], "ocr-test")
        self.assertNotIn("UNRELATED", keys)

    def test_unknown_speaker_and_non_message_block_analysis(self):
        for text in ("待确认：你好", "测试会话", "", "我："):
            with self.subTest(text=text), self.assertRaises(ServiceError):
                parse_transcript(text)

    def test_repeated_messages_are_preserved(self):
        messages = parse_transcript("对方：好\n对方：好\n我: 嗯")
        self.assertEqual(len(messages), 3)
        self.assertEqual([m["from"] for m in messages], ["other", "other", "me"])

    def test_context_limit(self):
        with self.assertRaises(ServiceError):
            parse_transcript("我：好\n" * 31)

    def test_green_bubble_and_ambiguous_lines(self):
        image = Image.new("RGB", (1000, 1000), "white")
        ImageDraw.Draw(image).rectangle((330, 300, 700, 380), fill="#95ec69")
        content = [
            {"type": "text", "text": "右侧", "bbox": [330, 300, 700, 380]},
            {"type": "text", "text": "左侧长消息", "bbox": [60, 100, 800, 180]},
            {"type": "text", "text": "时间", "bbox": [440, 200, 550, 230]},
        ]
        self.assertEqual(to_transcript(content, image), "对方：左侧长消息\n待确认：时间\n我：右侧")

    def test_invalid_boxes_not_silently_used(self):
        with self.assertRaises(ServiceError):
            to_transcript([{"type": "text", "text": "x", "bbox": [0, 0, float("nan"), 20]}], Image.new("RGB", (100, 100)))

    def test_zip_only_reads_content_member_without_extracting(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("../../outside.txt", "ignored")
            archive.writestr("sample_content_list.json", json.dumps([{"type": "text"}]))
        self.assertEqual(content_from_zip(stream.getvalue()), [{"type": "text"}])

    def test_zip_requires_coordinate_content(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("full.md", "Only Markdown")
        with self.assertRaises(ServiceError):
            content_from_zip(stream.getvalue())

    def test_candidates_require_exactly_three_strings(self):
        for payload in ([], ["a", "b"], ["a", {}, "b"], ["a", "", "c"]):
            with self.subTest(payload=payload), self.assertRaises(ServiceError):
                parse_candidates({"choices": [{"message": {"content": json.dumps(payload)}}]})

    def test_candidates_fenced_json(self):
        self.assertEqual(parse_candidates({"choices": [{"message": {"content": '```json\n["a", "b", "c"]\n```'}}]}), ["a", "b", "c"])

    def test_candidates_known_text_object_variant(self):
        raw = json.dumps([{"strategy": "unused", "text": text} for text in ("a", "b", "c")])
        self.assertEqual(parse_candidates({"choices": [{"message": {"content": raw}}]}), ["a", "b", "c"])

    def test_cancelled_capture_never_uploads(self):
        cancel = threading.Event()
        cancel.set()
        with patch("desktop.service.api") as api, self.assertRaises(Cancelled):
            recognize(Image.new("RGB", (100, 100)), "test", cancel)
        api.assert_not_called()

    def test_generation_rejects_late_results_after_clear_or_new_capture(self):
        state = Generation()
        old, cancel = state.revision, state.cancel
        state.invalidate()
        self.assertTrue(cancel.is_set())
        self.assertFalse(state.current(old))
        self.assertTrue(state.current(state.revision))

    def test_no_auth_sent_to_storage(self):
        with self.assertRaises(ServiceError):
            request("https://example.aliyuncs.com/upload", key="never-forward")
        with patch("desktop.service.http.client.HTTPSConnection") as connection:
            connection.return_value.getresponse.return_value.status = 200
            connection.return_value.getresponse.return_value.read.return_value = b""
            request("https://example.aliyuncs.com/upload", method="PUT", body=b"png")
            self.assertEqual(connection.return_value.request.call_args.kwargs["headers"], {})

    def test_redirect_rejected_without_exposing_body(self):
        with patch("desktop.service.http.client.HTTPSConnection") as connection:
            connection.return_value.getresponse.return_value.status = 302
            with self.assertRaisesRegex(ServiceError, "HTTP 302"):
                request("https://mineru.net/api", key="test-only")
            connection.return_value.getresponse.return_value.read.assert_not_called()

    def test_untrusted_and_http_urls_rejected(self):
        for url in ("http://mineru.net/x", "https://localhost/x", "https://mineru.net@evil.test/x"):
            with self.subTest(url=url), self.assertRaises(ServiceError):
                request(url)

    def test_cancellation_between_draft_and_judge(self):
        cancel = threading.Event()
        def draft(*args, **kwargs):
            cancel.set()
            return {"choices": [{"message": {"content": '["a","b","c"]'}}]}
        with patch("desktop.service.api", side_effect=draft) as api, self.assertRaises(Cancelled):
            analyze([{"from": "other", "text": "hi"}], "friends", {"DEEPSEEK_API_KEY": "test"}, cancel)
        self.assertEqual(api.call_count, 1)


if __name__ == "__main__":
    unittest.main()
