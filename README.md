# Computer Use SubQ

Superhuman real-time voice desktop agent combining instant Win32 process snapping, zero-latency local reflexes, and Gemini multimodal computer use with SubQ Snap visual verification.

Interacts with Windows applications, Chromium browsers, media, and games faster than human manual interaction (<400ms end-to-end), backed by an autonomous visual perception loop.

---

## Architecture Overview

```
                      User Speech (Silero VAD + Deepgram STT)
                                         |
                                         v
                    +------------------------------------------+
                    |    Local Zero-Latency Fast Path (<2ms)   |
                    |    Token Normalization & Intent Routing  |
                    +--------------------+---------------------+
                                         |
                 +-----------------------+-----------------------+
                 |                                               |
      [Hardware Hotkeys: <1ms]                        [Direct App / Tab Switch]
      * pause, play, resume (Space)                   * "switch to discord"
      * mute, unmute (M)                              * "go to my code"
      * volume up / down                              * "open youtube tab"
      * scroll up / down                                         |
      * close tab (Ctrl+W)                                       v
      * fullscreen (F)                                +------------------------------------+
                 |                                    | Fast OS Radars                     |
                 v                                    | Radar 1: Win32 Process Snap (<5ms) |
        Instant Physical Key                          | Radar 2: Chromium Tab Search (50ms)|
        Execution (<5ms)                              +------------------+-----------------+
                                                                         |
                                                   [If Not Open / Complex / Visual]
                                                                         |
                                                                         v
                                                      +------------------------------------+
                                                      | Tier 2: Universal Desktop          |
                                                      | Gemini Controller + Universal Tools|
                                                      +------------------+-----------------+
                                                                         |
                                                                         v
                                                             [Visual Navigation Engine]
                                                             * Live 1080p desktop capture
                                                             * Multimodal UI element grounding
                                                             * Human-paced mouse move & click
                                                                         |
                                                                         v
                                                             [SubQ Snap Visual Verifier]
                                                             * High-speed image API (<300ms)
                                                             * Verifies visual click success
```

---

## One-Liner Quickstart

### Windows (PowerShell)

Run the following single command in PowerShell. It verifies or installs `uv`, clones the repository, provisions all dependencies, and activates the agent:

```powershell
if (!(Get-Command uv -ErrorAction SilentlyContinue)) { irm https://astral.sh/uv/install.ps1 | iex }; git clone https://github.com/rAdvirtua/computer-use-subq.git; cd computer-use-subq; uv run python run_agent.py
```

### Linux / macOS (Bash)

```bash
command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh; git clone https://github.com/rAdvirtua/computer-use-subq.git && cd computer-use-subq && uv run python run_agent.py
```

---

## Prerequisites & Environment Variables

Ensure the following API keys are present in your environment:

| Key | Description |
| :--- | :--- |
| `GEMINI_API_KEY` | Google Gemini API key for multimodal spatial computer use |
| `SUBQ_API_KEY` | SubQ API key for ultra-fast visual click verification |
| `DEEPGRAM_API_KEY` | Deepgram API key for real-time streaming speech-to-text |
| `CARTESIA_API_KEY` | Cartesia API key for ultra-low latency voice synthesis |

### Setting Environment Variables

#### Windows (PowerShell)
```powershell
[System.Environment]::SetEnvironmentVariable('GEMINI_API_KEY', 'your_key_here', 'User')
[System.Environment]::SetEnvironmentVariable('SUBQ_API_KEY', 'your_key_here', 'User')
[System.Environment]::SetEnvironmentVariable('DEEPGRAM_API_KEY', 'your_key_here', 'User')
[System.Environment]::SetEnvironmentVariable('CARTESIA_API_KEY', 'your_key_here', 'User')
```

#### Linux / macOS (Bash)
```bash
export GEMINI_API_KEY="your_key_here"
export SUBQ_API_KEY="your_key_here"
export DEEPGRAM_API_KEY="your_key_here"
export CARTESIA_API_KEY="your_key_here"
```

---

