"""
Autonomous computer-use agent: give it a high-level goal and it will
observe the screen, decide what to do, and execute actions until done.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import pyautogui
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError
from PIL import Image, ImageDraw, ImageFont, ImageGrab

from ground import encode_image

load_dotenv()

MODEL = "qwen/qwen3.5-plus-02-15"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"

# Safety: pyautogui will raise an exception if the mouse moves to a corner
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.3

SYSTEM_PROMPT = """\
You are an autonomous computer-use agent. You can see the user's screen and \
control their mouse and keyboard to accomplish a goal.

On each turn you will receive a screenshot of the current screen and a log of \
your previous actions. Use the action log to track progress and avoid repeating \
failed actions. Decide the best next action (or a short sequence of blind-safe \
actions) to take toward the goal, then output it in the format described below.

## Available actions

### click — left-click on a UI element
<think>your reasoning</think>
<action>click</action>
<target>description of element</target>
<box>(x1,y1),(x2,y2)</box>

### double_click — double-click on a UI element
<think>your reasoning</think>
<action>double_click</action>
<target>description of element</target>
<box>(x1,y1),(x2,y2)</box>

### right_click — right-click on a UI element
<think>your reasoning</think>
<action>right_click</action>
<target>description of element</target>
<box>(x1,y1),(x2,y2)</box>

### type — type text at the current cursor position
<think>your reasoning</think>
<action>type</action>
<text>the text to type</text>

### hotkey — press a keyboard shortcut
<think>your reasoning</think>
<action>hotkey</action>
<keys>ctrl+c</keys>

### scroll — scroll the mouse wheel
<think>your reasoning</think>
<action>scroll</action>
<direction>down</direction>
<amount>3</amount>

### drag — drag from one point to another
<think>your reasoning</think>
<action>drag</action>
<from><box>(x1,y1),(x2,y2)</box></from>
<to><box>(x1,y1),(x2,y2)</box></to>

### wait — pause before the next action
<think>your reasoning</think>
<action>wait</action>
<seconds>2</seconds>

### done — the goal has been accomplished
<think>your reasoning</think>
<action>done</action>
<reason>explain why the task is complete</reason>

## Sequencing

You may output a SINGLE action OR a SEQUENCE of actions.

Use a sequence when the follow-up actions do NOT depend on new visual state — \
for example, clicking a text field, typing a query, and pressing Enter. These \
"blind-safe" chains save time because no screenshot is taken between steps.

Do NOT sequence actions where a later step depends on seeing the result of an \
earlier one (e.g. clicking a dropdown then selecting an option — you need to \
see the menu first).

### Single action (same as above)
<think>your reasoning</think>
<action>click</action>
<target>description</target>
<box>(x1,y1),(x2,y2)</box>

### Sequence of actions
<think>your reasoning for the full sequence</think>
<sequence>
<step>
<action>click</action>
<target>description</target>
<box>(x1,y1),(x2,y2)</box>
</step>
<step>
<action>type</action>
<text>hello world</text>
</step>
<step>
<action>hotkey</action>
<keys>enter</keys>
</step>
</sequence>

