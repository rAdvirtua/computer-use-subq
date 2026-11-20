# Computer Use SubQ

Voice-controlled desktop automation agent powered by Subquadratic models (**SubQ Savant 1.4** and **SubQ Snap**), combining instant Win32 process switching, local hardware reflexes, and native multimodal screen perception.

Controls Windows applications, Chromium browsers, media, and games hands-free via real-time speech or terminal console.

---

## Quickstart

### 1. Clone & Run with `uv`

```bash
git clone https://github.com/rAdvirtua/computer-use-subq.git
cd computer-use-subq
uv run python run_agent.py          # real-time voice
uv run python run_agent.py --text   # interactive text console
```

---

## Environment Variables

Only `SUBQ_API_KEY` is required to run the agent in text console mode. For voice input/output, add Deepgram and Cartesia keys:

| Variable | Required | Description |
| :--- | :--- | :--- |
| `SUBQ_API_KEY` | **Yes** | SubQ API key for Savant 1.4 reasoning, vision, and Snap verification |
| `DEEPGRAM_API_KEY` | Optional (Voice) | Deepgram API key for streaming speech-to-text (`nova-3`) |
| `CARTESIA_API_KEY` | Optional (Voice) | Cartesia API key for low-latency voice synthesis |
| `GEMINI_API_KEY` | Optional | Offline fallback model if SubQ API key is absent |

### Setting Environment Variables (PowerShell)

```powershell
[System.Environment]::SetEnvironmentVariable('SUBQ_API_KEY', 'your_key_here', 'User')
[System.Environment]::SetEnvironmentVariable('DEEPGRAM_API_KEY', 'your_key_here', 'User')
[System.Environment]::SetEnvironmentVariable('CARTESIA_API_KEY', 'your_key_here', 'User')
```

---

## Capabilities

### 1. SubQ Savant Controller & Tool Chaining (~600ms)
Powered by `subq-savant-1.4`, the controller orchestrates multi-step desktop tasks autonomously. For example, asking to *"Open Discord, jump to the general channel, and say hello"* opens the app, presses `Ctrl+K`, types the channel, and drafts the message in a single tool sequence.

### 2. Native Multimodal Screen Perception
SubQ Savant inspects full 1080p desktop screenshots, reading active conversation threads, identifying UI buttons and desktop icons, and computing normalized coordinates to click or double-click targets.

### 3. SubQ Snap Visual Outcome Verification
After executing visual actions, the agent queries `subq-snap-preview` via `POST /v1/systemone` to verify whether the intended state change actually occurred (e.g., confirming a dialogue advanced or a window focused).

### 4. Fast Win32 Process Radar (<5ms)
Matches executable basenames (`discord.exe`, `code.exe`, `spotify.exe`, `steam.exe`) and calls `SetForegroundWindow` in under 5ms, switching to already-running applications without opening the Start Menu.

### 5. Local Hardware Reflexes (<1ms)
Zero-latency media and navigation hotkeys execute directly in local memory before hitting the cloud:
* Show desktop (`Win+D`)
* Playback / pause toggle (`Space`)
* Volume adjustment (`Volume Up` / `Volume Down`)
* Mute toggle (`M`)
* Scroll screen (`Page Up` / `Page Down`)
* Close tab (`Ctrl+W`)
* Fullscreen toggle (`F`)

### 6. DirectInput Game Automation & Press-and-Hold
Dispatches hardware scan codes via `pydirectinput` to interact with games (DirectX, Unreal Engine, Unity) that bypass standard Windows message queues:
* Press-and-hold movement (e.g. `hold_key("w", duration=2.0)`)
* Key repeat support for menus and dialogue skipping
* Autonomous copilot loops with on-screen button legend detection (`[C] Talk`, `[Space] Advance`, `[Enter] Decide`)
* Persistent memory (`reflex_agent/data/learned_memory.json`) for caching proven key combinations and rules across sessions

---

## License

Apache-2.0
