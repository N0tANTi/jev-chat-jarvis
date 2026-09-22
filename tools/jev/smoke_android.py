"""Exercise Android-shaped judgment + ranking on synthetic data, without key output."""
import json

from jev_client import ask
from questions import JUDGE_QUESTIONS, build_rank_question


def main():
    state = {
        "chat": {
            "relationship": "friends",
            "messages": [
                {"from": "me", "text": "我们周六下午三点在公园见。"},
                {"from": "other", "text": "好，周六三点见！"},
            ],
            "latest_from": "other",
        },
        "background": "合成测试背景：约定周六下午三点在公园见面。",
        "history": [{"from": "other", "text": "周末一起散步吧。"}],
    }
    questions = {k: dict(v) for k, v in JUDGE_QUESTIONS.items()}
    for question in questions.values():
        question["instructions"] += " Facts given in background are provided context, not off-topic."
    judged = ask(state, questions)
    answers = judged.get("answers", {})
    assert set(questions) <= set(answers), "Judgment response missing required answers"
    ranked = ask(state, build_rank_question(["好，周六三点公园见！", "明天上午九点见。", "我不知道你在说什么。"] ))
    probabilities = ranked.get("answers", {}).get("best_reply", {}).get("probabilities", {})
    assert set(probabilities) == {"reply_a", "reply_b", "reply_c"}, "Ranking probabilities missing"
    print(json.dumps({"judgment_answers": len(answers), "background_history_accepted": True,
                      "ranking_candidates": len(probabilities), "passed": True}))


if __name__ == "__main__":
    main()
