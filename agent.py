"""
Autonomous computer-use agent: give it a high-level goal and it will
observe the screen, decide what to do, and execute actions until done.
"""

from __future__ import annotations

import argparse
import time

from actions import execute_action
from config import load_config
from debug_session import DebugSession
from adapters import get_adapter
from events import AgentEvent, AgentEventBus, EventType
from prompts import build_system_prompt
from screenshot import take_screenshot, screenshots_are_similar


def run_agent(goal: str, config: dict, event_bus: AgentEventBus | None = None):
    adapter = get_adapter(config["model"])
    client = adapter.build_client(config)
    system_prompt = build_system_prompt(adapter.get_prompt_overrides())

    max_steps = config.get("max_steps", 30)
    step_delay = config.get("step_delay", 1.5)
    debug = config.get("debug", False)

    # --- Helpers for event emission and controls ---

    def emit(event_type, step=None, message=None, **data):
        if event_bus:
            event_bus.emit(AgentEvent(type=event_type, step=step, message=message, data=data))

    def check_controls() -> bool:
        """Check pause/stop. Returns False if agent should exit."""
        if not event_bus:
            return True
        if event_bus.stop_requested:
            print("\n*** Agent stopped by user ***")
            emit(EventType.AGENT_FINISHED, message="stopped_by_user")
            return False
        event_bus.check_pause()  # blocks if paused
        return not event_bus.stop_requested

    def make_reasoning_callback(step_num):
        """Create a per-step callback for streaming reasoning tokens."""
        if not event_bus:
            return None
        def on_reasoning(delta: str, accumulated: str):
            emit(EventType.STEP_LLM_REASONING_DELTA, step=step_num,
                 delta=delta, accumulated=accumulated)
        return on_reasoning

    def live(key: str, default):
        """Read a live-adjustable setting, falling back to config."""
        if event_bus:
            return event_bus.get_live_setting(key, default)
        return default

    def print_cost_summary():
        if totals["steps"] == 0:
            return
        total_tokens = totals["prompt"] + totals["completion"]
        print(f"\n{'─'*40}")
        print(f"Token usage  — in: {totals['prompt']:,}  out: {totals['completion']:,}  total: {total_tokens:,}")
        if totals["cost"] > 0:
            print(f"Est. cost    — ${totals['cost']:.4f}")
        else:
            print(f"Est. cost    — n/a (no pricing for this model)")
        print(f"LLM calls    — {totals['steps']}")
        print(f"{'─'*40}")

    # --- Setup ---

    dbg = DebugSession(goal)
    print(f"Session log: {dbg.dir}")
    if debug:
        print(f"Debug images enabled")

    emit(EventType.AGENT_STARTED,
         goal=goal, model=config["model"],
         model_id=config.get("model_id"), max_steps=max_steps)

    print(f"Goal: {goal}")
    print(f"Model: {config['model']}" + (f" ({config['model_id']})" if config.get("model_id") else ""))
    print(f"Max steps: {max_steps}")
    print(f"Failsafe: move mouse to any corner to abort\n")

    # Initial screenshot
    img = take_screenshot()
    w, h = img.size
    print(f"Screen: {w}x{h}")
    emit(EventType.STEP_SCREENSHOT_TAKEN, step=0, screenshot=img, width=w, height=h)

    # Text-based action log replaces screenshot history
    action_log: list[str] = []

    # Loop detection: track consecutive unchanged screenshots
    prev_img = img
    unchanged_count = 0

    # Token / cost accumulator
    totals = {"prompt": 0, "completion": 0, "cost": 0.0, "steps": 0}

    for step in range(1, max_steps + 1):
        # Check pause/stop between steps
        if not check_controls():
            print_cost_summary()
            dbg.finalize("stopped_by_user")
            break

        # Re-read live settings each iteration
        current_max_steps = live("max_steps", max_steps)
        if step > current_max_steps:
            print(f"\n*** Reached max steps ({current_max_steps}) without completion ***")
            print_cost_summary()
            emit(EventType.AGENT_FINISHED, message="max_steps")
            dbg.finalize("max_steps")
            break

        emit(EventType.STEP_STARTED, step=step, message=f"Step {step}/{current_max_steps}")

        print(f"\n{'='*60}")
        print(f"Step {step}/{current_max_steps}")
        print(f"{'='*60}")

        # Build user message
        user_text = f"Goal: {goal}"
        if action_log:
            user_text += "\n\nCompleted actions:\n" + "\n".join(action_log)

        # Loop detection: warn the model when the screen hasn't changed
        if unchanged_count >= 2:
            print(f"  ⚠ Screen unchanged for {unchanged_count} consecutive actions")
            user_text += (
                f"\n\n⚠ WARNING: The screen has NOT changed for {unchanged_count} "
                f"consecutive actions. Your recent actions had no visible effect. "
                f"You MUST try a completely different approach — for example:\n"
                f"- Use double_click instead of click\n"
                f"- Try a keyboard shortcut (e.g. Enter to play, Space to toggle)\n"
                f"- Click a different UI element (e.g. a play button instead of the track name)\n"
                f"- Scroll to reveal new elements\n"
                f"Do NOT repeat the same action again."
            )

        user_text += "\n\nHere is the current screenshot. What is your next action?"

        # Call model (adapter handles API specifics, parsing, retries)
        emit(EventType.STEP_LLM_CALL_STARTED, step=step)
        print(f"Sending prompt with {len(action_log)} logged actions")
        response = adapter.call(client, system_prompt, user_text, img, config,
                                on_reasoning=make_reasoning_callback(step))

        raw = response["raw"]
        parsed = response["parsed"]
        think = response.get("think")

        usage = response.get("usage")
        step_cost = adapter.estimate_cost(usage)

        if usage:
            totals["prompt"] += usage.get("prompt", 0)
            totals["completion"] += usage.get("completion", 0)
            totals["steps"] += 1
            if step_cost:
                totals["cost"] += step_cost
            cost_str = f"  (${step_cost:.4f} / total ${totals['cost']:.4f})" if step_cost else ""
            print(f"Tokens — in: {usage.get('prompt', '?'):,}  out: {usage.get('completion', '?'):,}{cost_str}")

        emit(EventType.STEP_LLM_CALL_FINISHED, step=step,
             raw=raw, parsed=parsed, think=think, usage=usage,
             step_cost=step_cost, total_cost=totals["cost"])

        # Check stop after (potentially long) LLM call
        if not check_controls():
            print_cost_summary()
            dbg.finalize("stopped_by_user")
            break

        if parsed["type"] == "sequence":
            steps_list = parsed["steps"]
            seq_think = parsed.get("think")
            if seq_think:
                print(f"Think: {seq_think[:300]}")
            print(f"Executing sequence of {len(steps_list)} actions")

            if debug:
                dbg.save_screenshot(img, step, actions=steps_list)

            done_flag = False
            done_reason = ""
            seq_results = []
            for i, act in enumerate(steps_list):
                # Check stop between sequence actions
                if not check_controls():
                    break
                if act["action"] == "done":
                    done_reason = act.get("reason", "task complete")
                    print(f"\n*** DONE: {done_reason} ***")
                    done_flag = True
                    break
                result = execute_action(act, w, h)
                print(f"  [{i+1}/{len(steps_list)}] {result}")
                emit(EventType.STEP_ACTION_EXECUTED, step=step,
                     message=f"[{i+1}/{len(steps_list)}] {result}", action=act)
                seq_results.append(result)
                if result.startswith("ERROR"):
                    print(f"  Sequence aborted due to error at step {i+1}")
                    break
                if i < len(steps_list) - 1:
                    time.sleep(0.3)

            action_log.append(f"Step {step}: sequence [{', '.join(seq_results)}]")

            dbg.log_step(step, raw_response=raw, think=seq_think, parsed=parsed,
                         results=seq_results, usage=response.get("usage"))

            # Break outer loop if stopped mid-sequence
            if event_bus and event_bus.stop_requested:
                print_cost_summary()
                dbg.finalize("stopped_by_user")
                break

            if done_flag:
                print_cost_summary()
                emit(EventType.AGENT_FINISHED, message="done", reason=done_reason)
                dbg.finalize("done")
                break

        else:
            action = parsed["action"]
            print(f"Parsed action: {action}")
            if "think" in action:
                print(f"Think: {action['think'][:300]}")

            if action["action"] == "done":
                done_reason = action.get("reason", "task complete")
                print(f"\n*** DONE: {done_reason} ***")
                print_cost_summary()
                emit(EventType.AGENT_FINISHED, message="done", reason=done_reason)
                dbg.log_step(step, raw_response=raw, think=action.get("think"),
                             parsed=parsed, results=["done"], usage=response.get("usage"))
                dbg.finalize("done")
                break

            if action["action"] == "unknown":
                print(f"WARNING: Could not parse action, retrying...")
                emit(EventType.STEP_ACTION_EXECUTED, step=step,
                     message="ERROR: parse error — retrying", action=action)
                action_log.append(f"Step {step}: [parse error — retrying]")
                dbg.log_step(step, raw_response=raw, think=None,
                             parsed=parsed, results=["parse error"])
                continue

            if debug:
                dbg.save_screenshot(img, step, actions=[action])

            result = execute_action(action, w, h)
            print(f"Executed: {result}")
            emit(EventType.STEP_ACTION_EXECUTED, step=step, message=result, action=action)

            dbg.log_step(step, raw_response=raw, think=action.get("think"),
                         parsed=parsed, results=[result], usage=response.get("usage"))

            if result.startswith("ERROR"):
                action_log.append(f"Step {step}: {result}")
                continue

            action_log.append(f"Step {step}: {result}")

        emit(EventType.STEP_COMPLETED, step=step)

        # Check stop before waiting for next step
        if event_bus and event_bus.stop_requested:
            print_cost_summary()
            dbg.finalize("stopped_by_user")
            break

        # Wait for UI to update, then take new screenshot
        current_delay = live("step_delay", step_delay)
        time.sleep(current_delay)
        img = take_screenshot()
        w, h = img.size
        emit(EventType.STEP_SCREENSHOT_TAKEN, step=step, screenshot=img, width=w, height=h)

        # Loop detection: compare with previous screenshot
        if screenshots_are_similar(prev_img, img):
            unchanged_count += 1
            # Annotate the most recent action log entry
            if action_log and not action_log[-1].endswith("[screen unchanged]"):
                action_log[-1] += "  [screen unchanged]"
        else:
            unchanged_count = 0
        prev_img = img

    else:
        print(f"\n*** Reached max steps ({max_steps}) without completion ***")
        print_cost_summary()
        emit(EventType.AGENT_FINISHED, message="max_steps")
        dbg.finalize("max_steps")


