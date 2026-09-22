import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop.memory import ProfileStore, analyze_profile, history_messages
from desktop.service import Cancelled, ServiceError, analyze


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "profiles.json"
        self.store = ProfileStore(self.path)

    def test_no_disk_write_until_explicit_save(self):
        self.assertFalse(self.path.exists())

    def test_same_name_friends_remain_separate(self):
        a, b = self.store.create("同名"), self.store.create("同名")
        self.store.append(a, history_messages("对方：少放辣椒"))
        self.assertNotEqual(a, b)
        self.assertEqual(self.store.context(b)["recent_history"], [])
        self.assertEqual(self.store.get(b)["history"], [])

    def test_config_survives_restart_and_model_does_not_override_facts(self):
        cid = self.store.create("测试好友")
        self.store.configure(cid, persona="简短直接", facts="同事", learn=True)
        p = self.store.get(cid)
        self.store.apply(cid, p["version"], {"summary": "模型推测", "tags": []})
        reloaded = ProfileStore(self.path)
        self.assertEqual(reloaded.get(cid)["facts"], "同事")
        self.assertEqual(reloaded.data["persona"], "简短直接")

    def test_late_observation_rejected_after_edit_or_forget(self):
        cid = self.store.create("测试")
        version = self.store.get(cid)["version"]
        self.store.forget(cid)
        self.assertFalse(self.store.apply(cid, version, {"summary": "stale", "tags": []}))
        self.assertIsNone(self.store.get(cid)["observations"])

    def test_identical_snapshot_does_not_trigger_relearning(self):
        cid = self.store.create("测试")
        messages = history_messages("对方：你好\n我：你好\n对方：今天好吗")
        self.assertTrue(self.store.append(cid, messages))
        self.assertFalse(self.store.append(cid, messages))
        self.assertEqual(len(self.store.get(cid)["history"]), 3)

    def test_overlapping_snapshot_only_appends_new_tail(self):
        cid = self.store.create("测试")
        self.store.append(cid, history_messages("对方：一\n我：二\n对方：三"))
        self.store.append(cid, history_messages("我：二\n对方：三\n我：四"))
        self.assertEqual([m["text"] for m in self.store.get(cid)["history"]], ["一", "二", "三", "四"])

    def test_second_instance_cannot_overwrite_new_data(self):
        other = ProfileStore(self.path)
        self.store.create("first")
        with self.assertRaises(ServiceError):
            other.create("stale")
        self.assertEqual(other.data["contacts"], {})
        self.assertEqual(len(ProfileStore(self.path).data["contacts"]), 1)

    def test_atomic_write_failure_preserves_previous_file(self):
        cid = self.store.create("test")
        previous = self.path.read_bytes()
        with patch("desktop.memory.os.replace", side_effect=OSError), self.assertRaises(ServiceError):
            self.store.configure(cid, persona="new", facts="new", learn=True)
        self.assertEqual(self.path.read_bytes(), previous)
        self.assertEqual(self.store.data["persona"], "")

    def test_clear_observations_keeps_history_and_confirmed_facts(self):
        cid = self.store.create("test")
        self.store.configure(cid, persona="", facts="朋友", learn=False)
        self.store.append(cid, history_messages("对方：hello"))
        self.store.apply(cid, self.store.get(cid)["version"], {"summary": "test", "tags": []})
        self.store.forget_observations(cid)
        p = self.store.get(cid)
        self.assertEqual(p["facts"], "朋友")
        self.assertEqual(len(p["history"]), 1)
        self.assertIsNone(p["observations"])

    def test_previous_versions_bounded(self):
        cid = self.store.create("test")
        for i in range(8):
            self.store.apply(cid, self.store.get(cid)["version"], {"summary": str(i), "tags": []})
        self.assertEqual(len(self.store.get(cid)["previous_observations"]), 3)

    def test_history_format_validation(self):
        for raw in ("标题", "待确认：你好", "", "我："):
            with self.subTest(raw=raw), self.assertRaises(ServiceError):
                history_messages(raw)

    def profile_fixture(self):
        cid = self.store.create("合成好友")
        self.store.append(cid, history_messages("对方：我比较喜欢简短的回复。"))
        return self.store.get(cid)

    def test_model_tags_require_real_evidence_ids(self):
        profile = self.profile_fixture()
        invalid = {"summary": "test", "tags": [{"label": "test", "confidence": "high", "evidence_ids": ["fabricated"]}]}
        response = {"choices": [{"message": {"content": json.dumps(invalid)}}]}
        with patch("desktop.memory.api", return_value=response), self.assertRaises(ServiceError):
            analyze_profile(profile, "test", threading.Event())

    def test_valid_tag_attaches_original_evidence(self):
        profile = self.profile_fixture()
        tag = {"label": "偏好简短", "confidence": "high", "evidence_ids": [profile["history"][0]["id"]]}
        response = {"choices": [{"message": {"content": json.dumps({"summary": "偏好简短", "tags": [tag]})}}]}
        with patch("desktop.memory.api", return_value=response):
            value = analyze_profile(profile, "test", threading.Event())
        self.assertEqual(value["tags"][0]["evidence"], profile["history"])

    def test_persona_and_memory_sent_to_draft_and_judge(self):
        draft = {"choices": [{"message": {"content": '["a","b","c"]'}}]}
        judge = {"answers": {"best_reply": {"choice": "reply_a"}}}
        background = {"my_persona": "简短", "confirmed_by_user": "同事", "model_observations": None}
        with patch("desktop.service.api", side_effect=[draft, judge]) as api:
            analyze([{"from": "other", "text": "hi"}], "friends", {"DEEPSEEK_API_KEY": "test", "TYPESAFE_API_KEY": "test"}, threading.Event(), memory=background)
        payload = api.call_args_list[0].args[2]
        self.assertEqual(json.loads(payload["messages"][1]["content"])["background"], background)
        self.assertEqual(api.call_args_list[1].args[2]["state"]["background"], background)