## Rules
- Output exactly ONE action or ONE sequence per turn.
- Always include <think> before your action/sequence to explain your reasoning.
- Your <box> coordinates are used DIRECTLY to control the mouse — they must \
be precise. For click/double_click/right_click, you MUST visually ground the \
element in your <think> tag before writing <box>: describe the element's exact \
position on screen, its size, and its spatial relationship to surrounding \
elements. For small elements like icons, buttons, or checkboxes, be extra \
careful — zoom in mentally and estimate the tight bounding box around just \
that element, not the surrounding area.
- Write a detailed <target> description that includes the element's visual \
appearance, label/text, and location on screen (e.g. "the small gear icon in \
the top-right corner of the settings panel" not just "settings").
- For click/double_click/right_click/drag, you MUST include <box> coordinates \
normalized to 0-1000 (Qwen visual grounding format).
- For hotkey, separate keys with + (e.g. ctrl+shift+s, alt+f4, enter).
- Only use sequences for blind-safe chains. When in doubt, use a single action.
- Do not explain anything outside the XML tags.
"""


class DebugSession:
    """Manages a per-run debug directory with screenshots and logs."""

    def __init__(self, goal: str):
        root = Path(__file__).resolve().parent / "debug"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.dir = root / stamp
        self.dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.dir / "session.log"
        self.steps: list[dict] = []
        self._write_log(f"Session started: {stamp}\nGoal: {goal}\n")

    def _write_log(self, text: str):
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(text)

    def save_screenshot(self, img: Image.Image, step: int, actions: list[dict] | None = None) -> Path:
        """Save a screenshot, optionally with bounding boxes drawn on it."""
        annotated = img.copy().convert("RGBA")
        if actions:
            overlay = Image.new("RGBA", annotated.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            w, h = img.size
            for act in actions:
                box = act.get("box")
                if not box:
                    continue
                x1 = int(box[0] / 1000 * w)
                y1 = int(box[1] / 1000 * h)
                x2 = int(box[2] / 1000 * w)
                y2 = int(box[3] / 1000 * h)
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                # Semi-transparent fill + border
                draw.rectangle([x1, y1, x2, y2], fill=(255, 0, 0, 40))
                for i in range(2):
                    draw.rectangle([x1 - i, y1 - i, x2 + i, y2 + i], outline=(255, 0, 0, 200))
                # Crosshair
                arm = max(6, min(x2 - x1, y2 - y1) // 4)
                draw.line([(cx - arm, cy - arm), (cx + arm, cy + arm)], fill=(255, 0, 0, 255), width=2)
                draw.line([(cx + arm, cy - arm), (cx - arm, cy + arm)], fill=(255, 0, 0, 255), width=2)
                # Label
                label = act.get("target", act.get("action", ""))
                if label:
                    try:
                        font = ImageFont.truetype("arial.ttf", 14)
                    except OSError:
                        font = ImageFont.load_default()
                    label_y = max(0, y1 - 20)
                    draw.rectangle([x1, label_y, x1 + len(label) * 8 + 8, label_y + 18], fill=(255, 0, 0, 180))
                    draw.text((x1 + 4, label_y + 2), label, fill=(255, 255, 255, 255), font=font)
            annotated = Image.alpha_composite(annotated, overlay)

        out = self.dir / f"step_{step:03d}.png"
        annotated.convert("RGB").save(str(out))
        return out

    def log_step(self, step: int, *, raw_response: str, think: str | None,
                 parsed: dict, results: list[str], usage: dict | None = None):
        """Append a structured entry to the session log and save raw JSON."""
        entry = {
            "step": step,
            "think": think,
            "parsed": parsed,
            "results": results,
            "usage": usage,
        }
        self.steps.append(entry)

        # Human-readable log
        lines = [
            f"\n{'='*60}",
            f"Step {step}",
            f"{'='*60}",
        ]
        if think:
            lines.append(f"Reasoning: {think}")
        lines.append(f"Parsed: {json.dumps(parsed, indent=2)}")
        for r in results:
            lines.append(f"Result: {r}")
        if usage:
            lines.append(f"Tokens: {usage}")
        lines.append("")
        self._write_log("\n".join(lines))

        # Save raw model output
        raw_path = self.dir / f"step_{step:03d}_raw.txt"
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(raw_response)

    def finalize(self, reason: str):
        """Write the final summary."""
        summary = {
            "total_steps": len(self.steps),
            "end_reason": reason,
            "steps": self.steps,
        }
        with open(self.dir / "summary.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        self._write_log(f"\nSession ended: {reason}\n")


def build_client() -> OpenAI:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        sys.exit("OPENROUTER_API_KEY not set in .env")
    return OpenAI(
        base_url=OPENROUTER_BASE,
        api_key=api_key,
        timeout=120,
        default_headers={
            "HTTP-Referer": "https://github.com/opencursor",
            "X-Title": "opencursor-agent",
        },
    )



def take_screenshot():
    img = ImageGrab.grab(all_screens=False)
    return img



def extract_tag(text: str, tag: str) -> str | None:
    """Extract content from an XML tag, tolerating missing closing tags."""
    # Try with closing tag first
    m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Fallback: grab everything after the opening tag (model didn't close it)
    m = re.search(rf"<{tag}>\s*(.*)", text, re.DOTALL)
    if m:
        # Take just the first line of content to avoid grabbing other tags
        content = m.group(1).strip().split("\n")[0].strip()
        # Strip any trailing tags that might have been captured
        content = re.sub(r"<.*", "", content).strip()
        if content:
            return content
    return None


def extract_box(text: str) -> list | None:
    """Extract box coordinates, tolerating unclosed tags and missing parens."""
    # Strict: <box>(x1,y1),(x2,y2)</box>
    m = re.search(r"<box>\((\d+),(\d+)\),\((\d+),(\d+)\)</box>", text)
    if m:
        return [int(v) for v in m.groups()]
    # Tolerant: <box> followed by 4 numbers anywhere
    m = re.search(r"<box>[^\d]*(\d+)\D+(\d+)\D+(\d+)\D+(\d+)", text)
    if m:
        return [int(v) for v in m.groups()]
    return None


def parse_action(text: str) -> dict:
    """Parse the model's XML-tagged action response."""
    action = extract_tag(text, "action")
    if not action:
        return {"action": "unknown", "raw": text}

    result = {"action": action}

    think = extract_tag(text, "think")
    if think:
        result["think"] = think

    if action in ("click", "double_click", "right_click"):
        target = extract_tag(text, "target")
        if target:
            result["target"] = target
        box = extract_box(text)
        if box:
            result["box"] = box

    elif action == "type":
        typed = extract_tag(text, "text")
        if typed:
            result["text"] = typed

    elif action == "hotkey":
        keys = extract_tag(text, "keys")
        if keys:
            result["keys"] = keys

    elif action == "scroll":
        direction = extract_tag(text, "direction")
        amount = extract_tag(text, "amount")
        if direction:
            result["direction"] = direction
        result["amount"] = int(amount) if amount else 3

    elif action == "drag":
        from_m = re.search(r"<from>(.*?)</from>", text, re.DOTALL)
        to_m = re.search(r"<to>(.*?)</to>", text, re.DOTALL)
        if not to_m:
            # Tolerant: split on <to> without closing tag
            to_m = re.search(r"<to>(.*)", text, re.DOTALL)
        if from_m:
            box = extract_box(from_m.group(0))
            if box:
                result["from_box"] = box
        if to_m:
            box = extract_box(to_m.group(0))
            if box:
                result["to_box"] = box

    elif action == "wait":
        seconds = extract_tag(text, "seconds")
        result["seconds"] = float(seconds) if seconds else 1.0

    elif action == "done":
        reason = extract_tag(text, "reason")
        if reason:
            result["reason"] = reason

    return result


