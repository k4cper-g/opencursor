"""Debug session management: screenshots, logs, and summaries."""

import json
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


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
