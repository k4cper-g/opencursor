"""Response parsing for XML-tagged model output."""

import re


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


def parse_response_tool_use(tool_calls: list) -> dict:
    """Parse tool_use response blocks into the standard action format.

    Converts structured tool call arguments into the same dict format
    that parse_response() returns. Used by Claude and GPT-4o adapters.
    """
    steps = []
    think = None

    for call in tool_calls:
        name = call.get("name", call.get("function", {}).get("name", ""))
        args = call.get("input", call.get("function", {}).get("arguments", {}))
        if isinstance(args, str):
            import json
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                continue

        action = {"action": name}

        if name in ("click", "double_click", "right_click"):
            if "target" in args:
                action["target"] = args["target"]
            if "x" in args and "y" in args:
                x, y = int(args["x"]), int(args["y"])
                # Convert center point to a small box
                action["box"] = [max(0, x - 5), max(0, y - 5), min(1000, x + 5), min(1000, y + 5)]

        elif name == "type":
            if "text" in args:
                action["text"] = args["text"]

        elif name == "hotkey":
            if "keys" in args:
                action["keys"] = args["keys"]

        elif name == "scroll":
            if "direction" in args:
                action["direction"] = args["direction"]
            action["amount"] = int(args.get("amount", 3))

        elif name == "drag":
            if "from_x" in args and "from_y" in args:
                fx, fy = int(args["from_x"]), int(args["from_y"])
                action["from_box"] = [max(0, fx - 5), max(0, fy - 5), min(1000, fx + 5), min(1000, fy + 5)]
            if "to_x" in args and "to_y" in args:
                tx, ty = int(args["to_x"]), int(args["to_y"])
                action["to_box"] = [max(0, tx - 5), max(0, ty - 5), min(1000, tx + 5), min(1000, ty + 5)]

        elif name == "wait":
            action["seconds"] = float(args.get("seconds", 1.0))

        elif name == "done":
            if "reason" in args:
                action["reason"] = args["reason"]

        elif name == "think":
            think = args.get("reasoning", "")
            continue

        steps.append(action)

    if not steps:
        return {"type": "single", "action": {"action": "unknown", "raw": str(tool_calls)}}

    if len(steps) == 1:
        action = steps[0]
        if think:
            action["think"] = think
        return {"type": "single", "action": action}

    return {"type": "sequence", "think": think, "steps": steps}
