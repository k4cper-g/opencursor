"""
Visual grounding test: send a screenshot + element description to Qwen 3.5 via OpenRouter,
get back coordinates, and draw a bounding box / X on the image.
"""

import argparse
import base64
import io
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont, ImageGrab

load_dotenv()

MODEL = "qwen/qwen3.5-plus-02-15"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"

SYSTEM_PROMPT = """\
You are a visual grounding assistant. The user will give you a screenshot and describe a UI element.
Your job is to locate that element in the screenshot and return its bounding box.

Return the bounding box using the <box> format with coordinates normalized to 0-1000:
<box>(x1,y1),(x2,y2)</box>

Do not add any explanation, just the <box> tag."""


def take_screenshot() -> Image.Image:
    print("Taking screenshot...")
    img = ImageGrab.grab(all_screens=False)
    print(f"Captured {img.size[0]}x{img.size[1]} screenshot")
    return img


def encode_image(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def call_qwen(img: Image.Image, query: str) -> dict:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        sys.exit("OPENROUTER_API_KEY not set in .env")

    w, h = img.size
    b64 = encode_image(img)

    client = OpenAI(
        base_url=OPENROUTER_BASE,
        api_key=api_key,
        timeout=120,
        default_headers={
            "HTTP-Referer": "https://github.com/opencursor",
            "X-Title": "opencursor-grounding",
        },
    )

    user_content = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"},
        },
        {
            "type": "text",
            "text": f'Locate the element: "{query}"',
        },
    ]

    print(f"Sending {w}x{h} screenshot to {MODEL}...")
    print(f"Query: \"{query}\"")

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        max_tokens=256,
        temperature=0,
        extra_body={},
    )

    raw = resp.choices[0].message.content.strip()
    print(f"\nRaw response:\n{raw}\n")

    return parse_coords(raw, w, h)


def parse_coords(text: str, img_w: int, img_h: int) -> dict:
    """Try multiple strategies to extract bounding box coordinates."""

    # Strategy 1: direct JSON parse
    try:
        obj = json.loads(text)
        if all(k in obj for k in ("x1", "y1", "x2", "y2")):
            return clamp_coords(obj, img_w, img_h)
    except json.JSONDecodeError:
        pass

    # Strategy 2: find JSON in the text
    json_match = re.search(r'\{[^}]+\}', text)
    if json_match:
        try:
            obj = json.loads(json_match.group())
            if all(k in obj for k in ("x1", "y1", "x2", "y2")):
                return clamp_coords(obj, img_w, img_h)
        except json.JSONDecodeError:
            pass

    # Strategy 3: Qwen native bbox_2d format: {"bbox_2d": [x1, y1, x2, y2], ...}
    bbox_match = re.search(r'"bbox_2d"\s*:\s*\[(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\]', text)
    if bbox_match:
        x1, y1, x2, y2 = [int(v) for v in bbox_match.groups()]
        return clamp_coords({"x1": x1, "y1": y1, "x2": x2, "y2": y2}, img_w, img_h)

    # Strategy 4: Qwen box format <box>(x1,y1),(x2,y2)</box> — normalized 0-1000
    box_match = re.search(r'<box>\((\d+),(\d+)\),\((\d+),(\d+)\)</box>', text)
    if box_match:
        vals = [int(v) for v in box_match.groups()]
        return clamp_coords({
            "x1": int(vals[0] / 1000 * img_w),
            "y1": int(vals[1] / 1000 * img_h),
            "x2": int(vals[2] / 1000 * img_w),
            "y2": int(vals[3] / 1000 * img_h),
        }, img_w, img_h)

    # Strategy 4: look for 4 numbers in sequence
    nums = re.findall(r'(\d+\.?\d*)', text)
    if len(nums) >= 4:
        vals = [float(v) for v in nums[:4]]
        # If all values <= 1, treat as normalized 0-1
        if all(v <= 1.0 for v in vals):
            return clamp_coords({
                "x1": int(vals[0] * img_w),
                "y1": int(vals[1] * img_h),
                "x2": int(vals[2] * img_w),
                "y2": int(vals[3] * img_h),
            }, img_w, img_h)
        # If all values <= 1000 and image is bigger, assume 0-1000 normalized
        if all(v <= 1000 for v in vals) and (img_w > 1000 or img_h > 1000):
            return clamp_coords({
                "x1": int(vals[0] / 1000 * img_w),
                "y1": int(vals[1] / 1000 * img_h),
                "x2": int(vals[2] / 1000 * img_w),
                "y2": int(vals[3] / 1000 * img_h),
            }, img_w, img_h)
        return clamp_coords({
            "x1": int(vals[0]), "y1": int(vals[1]),
            "x2": int(vals[2]), "y2": int(vals[3]),
        }, img_w, img_h)

    sys.exit(f"Could not parse coordinates from response:\n{text}")


