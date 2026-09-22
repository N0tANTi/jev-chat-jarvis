"""DeepSeek draft -> Jev ranking smoke test using synthetic conversation only."""
import json
import os
import urllib.error
import urllib.request

from jev_client import ask
from questions import build_rank_question


def main():
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise SystemExit("DEEPSEEK_API_KEY is required")
    body = {
        "model": "deepseek-flash",
        "thinking": {"type": "disabled"},
        "messages": [
            {"role": "system", "content": "你是中文即时通讯回复助手。只输出 JSON 数组，含三条不同策略的候选回复，每条不超过40字。不编造约定之外的事实。"},
            {"role": "user", "content": "合成测试。关系：朋友。我：周六下午三点公园见。对方：好，周六三点见！请给出三条候选回复。"},
        ],
        "temperature": 0.8,
        "max_tokens": 512,
    }
    request = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"DeepSeek HTTP {exc.code}; no response body logged") from None
    content = result["choices"][0]["message"]["content"]
    candidates = json.loads(content[content.index("["):content.rindex("]") + 1])
    assert len(candidates) == 3 and all(isinstance(c, str) and c.strip() for c in candidates)
    state = {"chat": {"relationship": "friends", "latest_from": "other", "messages": [
        {"from": "me", "text": "周六下午三点公园见。"},
        {"from": "other", "text": "好，周六三点见！"},
    ]}}
    ranked = ask(state, build_rank_question(candidates))
    probabilities = ranked.get("answers", {}).get("best_reply", {}).get("probabilities", {})
    assert set(probabilities) == {"reply_a", "reply_b", "reply_c"}
    print(json.dumps({"deepseek_candidates": len(candidates), "jev_ranked": len(probabilities), "passed": True}))


if __name__ == "__main__":
    main()
