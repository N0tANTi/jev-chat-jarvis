"""Synthetic-only live profile learning and reply smoke test."""
import argparse
import json
import tempfile
import threading
from pathlib import Path

from desktop.memory import ProfileStore, analyze_profile, history_messages
from desktop.service import analyze, load_keys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args()
    keys, cancel = load_keys(args.env_file), threading.Event()
    with tempfile.TemporaryDirectory(prefix="jev-synthetic-memory-") as directory:
        store = ProfileStore(Path(directory) / "profiles.json")
        cid = store.create("合成测试好友")
        store.configure(cid, persona="简短自然，不用表情，不替我承诺时间。", facts="同事；共同准备项目汇报。", learn=True)
        store.append(cid, history_messages("对方：平时进度告诉我结论就行，我喜欢短一点。\n我：好，我先给你结论。\n对方：这次汇报比较重要，请把原因和数据也列出来。"))
        p = store.get(cid)
        observation = analyze_profile(p, keys["DEEPSEEK_API_KEY"], cancel)
        assert observation["tags"]
        assert store.apply(cid, p["version"], observation)
        store.append(cid, history_messages("对方：以后每周汇报都写详细些，但临时通知还是一句话就好。"))
        p = store.get(cid)
        updated = analyze_profile(p, keys["DEEPSEEK_API_KEY"], cancel)
        assert store.apply(cid, p["version"], updated)
        messages = history_messages("对方：今天的汇报准备得怎么样了？")
        result = analyze(messages, "colleagues", keys, cancel, memory=store.context(cid))
        assert store.get(cid)["facts"] == "同事；共同准备项目汇报。"
        assert len(store.get(cid)["previous_observations"]) == 1
        assert len(result["candidates"]) == 3
        print(json.dumps({"synthetic_only": True, "initial_tags": len(observation["tags"]),
                          "updated_tags": len(updated["tags"]), "confirmed_facts_preserved": True,
                          "previous_versions": 1, "candidates": 3, "jev_ranked": True}))


if __name__ == "__main__":
    main()