def parse_response(text: str) -> dict:
    """Parse the model response, returning either a single action or a sequence.

    Returns:
        {"type": "single", "action": {...}} or
        {"type": "sequence", "think": "...", "steps": [{...}, ...]}
    """
    # Check for <sequence> block
    seq_match = re.search(r"<sequence>(.*?)</sequence>", text, re.DOTALL)
    if seq_match:
        think = extract_tag(text, "think")
        steps_raw = re.findall(r"<step>(.*?)</step>", seq_match.group(1), re.DOTALL)
        steps = []
        for step_text in steps_raw:
            action = parse_action(step_text)
            if action["action"] != "unknown":
                steps.append(action)
        if steps:
            return {"type": "sequence", "think": think, "steps": steps}

    # Fall back to single action
    action = parse_action(text)
    return {"type": "single", "action": action}


def box_to_center(box: list, img_w: int, img_h: int) -> tuple:
    """Convert a 0-1000 normalized box to pixel center coordinates."""
    x1 = int(box[0] / 1000 * img_w)
    y1 = int(box[1] / 1000 * img_h)
    x2 = int(box[2] / 1000 * img_w)
    y2 = int(box[3] / 1000 * img_h)
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    return cx, cy


def execute_action(action: dict, img_w: int, img_h: int) -> str:
    """Execute a parsed action. Returns a description of what was done."""
    name = action["action"]

    if name in ("click", "double_click", "right_click"):
        if "box" not in action:
            return f"ERROR: {name} action missing <box> coordinates"
        cx, cy = box_to_center(action["box"], img_w, img_h)
        target = action.get("target", "element")
        if name == "click":
            pyautogui.click(cx, cy)
        elif name == "double_click":
            pyautogui.doubleClick(cx, cy)
        elif name == "right_click":
            pyautogui.rightClick(cx, cy)
        return f"{name} on '{target}' at ({cx}, {cy})"

    elif name == "type":
        text = action.get("text", "")
        if not text:
            return "ERROR: type action missing <text>"
        pyautogui.typewrite(text, interval=0.02) if text.isascii() else pyautogui.write(text)
        return f"typed '{text[:50]}{'...' if len(text) > 50 else ''}'"

    elif name == "hotkey":
        keys_str = action.get("keys", "")
        if not keys_str:
            return "ERROR: hotkey action missing <keys>"
        keys = [k.strip() for k in keys_str.split("+")]
        pyautogui.hotkey(*keys)
        return f"hotkey {'+'.join(keys)}"

    elif name == "scroll":
        direction = action.get("direction", "down")
        amount = action.get("amount", 3)
        clicks = amount if direction in ("down", "right") else -amount
        if direction in ("up", "down"):
            pyautogui.scroll(-clicks)  # pyautogui: negative = down
        else:
            pyautogui.hscroll(clicks)
        return f"scroll {direction} {amount}"

    elif name == "drag":
        if "from_box" not in action or "to_box" not in action:
            return "ERROR: drag action missing <from> or <to> boxes"
        fx, fy = box_to_center(action["from_box"], img_w, img_h)
        tx, ty = box_to_center(action["to_box"], img_w, img_h)
        pyautogui.moveTo(fx, fy)
        pyautogui.drag(tx - fx, ty - fy, duration=0.5)
        return f"drag from ({fx},{fy}) to ({tx},{ty})"

    elif name == "wait":
        seconds = action.get("seconds", 1.0)
        time.sleep(seconds)
        return f"waited {seconds}s"

    elif name == "done":
        return f"DONE: {action.get('reason', 'task complete')}"

    return f"unknown action: {name}"



