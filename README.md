# OpenCursor

An open-source, model-agnostic autonomous computer-use agent. Give it a goal in plain English, and it observes your screen, reasons about what to do, and controls your mouse and keyboard until the task is done.

## How It Works

```
Screenshot  -->  Vision LLM  -->  Parsed Action  -->  pyautogui  -->  repeat
```

Each step, the agent:
1. Takes a screenshot of your desktop
2. Sends it to a vision model along with the goal and action history
3. The model decides the next action (click, type, scroll, hotkey, etc.)
4. The action is executed via `pyautogui`
5. Waits for the UI to update, then loops

The agent stops when the model signals `done` or when `--max-steps` is reached.

## Supported Models

| Adapter   | Default Model                  | API              | Install                        |
|-----------|--------------------------------|------------------|--------------------------------|
| `qwen`    | Qwen 3.5 Plus                  | OpenRouter       | *(included)*                   |
| `gpt4o`   | GPT-4o                         | OpenAI (direct)  | *(included)*                   |
| `claude`  | Claude Sonnet 4                | Anthropic        | `pip install anthropic`        |
| `gemini`  | Gemini 2.5 Pro                 | OpenRouter       | *(included)*                   |
| `generic` | Any vision model (you choose)  | OpenRouter / any | *(included)*                   |

The `generic` adapter works with any OpenAI-compatible API, including local models via Ollama, LM Studio, etc.

## Installation

```bash
git clone https://github.com/user/opencursor.git
cd opencursor
pip install -r requirements.txt
```

**Optional** &mdash; install only for the adapters you use:
```bash
pip install anthropic          # for --model claude
```

## Configuration

Copy the example env file and add your API key(s):

```bash
cp .env.example .env
```

```env
# Required for qwen, gemini, and generic adapters (via OpenRouter)
OPENROUTER_API_KEY=sk-or-v1-...

# Required for --model gpt4o (direct OpenAI API)
OPENAI_API_KEY=sk-...

# Required for --model claude (direct Anthropic API)
ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

```bash
# Basic usage (defaults to Qwen via OpenRouter)
python agent.py "open notepad and type hello world"

# Use a specific model
python agent.py "search google for openai" --model gpt4o
python agent.py "open the calculator app" --model claude
python agent.py "scroll down on this page" --model gemini

# Use any model via the generic adapter
python agent.py "open settings" --model generic --model-id "meta-llama/llama-4-maverick"

# Point to a local model (Ollama, LM Studio, etc.)
python agent.py "open firefox" --model generic --model-id "llava" --base-url http://localhost:11434/v1

# Run without the GUI overlay
python agent.py "type hello" --no-gui

# Enable debug mode (saves screenshots, reasoning, and logs)
python agent.py "open spotify" --debug
```

### CLI Flags

| Flag              | Description                                            | Default     |
|-------------------|--------------------------------------------------------|-------------|
| `goal`            | Goal to accomplish (positional, required)               | &mdash;     |
| `--model`         | Model adapter: `qwen`, `gpt4o`, `claude`, `gemini`, `generic` | `qwen` |
| `--model-id`      | Override the specific model ID                          | adapter default |
| `--base-url`      | Override API base URL                                   | adapter default |
| `--api-key-env`   | Env var name for the API key                            | adapter default |
| `--max-steps`     | Maximum number of actions before stopping               | `30`        |
| `--step-delay`    | Seconds to wait between actions                         | `1.5`       |
| `--no-gui`        | Run in terminal mode without the GUI overlay            | `false`     |
| `--debug`         | Save screenshots, reasoning, and logs to `debug/<session>/` | `false` |

## Features

### Action Sequencing

The model can output a batch of "blind-safe" actions in a single turn (e.g., click a text field, type a query, press Enter) when no visual feedback is needed between steps. This reduces the number of API calls and speeds up execution.

### GUI Overlay

By default, the agent displays a real-time log overlay on screen using Tkinter. The overlay uses the Windows `SetWindowDisplayAffinity` API to make itself **invisible to screen capture** &mdash; so the agent never sees its own UI in the screenshots.

### Debug Mode

Pass `--debug` to save a full session trace to `debug/<timestamp>/`:

- `step_001.png`, `step_002.png`, ... &mdash; annotated screenshots with bounding boxes
- `step_001_raw.txt`, ... &mdash; raw model responses
- `session.log` &mdash; human-readable step-by-step log
- `summary.json` &mdash; structured session summary

### Visual Grounding Tool

`ground.py` is a standalone utility for testing whether a vision model can locate a UI element on screen:

```bash
python ground.py "the search bar"
python ground.py "close button" --delay 3
python ground.py "submit button" --image screenshot.png
```

It sends a screenshot to the model, gets back bounding box coordinates, and saves an annotated image to `output/`.

### Safety

- **Failsafe**: `pyautogui.FAILSAFE` is enabled &mdash; move your mouse to any screen corner to instantly abort
- **Max steps**: The agent stops after `--max-steps` actions (default 30) to prevent runaway loops
- **Step delay**: A configurable pause between actions lets you observe what's happening

## Project Structure

```
opencursor/
  agent.py           # Main agent loop and CLI entry point
  actions.py         # Action execution via pyautogui
  config.py          # Configuration loading (defaults -> .env -> CLI args)
  parsing.py         # XML and tool_use response parsing
  prompts.py         # System prompt templates
  screenshot.py      # Screenshot capture and base64 encoding
  overlay.py         # GUI overlay (hidden from screen capture)
  debug_session.py   # Debug session management
  ground.py          # Standalone visual grounding test tool
  adapters/
    base.py          # Abstract adapter base class
    qwen.py          # Qwen adapter (OpenRouter)
    openai_gpt.py    # GPT-4o adapter (OpenAI API, tool_use)
    claude.py        # Claude adapter (Anthropic API, tool_use)
    gemini.py        # Gemini adapter (OpenRouter)
    generic.py       # Generic adapter (any OpenAI-compatible API)
```

## Adding a New Model Adapter

1. Create a new file in `adapters/` that extends `ModelAdapter` from `adapters/base.py`
2. Implement `build_client()`, `_call_api()`, and `get_prompt_overrides()`
3. Register it in `adapters/__init__.py`

The base class provides helpers for building OpenRouter clients, constructing message arrays, retry logic, debug output, and response packaging.

## Requirements

- Python 3.10+
- Windows (the GUI overlay uses Windows-specific APIs; the agent itself works cross-platform with `--no-gui`)
- A vision-capable LLM API key (OpenRouter, OpenAI, or Anthropic)

## License

MIT