def clamp_coords(c: dict, w: int, h: int) -> dict:
    return {
        "x1": max(0, min(int(c["x1"]), w)),
        "y1": max(0, min(int(c["y1"]), h)),
        "x2": max(0, min(int(c["x2"]), w)),
        "y2": max(0, min(int(c["y2"]), h)),
    }


def draw_result(img: Image.Image, coords: dict, query: str) -> str:
    img = img.convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    x1, y1, x2, y2 = coords["x1"], coords["y1"], coords["x2"], coords["y2"]
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

    # Semi-transparent red fill
    draw.rectangle([x1, y1, x2, y2], fill=(255, 0, 0, 40))

    # Solid red border (3px)
    for i in range(3):
        draw.rectangle([x1 - i, y1 - i, x2 + i, y2 + i], outline=(255, 0, 0, 220))

    # X crosshair at center
    arm = min(x2 - x1, y2 - y1) // 4
    draw.line([(cx - arm, cy - arm), (cx + arm, cy + arm)], fill=(255, 0, 0, 255), width=3)
    draw.line([(cx + arm, cy - arm), (cx - arm, cy + arm)], fill=(255, 0, 0, 255), width=3)

    # Label
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except OSError:
        font = ImageFont.load_default()

    label = f'"{query}" \u2192 ({cx}, {cy})'
    label_y = max(0, y1 - 24)
    draw.rectangle([x1, label_y, x1 + len(label) * 10, label_y + 20], fill=(255, 0, 0, 200))
    draw.text((x1 + 4, label_y + 2), label, fill=(255, 255, 255, 255), font=font)

    result = Image.alpha_composite(img, overlay).convert("RGB")

    out_dir = Path(__file__).resolve().parent / "output"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"ground_{stamp}.png"
    result.save(str(out_path))
    return str(out_path)


def main():
    parser = argparse.ArgumentParser(description="Test Qwen visual grounding via OpenRouter")
    parser.add_argument("query", help='Element to locate, e.g. "search bar"')
    parser.add_argument("-i", "--image", help="Path to screenshot (default: capture screen)", default=None)
    parser.add_argument("-d", "--delay", type=float, default=0, help="Seconds to wait before capturing")
    args = parser.parse_args()

    if args.image:
        if not Path(args.image).exists():
            sys.exit(f"Image not found: {args.image}")
        img = Image.open(args.image)
        print(f"Loaded {img.size[0]}x{img.size[1]} from {args.image}")
    else:
        if args.delay > 0:
            import time
            print(f"Waiting {args.delay}s...")
            time.sleep(args.delay)
        img = take_screenshot()

    coords = call_qwen(img, args.query)
    print(f"Bounding box: ({coords['x1']}, {coords['y1']}) \u2192 ({coords['x2']}, {coords['y2']})")
    cx, cy = (coords["x1"] + coords["x2"]) // 2, (coords["y1"] + coords["y2"]) // 2
    print(f"Click point:  ({cx}, {cy})")

    out = draw_result(img, coords, args.query)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