def run_agent(goal: str, max_steps: int = 30, step_delay: float = 1.5, debug: bool = False):
    client = build_client()
    dbg = DebugSession(goal) if debug else None
    if dbg:
        print(f"Debug session: {dbg.dir}")

    print(f"Goal: {goal}")
    print(f"Max steps: {max_steps}")
    print(f"Failsafe: move mouse to any corner to abort\n")

    # Initial screenshot
    img = take_screenshot()
    w, h = img.size
    print(f"Screen: {w}x{h}")

    # Text-based action log replaces screenshot history
    action_log: list[str] = []

    for step in range(1, max_steps + 1):
        print(f"\n{'='*60}")
        print(f"Step {step}/{max_steps}")
        print(f"{'='*60}")

        # Build prompt from scratch each step: system + (screenshot + goal + action log)
        user_text = f"Goal: {goal}"
        if action_log:
            user_text += "\n\nCompleted actions:\n" + "\n".join(action_log)
        user_text += "\n\nHere is the current screenshot. What is your next action?"

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encode_image(img)}"}},
                    {"type": "text", "text": user_text},
                ],
            },
        ]

        # Ask model for next action (retry on rate limit)
        print(f"Sending prompt with {len(action_log)} logged actions")
        resp = None
        for attempt in range(3):
            try:
                resp = client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    max_tokens=4096,
                    temperature=0,
                    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                )
                break
            except RateLimitError:
                wait = 2 ** (attempt + 1)  # 2s, 4s, 8s
                print(f"Rate limited (attempt {attempt + 1}/3), waiting {wait}s...")
                time.sleep(wait)
        if resp is None:
            sys.exit("Aborted: rate limited after 3 retries")

        choice = resp.choices[0]
        raw = choice.message.content.strip() if choice.message.content else ""
        # Check for hidden reasoning content
        reasoning = getattr(choice.message, "reasoning_content", None) or getattr(choice.message, "reasoning", None)
        usage = resp.usage

        print(f"\n--- DEBUG ---")
        print(f"Finish reason: {choice.finish_reason}")
        if usage:
            print(f"Tokens — prompt: {usage.prompt_tokens}, completion: {usage.completion_tokens}, total: {usage.total_tokens}")
        if reasoning:
            print(f"Hidden reasoning ({len(reasoning)} chars):\n{reasoning}")
        print(f"Response length: {len(raw)} chars")
        print(f"Full response:\n{raw}")
        print(f"--- END DEBUG ---\n")

        # Parse and execute (single action or sequence)
        parsed = parse_response(raw)

        if parsed["type"] == "sequence":
            steps = parsed["steps"]
            think = parsed.get("think")
            if think:
                print(f"Think: {think[:300]}")
            print(f"Executing sequence of {len(steps)} actions")

            # Debug: save screenshot with all boxes from the sequence
            if dbg:
                dbg.save_screenshot(img, step, actions=steps)

            done_flag = False
            seq_results = []
            for i, act in enumerate(steps):
                if act["action"] == "done":
                    print(f"\n*** DONE: {act.get('reason', 'task complete')} ***")
                    done_flag = True
                    break
                result = execute_action(act, w, h)
                print(f"  [{i+1}/{len(steps)}] {result}")
                seq_results.append(result)
                if result.startswith("ERROR"):
                    print(f"  Sequence aborted due to error at step {i+1}")
                    break
                # Short delay between steps so the UI can react
                if i < len(steps) - 1:
                    time.sleep(0.3)

            action_log.append(f"Step {step}: sequence [{', '.join(seq_results)}]")

            if dbg:
                usage_dict = {"prompt": usage.prompt_tokens, "completion": usage.completion_tokens, "total": usage.total_tokens} if usage else None
                dbg.log_step(step, raw_response=raw, think=think, parsed=parsed, results=seq_results, usage=usage_dict)

            if done_flag:
                if dbg:
                    dbg.finalize("done")
                break

        else:
            action = parsed["action"]
            print(f"Parsed action: {action}")
            if "think" in action:
                print(f"Think: {action['think'][:300]}")

            if action["action"] == "done":
                print(f"\n*** DONE: {action.get('reason', 'task complete')} ***")
                if dbg:
                    usage_dict = {"prompt": usage.prompt_tokens, "completion": usage.completion_tokens, "total": usage.total_tokens} if usage else None
                    dbg.log_step(step, raw_response=raw, think=action.get("think"), parsed=parsed, results=["done"], usage=usage_dict)
                    dbg.finalize("done")
                break

            if action["action"] == "unknown":
                print(f"WARNING: Could not parse action, retrying...")
                action_log.append(f"Step {step}: [parse error — retrying]")
                if dbg:
                    dbg.log_step(step, raw_response=raw, think=None, parsed=parsed, results=["parse error"])
                continue

            # Debug: save screenshot with this action's box
            if dbg:
                dbg.save_screenshot(img, step, actions=[action])

            result = execute_action(action, w, h)
            print(f"Executed: {result}")

            if dbg:
                usage_dict = {"prompt": usage.prompt_tokens, "completion": usage.completion_tokens, "total": usage.total_tokens} if usage else None
                dbg.log_step(step, raw_response=raw, think=action.get("think"), parsed=parsed, results=[result], usage=usage_dict)

            if result.startswith("ERROR"):
                action_log.append(f"Step {step}: {result}")
                continue

            action_log.append(f"Step {step}: {result}")

        # Wait for UI to update, then take new screenshot
        time.sleep(step_delay)
        img = take_screenshot()
        w, h = img.size

    else:
        print(f"\n*** Reached max steps ({max_steps}) without completion ***")
        if dbg:
            dbg.finalize("max_steps")


def main():
    parser = argparse.ArgumentParser(description="Autonomous computer-use agent powered by Qwen vision")
    parser.add_argument("goal", help='Goal to accomplish, e.g. "open notepad and type hello world"')
    parser.add_argument("--max-steps", type=int, default=30, help="Maximum number of actions (default: 30)")
    parser.add_argument("--step-delay", type=float, default=1.5, help="Seconds to wait between actions (default: 1.5)")
    parser.add_argument("--no-gui", action="store_true", help="Run in terminal mode without GUI overlay")
    parser.add_argument("--debug", action="store_true", help="Save screenshots, reasoning, and logs to debug/<session>/")
    args = parser.parse_args()

    if args.no_gui:
        run_agent(args.goal, max_steps=args.max_steps, step_delay=args.step_delay, debug=args.debug)
    else:
        from overlay import AgentOverlay

        overlay = AgentOverlay(title=f"OpenCursor \u2014 {args.goal[:50]}")
        overlay.redirect_output()
        overlay.set_status(f"Goal: {args.goal[:80]}")
        overlay.run_in_background(run_agent, args.goal, args.max_steps, args.step_delay, debug=args.debug)
        overlay.mainloop()


if __name__ == "__main__":
    main()
