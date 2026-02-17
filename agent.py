"""
Autonomous computer-use agent: give it a high-level goal and it will
observe the screen, decide what to do, and execute actions until done.
"""

import argparse
import time

from actions import execute_action
from config import load_config
from debug_session import DebugSession
from models import get_adapter
from prompts import build_system_prompt
from screenshot import take_screenshot


def run_agent(goal: str, config: dict):
    adapter = get_adapter(config["model"])
    client = adapter.build_client(config)
    system_prompt = build_system_prompt(adapter.get_prompt_overrides())

    max_steps = config.get("max_steps", 30)
    step_delay = config.get("step_delay", 1.5)
    debug = config.get("debug", False)

    dbg = DebugSession(goal) if debug else None
    if dbg:
        print(f"Debug session: {dbg.dir}")

    print(f"Goal: {goal}")
    print(f"Model: {config['model']}" + (f" ({config['model_id']})" if config.get("model_id") else ""))
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

        # Build user message
        user_text = f"Goal: {goal}"
        if action_log:
            user_text += "\n\nCompleted actions:\n" + "\n".join(action_log)
        user_text += "\n\nHere is the current screenshot. What is your next action?"

        # Call model (adapter handles API specifics, parsing, retries)
        print(f"Sending prompt with {len(action_log)} logged actions")
        response = adapter.call(client, system_prompt, user_text, img, config)

        raw = response["raw"]
        parsed = response["parsed"]

        if parsed["type"] == "sequence":
            steps = parsed["steps"]
            think = parsed.get("think")
            if think:
                print(f"Think: {think[:300]}")
            print(f"Executing sequence of {len(steps)} actions")

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
                if i < len(steps) - 1:
                    time.sleep(0.3)

            action_log.append(f"Step {step}: sequence [{', '.join(seq_results)}]")

            if dbg:
                dbg.log_step(step, raw_response=raw, think=think, parsed=parsed,
                             results=seq_results, usage=response.get("usage"))

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
                    dbg.log_step(step, raw_response=raw, think=action.get("think"),
                                 parsed=parsed, results=["done"], usage=response.get("usage"))
                    dbg.finalize("done")
                break

            if action["action"] == "unknown":
                print(f"WARNING: Could not parse action, retrying...")
                action_log.append(f"Step {step}: [parse error — retrying]")
                if dbg:
                    dbg.log_step(step, raw_response=raw, think=None,
                                 parsed=parsed, results=["parse error"])
                continue

            if dbg:
                dbg.save_screenshot(img, step, actions=[action])

            result = execute_action(action, w, h)
            print(f"Executed: {result}")

            if dbg:
                dbg.log_step(step, raw_response=raw, think=action.get("think"),
                             parsed=parsed, results=[result], usage=response.get("usage"))

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
    parser = argparse.ArgumentParser(
        description="OpenCursor — model-agnostic autonomous computer-use agent"
    )
    parser.add_argument("goal", help='Goal to accomplish, e.g. "open notepad and type hello world"')
    parser.add_argument("--model", default=None, help="Model adapter: qwen, gpt4o, claude, gemini, generic (default: qwen)")
    parser.add_argument("--model-id", default=None, help="Override the specific model ID (e.g. gpt-4o-2024-11-20)")
    parser.add_argument("--base-url", default=None, help="Override API base URL (e.g. http://localhost:11434/v1)")
    parser.add_argument("--api-key-env", default=None, help="Env var name for API key (default depends on adapter)")
    parser.add_argument("--max-steps", type=int, default=None, help="Maximum number of actions (default: 30)")
    parser.add_argument("--step-delay", type=float, default=None, help="Seconds between actions (default: 1.5)")
    parser.add_argument("--no-gui", action="store_true", help="Run in terminal mode without GUI overlay")
    parser.add_argument("--debug", action="store_true", help="Save screenshots, reasoning, and logs to debug/<session>/")
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
        run_agent(args.goal, config)
    else:
        from overlay import AgentOverlay

        overlay = AgentOverlay(title=f"OpenCursor \u2014 {args.goal[:50]}")
        overlay.redirect_output()
        overlay.set_status(f"Goal: {args.goal[:80]}")
        overlay.run_in_background(run_agent, args.goal, config)
        overlay.mainloop()


if __name__ == "__main__":
    main()
