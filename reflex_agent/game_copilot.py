from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from typing import Optional, List

import httpx

from .desktop import press_key, hold_key
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

Inspect the game screen, HUD, key legends, and current state.
Actions:
- "advance_dialogue": dialogue box with text or arrow -> press space or enter.
- "confirm_choice": modal prompt -> press enter or space.
- "interact": interact icon -> press enter, e, or c.
- "move": hold 'w' (or 'a'/'s'/'d') towards target for duration.
- "press_key": press a single key.
- "research": if stuck -> trigger research.
- "done": objective is accomplished.

Return ONLY a JSON object:
{{
  "state": "<screen description>",
  "action": "advance_dialogue | confirm_choice | interact | move | press_key | research | done",
  "key": "<key to press>",
  "duration": <float seconds>,
  "reason": "<reason>",
  "is_complete": <true or false>
}}"""


class AutonomousGameCopilot:

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.subq_key = os.environ.get("SUBQ_API_KEY", "")
        self.gemini_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self._http_client: Optional[httpx.AsyncClient] = None
        self._gemini_client = None
        self.verifier = SnapVisualVerifier()

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                headers={"Authorization": f"Bearer {self.subq_key}"},
                timeout=30.0,
                limits=httpx.Limits(max_keepalive_connections=5, keepalive_expiry=120.0),
            )
        return self._http_client

    def _get_gemini_client(self):
        if self._gemini_client is None and self.gemini_key:
            from google import genai
            self._gemini_client = genai.Client(api_key=self.gemini_key)
        return self._gemini_client

    async def run_game_loop(self, objective: str, max_steps: int = 8) -> str:
        history: List[str] = []
        last_state = ""
        prev_key = ""
        stuck_count = 0

        print(f"[copilot] active for: '{objective}' (max {max_steps} steps)", flush=True)

        learned_ctx = global_memory.get_learned_prompt_context(objective)

        for step in range(1, max_steps + 1):
            screen = capture_screen()
            if screen is None:
                return "Could not capture screen."

            jpeg = _screen_to_jpeg_bytes(screen, max_dim=1280, quality=75)
            b64_img = base64.b64encode(jpeg).decode("ascii")

            prompt = _GAME_COPILOT_PROMPT.format(
                objective=objective,
                step_num=step,
                max_steps=max_steps,
                history=", ".join(history[-3:]) if history else "none",
                learned_context=learned_ctx,
            )

            data = None

            if self.subq_key:
                try:
                    client = self._get_http_client()
                    resp = await client.post(
                        "https://api.subq.ai/v1/chat/completions",
                        json={
                            "model": "subq-savant-1.4",
                            "messages": [
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": prompt},
                                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}},
                                    ],
                                }
                            ],
                        },
                    )
                    if resp.status_code == 200:
                        raw = resp.json()["choices"][0]["message"].get("content", "").strip()
                        data = _extract_json(raw)
                except Exception as exc:
                    logger.warning("[copilot] subq call failed: %s", exc)

            if not data and self.gemini_key:
                g_client = self._get_gemini_client()
                if g_client:
                    from google.genai import types
                    config = types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=600,
                        response_mime_type="application/json",
                    )
                    for m in ("gemini-3.5-flash-lite", "gemini-3.8-flash"):
                        try:
                            resp = await asyncio.to_thread(
                                g_client.models.generate_content,
                                model=m,
                                contents=[
                                    types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"),
                                    prompt,
                                ],
                                config=config,
                            )
                            data = _extract_json(resp.text)
                            break
                        except Exception:
                            break

            if not data:
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

            print(f"[copilot] step {step}/{max_steps}: {action} ({key})", flush=True)

            if action == "research" or stuck_count >= 3:
                guide = await research_game_knowledge(objective, "Persona 3 Reload")
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
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None
