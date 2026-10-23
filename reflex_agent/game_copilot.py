from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Optional, List, Dict, Any

from google.genai import types

from .desktop import press_key, hold_key, repeat_key, move_game, attach_to_input_desktop
from .snap import SnapVisualVerifier
from .vision import capture_screen, _screen_to_jpeg_bytes, _extract_json
from .memory import global_memory
from .research import research_game_knowledge

logger = logging.getLogger("reflex.game")

_GAME_COPILOT_PROMPT = """You are an autonomous game copilot playing a PC video game.
Objective: "{objective}"
Current Step: {step_num} of {max_steps}
Recent Actions: {history}

{learned_context}

The screenshot shows the current active game screen.
Inspect the game HUD, on-screen key legends, prompts, and current state:
1. State: Dialogue sequence, modal prompt (YES/NO), menu, exploration/walking, or cutscene?
2. Button Prompts: Look for on-screen prompt keys (e.g. "[C] Talk", "[SPACE] Advance/Skip", "[ENTER] Decide", "[ESC] Back", "[E] Interact", "[WASD] Move").
3. Determine the next step towards the objective:
   - "advance_dialogue": dialogue box with text or arrow -> press space or enter.
   - "confirm_choice": modal prompt (e.g. YES/NO) -> press enter or space to confirm, or arrow to switch.
   - "interact": interact icon on screen -> press enter, e, or c.
   - "move": player character is moving -> hold 'w' (or 'a'/'s'/'d' or 'shift+w') towards target for 1.0 to 2.5s.
   - "press_key": press a single game key (space, enter, esc, c, tab, etc.).
   - "research": if stuck, unsure of controls, or previous actions failed repeatedly -> trigger research.
   - "done": objective is accomplished, or human decision is required.

Return ONLY a JSON object:
{{
  "state": "<concise description of screen>",
  "action": "advance_dialogue | confirm_choice | interact | move | press_key | research | done",
  "key": "<key to press, e.g. space, c, enter, e, w, left, right, esc>",
  "duration": <float seconds if moving or holding, default 0.0>,
  "reason": "<why this action helps the objective>",
  "is_complete": <true or false>
}}"""


class AutonomousGameCopilot:

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self._client = None
        self.verifier = SnapVisualVerifier()

    def _get_client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def run_game_loop(self, objective: str, max_steps: int = 8) -> str:
        client = self._get_client()
        history: List[str] = []
        last_state = ""
        prev_key = ""
        stuck_count = 0

        logger.info("[Game Copilot] Starting autonomous loop for: '%s' (max %d steps)", objective, max_steps)
        print(f"\n🎮 [Game Copilot] Autopilot active for: '{objective}' (up to {max_steps} steps)", flush=True)

        learned_ctx = global_memory.get_learned_prompt_context(objective)

        for step in range(1, max_steps + 1):
            screen = capture_screen()
            if screen is None:
                return "Could not capture game screen."

            jpeg = _screen_to_jpeg_bytes(screen, max_dim=1280, quality=75)
            prompt = _GAME_COPILOT_PROMPT.format(
                objective=objective,
                step_num=step,
                max_steps=max_steps,
                history=", ".join(history[-3:]) if history else "none",
                learned_context=learned_ctx,
            )

            config = types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=600,
                response_mime_type="application/json",
            )

            data = None
            for m in ("gemini-3.5-flash-lite", "gemini-3.8-flash"):
                try:
                    resp = await asyncio.to_thread(
                        client.models.generate_content,
                        model=m,
                        contents=[
                            types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"),
                            prompt,
                        ],
                        config=config,
                    )
                    data = _extract_json(resp.text)
                    break
                except Exception as exc:
                    err_s = str(exc)
                    logger.warning("[Game Copilot] Model %s failed: %s", m, err_s)
                    if "429" in err_s or "RESOURCE_EXHAUSTED" in err_s:
                        await asyncio.sleep(2.0)
                        continue
                    break

            if not data:
                logger.warning("[Game Copilot] Could not parse model decision on step %d", step)
                break

            state = data.get("state", "in-game")
            action = data.get("action", "done")
            raw_key = data.get("key", "space").lower()
            duration = float(data.get("duration", 0.0))
            reason = data.get("reason", "")
            is_complete = data.get("is_complete", False)
            last_state = state

            if raw_key == prev_key and action in ("interact", "press_key"):
                stuck_count += 1
            else:
                stuck_count = 0
            prev_key = raw_key

            key = raw_key
            if stuck_count >= 1 and action == "interact":
                alternates = ["enter", "e", "space"]
                alt_idx = (stuck_count - 1) % len(alternates)
                key = alternates[alt_idx]
                print(f"  ⚡ [Adaptive Learning] Key '{raw_key}' had no effect. Trying '{key}'!", flush=True)

            print(f"  🕹️ [Step {step}/{max_steps}] State: {state}", flush=True)
            print(f"     Action: {action} ({key}) — {reason}", flush=True)

            if action == "research" or stuck_count >= 3:
                guide = await research_game_knowledge(objective, "Persona 3 Reload")
                print(f"  🧠 [Game Research Insight] {guide}", flush=True)
                history.append(f"Researched: {guide[:60]}")
                stuck_count = 0
                await asyncio.sleep(1.0)
                continue

            if action == "done" or is_complete:
                history.append(f"Completed: {reason}")
                break

            elif action == "advance_dialogue":
                adv_key = key if key in ("space", "enter") else "space"
                press_key(adv_key, hold_duration=0.08)
                await asyncio.sleep(0.25)
                press_key(adv_key, hold_duration=0.08)
                history.append(f"Advanced dialogue with {adv_key}")
                await asyncio.sleep(0.8)

            elif action == "confirm_choice":
                press_key(key if key else "enter", hold_duration=0.08)
                history.append(f"Confirmed choice with {key}")
                await asyncio.sleep(0.8)

            elif action == "interact":
                press_key(key if key else "enter", hold_duration=0.1)
                history.append(f"Interacted with {key}")
                await asyncio.sleep(0.8)

            elif action == "move":
                move_sec = duration if duration > 0.1 else 1.5
                hold_key(key if key else "w", duration=move_sec)
                history.append(f"Moved {key} for {move_sec:.1f}s")
                await asyncio.sleep(0.6)

            elif action == "press_key":
                press_key(key, hold_duration=0.08)
                history.append(f"Pressed {key}")
                await asyncio.sleep(0.8)

        summary_actions = "; ".join(history) if history else "Evaluated game state"
        global_memory.record_action_outcome("Persona 3 Reload", objective, summary_actions, True)
        return f"Autonomous action completed: {summary_actions}. Game state: {last_state}."

    async def close(self) -> None:
        await self.verifier.close()
