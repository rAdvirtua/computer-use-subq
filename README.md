# Computer Use SubQ

Autonomous real-time voice desktop agent combining SubQ Snap fast reflex routing (<80ms) with Gemini multimodal visual computer use.

Controls Windows applications, Chromium browsers, media, and games using natural voice commands, with an autonomous visual perception fallback for tasks that require seeing the screen.

---

## Architecture Overview

```
                      User Speech (Silero VAD + Deepgram STT)
                                         |
                                         v
                    +------------------------------------------+
                    |        Tier 1: SubQ Snap Reflex          |
                    |      Decision Engine (<80ms warm)        |
                    +--------------------+---------------------+
                                         |
                 +-----------------------+-----------------------+
                 |                                               |
      [Reflex Hotkeys: >=70%]                         [Complex / Semantic / Visual]
      * pause_resume  (space)                                    |
      * mute_toggle   (m)                                        v
      * volume_up/down                                +------------------------------------+
      * scroll_up/down                                | Tier 2: Universal Desktop          |
      * close_tab     (ctrl+w)                        | Gemini Controller + Universal Tools|
      * fullscreen    (f)                             +------------------+-----------------+
                 |                                                       |
                 v                                                       v
       Instant Physical Key                             Universal Autonomous Tools:
       Execution (<10ms)                                1. open_or_switch_app
                                                        2. search_or_open_website
                                                        3. switch_browser_tab
                                                        4. type_text_into_active_window
                                                        5. press_keyboard_key
                                                        6. see_screen_and_act
                                                                         |
                                                                         v
                                                             [Visual Navigation Engine]
                                                             * Live 1080p desktop capture
                                                             * Multimodal UI element grounding
                                                             * Human-paced mouse move & click
```

---

## One-Liner Quickstart

### Windows (PowerShell)

Run the following single command in PowerShell. It checks for `uv`, clones the repository, installs all dependencies, and activates the agent:

```powershell
if (!(Get-Command uv -ErrorAction SilentlyContinue)) { irm https://astral.sh/uv/install.ps1 | iex }; git clone https://github.com/rAdvirtua/computer-use-subq.git; cd computer-use-subq; uv run python run_agent.py
```

### Linux / macOS (Bash)

```bash
command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh; git clone https://github.com/rAdvirtua/computer-use-subq.git && cd computer-use-subq && uv run python run_agent.py
```

---

## Prerequisites & Environment Variables

Ensure the following API keys are set in your environment:

| Key | Description |
| :--- | :--- |
| `GEMINI_API_KEY` | Google Gemini API key for multimodal vision and controller reasoning |
| `SUBQ_API_KEY` | SubQ API key for ultra-fast categorical reflex classification |
| `DEEPGRAM_API_KEY` | Deepgram API key for real-time speech-to-text |
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

### Tier 1: SubQ Snap Instant Reflex (<80ms)
Direct physical hotkeys execute without invoking an LLM:
* Media playback toggle (Space)
* Audio mute toggle (M)
* Volume up / down
* Page scroll up / down
* Tab / window closure (Ctrl+W)
* Fullscreen toggle (F)

Execution completes in under 150 milliseconds end-to-end, preserving API quotas and eliminating conversational delay.

### Tier 2: Universal Desktop Controller
When a user command contains semantic entities or targets visual screen elements:
* **Application Management:** Uses native Win32 APIs and Windows Start search to focus or launch any desktop app or game.
* **Web Navigation:** Opens direct search queries or specific URLs in the default browser.
* **Browser Tab Search:** Uses Chromium Tab Search (`Ctrl+Shift+A`) to switch between tabs instantly.
* **Visual Navigation Fallback (`see_screen_and_act`):**
  1. Captures the active monitor via the interactive desktop station (`WinSta0\Default`).
  2. Compresses and evaluates the display using Gemini Multimodal Vision.
  3. Grounding identifies exact bounding coordinates `(x, y)` for dynamic targets (e.g., "third video result", "skip ad", "play button in game menu").
  4. Moves mouse smoothly with quadratic easing and triggers native hardware input events.

---

## Manual Installation & Usage

If you prefer to clone and set up manually:

```bash
git clone https://github.com/rAdvirtua/computer-use-subq.git
cd computer-use-subq
uv run python run_agent.py
```

`uv` automatically provisions the Python environment and installs all dependencies specified in `pyproject.toml`.

---

## License

Apache-2.0