## How It Works

### 1. Win32 Process Radar (<5ms)
Solves the dynamic window title problem. Instead of checking for shifting titles (e.g. `#general - Discord`), it queries running process image paths directly:
* Matches executable basenames (`discord.exe`, `code.exe`, `spotify.exe`, `steam.exe`).
* Bypasses the Windows foreground lock and calls `SetForegroundWindow` in under 5 milliseconds.
* If an application is already running, it brings it to the front instantly without ever opening the Windows Start Menu.

### 2. Universal Chromium Tab Search (50ms)
Solves the browser background tab blind spot:
* Focuses the browser and sends `Ctrl+Shift+A` (Chromium Tab Search).
* Types the target tab name and presses Enter.
* Directly activates any tab across 50+ open tabs in 50 milliseconds.

### 3. Local Hardware Hotkeys (<1ms)
Zero-parameter media and navigation actions execute directly in local memory:
* Playback toggle (Space)
* Mute toggle (M)
* Volume up / down
* Scroll up / down
* Tab closure (Ctrl+W)
* Fullscreen toggle (F)

### 4. SubQ Snap Visual Action Verifier (<300ms)
After the vision engine clicks an on-screen element (such as a video or button), SubQ Snap inspects the post-action screen state using its native image endpoint (`POST /v1/systemone` with a `noul` question):
* Evaluates visual state transition in ~300ms.
* Confirms click success or triggers immediate re-targeting at $0.05 / 1M tokens.

### 5. Gemini Multimodal Spatial Controller
When an action requires spatial awareness (reading complex web layouts, targeting video thumbnails, game menus):
* Captures the primary display via the interactive desktop station (`WinSta0\Default`).
* Computes normalized coordinates `(x, y)` for the target visual element.
* Moves the mouse with smooth easing and triggers native clicks.

### 6. Universal DirectInput Keystrokes & Press-and-Hold
Video games (DirectX, Unreal Engine, Unity) and desktop software bypass standard Windows virtual message queues and poll hardware scan codes directly via DirectInput and RawInput:
* Dispatches genuine hardware scan codes (`KEYEVENTF_SCANCODE`) via `pydirectinput`.
* Press-and-hold duration support: moves game characters smoothly (e.g. `hold_key("w", 2.0)` or `move_game("forward", 1.5, sprint=True)`).
* Key repeat support: handles requests like "press w four times" with calibrated inter-key intervals.
* Zero-latency local reflex routing: single-key presses ("press w", "press c", "press tab") execute in <60ms directly in local memory.
* Acoustic gaming STT normalizer: resolves background game audio confusions (e.g. "piece", "squeeze work" -> "space").

### 7. Autonomous Game Copilot
High-level gameplay sequences can run on autopilot without micro-dictation:
* Inspects HUD and on-screen button prompt legends (`[C] Talk`, `[Space] Advance`, `[Enter] Decide`).
* Dispatches multi-step sequences to advance dialogues, confirm modal dialogs (YES/NO), or interact with NPCs.
* Stops autonomously when the objective is met or when a major narrative choice requires human input.

### 8. Persistent Learning Memory & Autonomous Web Research
The agent continuously learns across sessions and autonomously researches unknown game mechanics or controls:
* Persistent Memory (`reflex_agent/data/learned_memory.json`): Records which actions succeed or fail, tracking proven controls and rules per game across runs.
* Adaptive Action Pivoting: If an interaction key fails to produce a state change, the copilot automatically cycles to alternative interact keys (Enter, E, Space) instead of repeating failed keys.
* Internet Game Research: When confused or asked how to save or perform an in-game action, the agent queries web guides via DuckDuckGo, synthesizes the exact PC keyboard sequence, and records the rule for future runs.

---

## Manual Installation & Usage

```bash
git clone https://github.com/rAdvirtua/computer-use-subq.git
cd computer-use-subq
uv run python run_agent.py
```

`uv` automatically provisions the environment and installs all dependencies specified in `pyproject.toml`.

---

## License

Apache-2.0
