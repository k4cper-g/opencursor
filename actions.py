"""Action execution via pyautogui."""

import time

import pyautogui

# Safety: pyautogui will raise an exception if the mouse moves to a corner
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.3


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
        pyautogui.moveTo(cx, cy, duration=0.4)
        if name == "click":
            pyautogui.click()
        elif name == "double_click":
            pyautogui.doubleClick()
        elif name == "right_click":
            pyautogui.rightClick()
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
        pyautogui.moveTo(fx, fy, duration=0.4)
        time.sleep(0.15)
        pyautogui.mouseDown()
        try:
            time.sleep(0.15)
            pyautogui.moveTo(tx, ty, duration=0.5)
        finally:
            pyautogui.mouseUp()
        return f"drag from ({fx},{fy}) to ({tx},{ty})"

    elif name == "wait":
        seconds = action.get("seconds", 1.0)
        time.sleep(seconds)
        return f"waited {seconds}s"

    elif name == "done":
        return f"DONE: {action.get('reason', 'task complete')}"

    return f"unknown action: {name}"
