"""Explicit, synthetic-only live API verification. Never captures the screen."""
import argparse
import json
import threading
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from desktop.service import analyze, load_keys, parse_transcript, recognize, to_transcript

TEXTS = ["你今天怎么都不理我？", "刚才在开会，现在忙完了。", "那晚上一起吃饭吗？"]


def synthetic_image():
    image = Image.new("RGB", (900, 520), "#ededed")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 24)
    for i, text in enumerate(TEXTS):
        x, y = (320 if i == 1 else 60), 65 + i * 140
        draw.rounded_rectangle((x, y, x + 510, y + 70), radius=10,
                               fill="#95ec69" if i == 1 else "white")
        draw.text((x + 16, y + 18), text, font=font, fill="black")
    return image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args()
    keys, cancel = load_keys(args.env_file), threading.Event()
    image = synthetic_image()
    started = time.monotonic()
    content = recognize(image, keys["MINERU_API_TOKEN"], cancel, lambda text: print(text, flush=True))
    ocr_seconds = round(time.monotonic() - started, 2)
    transcript = to_transcript(content, image)
    messages = parse_transcript(transcript)
    assert [m["text"] for m in messages] == TEXTS, "Synthetic OCR text mismatch"
    assert [m["from"] for m in messages] == ["other", "me", "other"], "Synthetic OCR side mismatch"
    result = analyze(messages, "friends", keys, cancel, lambda text: print(text, flush=True))
    assert len(result["candidates"]) == 3
    assert 0 <= result["best_index"] < 3
    print(json.dumps({"synthetic_only": True, "ocr_texts_correct": 3, "ocr_sides_correct": 3,
                      "candidates": 3, "jev_ranked": True, "ocr_seconds": ocr_seconds,
                      "total_seconds": round(time.monotonic() - started, 2)}))


if __name__ == "__main__":
    main()