def main():
    parser = argparse.ArgumentParser(
        description="OpenCursor — model-agnostic autonomous computer-use agent"
    )
    parser.add_argument("goal", nargs="?", default=None,
                        help='Goal to accomplish, e.g. "open notepad and type hello world"')
    parser.add_argument("--model", default=None, help="Model adapter: qwen, gpt4o, claude, gemini, generic (default: qwen)")
    parser.add_argument("--model-id", default=None, help="Override the specific model ID (e.g. gpt-4o-2024-11-20)")
    parser.add_argument("--base-url", default=None, help="Override API base URL (e.g. http://localhost:11434/v1)")
    parser.add_argument("--api-key-env", default=None, help="Env var name for API key (default depends on adapter)")
    parser.add_argument("--max-steps", type=int, default=None, help="Maximum number of actions (default: 30)")
    parser.add_argument("--step-delay", type=float, default=None, help="Seconds between actions (default: 1.5)")
    parser.add_argument("--no-gui", action="store_true", help="Run in terminal mode without GUI overlay")
    parser.add_argument("--debug", action="store_true", help="Also save annotated screenshots to the session directory")
    args = parser.parse_args()

    config = load_config({
        "model": args.model,
        "model_id": args.model_id,
        "base_url": args.base_url,
        "api_key_env": args.api_key_env,
        "max_steps": args.max_steps,
        "step_delay": args.step_delay,
        "debug": args.debug or None,
    })

    if args.no_gui:
        if not args.goal:
            parser.error("goal is required in --no-gui mode")
        run_agent(args.goal, config)
    else:
        import os
        import sys

        # Suppress harmless DPI warning on Windows (context already set by Python/pyautogui)
        os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.window=false")

        from PySide6.QtWidgets import QApplication
        from gui.app import Application

        app = QApplication(sys.argv)
        application = Application(run_fn=run_agent, config=config, goal_hint=args.goal)
        application.show()
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
