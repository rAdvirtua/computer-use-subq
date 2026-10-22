from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from typing import AsyncIterator

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from agno.agent import Agent
from agno.models.google import Gemini

from yapwrap.core.base import BaseAgent
from yapwrap.core.events import AgentEvent

from .snap import SnapReflex
from .vision import VisionComputerUse
from .desktop import (
    open_app_or_game,
    search_or_open_website as desktop_search_or_open,
    switch_browser_tab as desktop_switch_tab,
    scroll_screen,
    press_key,
    type_text,
)

logger = logging.getLogger("reflex.agent")


class ReflexDesktopAgent(BaseAgent):

    def __init__(self, model_id: str = "gemini-3-flash-preview") -> None:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.snap = SnapReflex()
        self.vision = VisionComputerUse(api_key=api_key)

        vision_engine = self.vision

        async def see_screen_and_act(instruction: str) -> str:
            """Visually look at the screen to find buttons, links, videos, cards, search bars, or UI elements, and interact with them using mouse and keyboard."""
            return await vision_engine.perceive_and_act(instruction)

        def open_or_switch_app(app_name: str) -> str:
            """Open or switch to any application or game by name (e.g. Discord, Brave, Chrome, Spotify, Steam, Persona 3)."""
            return open_app_or_game(app_name)

        def search_or_open_website(query_or_url: str, site: str = "") -> str:
            """Search Google or YouTube, or open a URL/domain directly in the default browser."""
            return desktop_search_or_open(query_or_url, site)

        def switch_browser_tab(tab_name: str = "") -> str:
            """Switch to an open browser tab using Chromium Tab Search."""
            return desktop_switch_tab(tab_name)

        def type_text_into_active_window(text: str, press_enter: bool = True) -> str:
            """Type text into the currently active window or input field, optionally pressing Enter."""
            return type_text(text, press_enter=press_enter)

        def press_keyboard_key(key: str) -> str:
            """Press any keyboard key or shortcut (e.g. enter, esc, tab, space, ctrl+w, backspace)."""
            return press_key(key)

        self.controller_agent = Agent(
            model=Gemini(id=model_id, api_key=api_key),
            tools=[
                open_or_switch_app,
                search_or_open_website,
                switch_browser_tab,
                type_text_into_active_window,
                press_keyboard_key,
                see_screen_and_act,
            ],
            instructions=(
                "You are an autonomous desktop voice assistant controlling a Windows PC. "
                "Always use your tools to perform user requests: "
                "- open_or_switch_app: opens or switches to an application or game like Discord, Steam, Spotify. "
                "- search_or_open_website: searches Google or YouTube, or opens URLs. "
                "- switch_browser_tab: switches to an open browser tab. "
                "- type_text_into_active_window: types text into active window. "
                "- press_keyboard_key: presses any keyboard key or shortcut. "
                "- see_screen_and_act: captures the screen and visually locates and clicks buttons, links, videos, or UI elements. "
                "When the user asks to click, select, or interact with a visible element on screen, always call see_screen_and_act. "
                "When the user asks to open or switch to an app, use open_or_switch_app with just the clean app name. "
                "After calling a tool, reply in 1 concise, natural spoken sentence confirming the action. "
                "Never use markdown formatting, bullets, or symbols."
            ),
            markdown=False,
        )

    async def warmup(self) -> None:
        await self.snap.warmup()

    async def respond(self, text: str) -> AsyncIterator[AgentEvent]:
        t0 = time.perf_counter()

        action, conf, snap_ms = await self.snap.decide_action(text)
        logger.info("[Snap] %s (%.0f%% conf, %.0fms) for '%s'", action, conf * 100, snap_ms, text)

        if action != "controller" and conf >= 0.70:
            ack = self._execute_reflex_action(action)
            total_ms = (time.perf_counter() - t0) * 1000
            print(f"\n⚡ [Snap Reflex] {action} ({conf:.0%} | {snap_ms:.0f}ms) -> Done in {total_ms:.0f}ms\n  ✅ {ack}", flush=True)
            yield AgentEvent.text(ack)
            return

        print(f"\n🧠 [Controller Agent] Reasoning on: '{text}'...", flush=True)

        try:
            stream = self.controller_agent.arun(text, stream=True, stream_events=True)
            async for event in stream:
                kind = getattr(event, "event", "")
                content = getattr(event, "content", None)
                if kind == "RunContent" and isinstance(content, str) and content:
                    yield AgentEvent.text(content)

        except Exception as exc:
            err_str = str(exc)
            logger.warning("[Agent] Controller error: %s", err_str)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                yield AgentEvent.text("I'm hitting a quick API quota limit, please give me a few seconds.")
            else:
                yield AgentEvent.text("Sorry, I had a momentary connection hiccup.")

    def _execute_reflex_action(self, action: str) -> str:
        if action == "pause_resume":
            press_key("space")
            return "Toggled playback."
        elif action == "mute_toggle":
            press_key("m")
            return "Toggled mute."
        elif action == "volume_up":
            press_key("volumeup")
            return "Volume up."
        elif action == "volume_down":
            press_key("volumedown")
            return "Volume down."
        elif action == "scroll_down":
            scroll_screen("down")
            return "Scrolled down."
        elif action == "scroll_up":
            scroll_screen("up")
            return "Scrolled up."
        elif action == "close_tab":
            press_key("ctrl+w")
            return "Closed tab."
        elif action == "fullscreen":
            press_key("f")
            return "Toggled fullscreen."
        return "Done."

    async def close(self) -> None:
        await self.snap.close()
