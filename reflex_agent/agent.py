from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
import time
from typing import AsyncIterator, Optional, Tuple

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

from .vision import VisionComputerUse
from .game_copilot import AutonomousGameCopilot
from .desktop import (
    focus_app_by_process,
    open_app_or_game,
    search_or_open_website as desktop_search_or_open,
    switch_browser_tab as desktop_switch_tab,
    scroll_screen,
    press_key,
    hold_key,
    repeat_key,
    move_game,
    type_text,
)

logger = logging.getLogger("reflex.agent")


def _clean_spoken_text(text: str) -> str:
    cleaned = text.lower().strip()
    cleaned = re.sub(r"[^\w\s]", "", cleaned)
    cleaned = re.sub(r"^(?:can you|could you|please|would you|just|hey|agent)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*(?:please|for me|now|right now)?$", "", cleaned)
    cleaned = re.sub(r"\b(?:piece|peace|breastpiece)\b", "space", cleaned)
    cleaned = re.sub(r"\bsqueeze\s*(?:work|bar)?\b", "space bar", cleaned)
    cleaned = re.sub(r"\bspace\s+where\b", "space bar", cleaned)
    return cleaned.strip()


def _check_local_hardware_reflex(text: str) -> Optional[Tuple[str, str]]:
    c = _clean_spoken_text(text)
    num_map = {
        "once": 1,
        "twice": 2,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }

    m_move = re.search(r"^(?:move|walk|run|sprint|go)\s+(forward|ahead|front|backward|back|left|right)(?:\s+(?:for\s+)?(\d+(?:\.\d+)?)\s*(?:s|sec|seconds)?)?$", c)
    if m_move:
        direction = m_move.group(1)
        raw_sec = m_move.group(2)
        duration = float(raw_sec) if raw_sec else 1.5
        is_sprint = "sprint" in c or "run" in c
        ack = move_game(direction, duration=duration, sprint=is_sprint)
        return ("move_game", ack)

    m_hold = re.search(r"^hold\s+(?:the\s+)?([a-z0-9]|space|shift\+[a-z])(?:\s+(?:key|button))?\s+(?:for\s+)?(\d+(?:\.\d+)?)\s*(?:s|sec|seconds)?$", c)
    if m_hold:
        key = m_hold.group(1)
        raw_sec = m_hold.group(2)
        duration = float(raw_sec) if raw_sec else 1.0
        ack = hold_key(key, duration=duration)
        return ("hold_key", ack)

    m_key = re.search(r"^(?:press|hit|tap)\s+(?:the\s+)?([a-z0-9]|tab|enter|esc|escape|space|backspace|delete|shift|ctrl|alt)(?:\s+(?:key|button|bar))?(?:\s+(\d+|once|twice|two|three|four|five|six|seven|eight|nine|ten)\s+times?)?(?:\s+again)?$", c)
    if m_key:
        raw_key = m_key.group(1)
        raw_count = m_key.group(2)
        times = int(raw_count) if raw_count and raw_count.isdigit() else num_map.get(raw_count, 1)
        if times > 1:
            ack = repeat_key(raw_key, times=times)
            return ("repeat_key", ack)
        else:
            ack = press_key(raw_key)
            return ("press_key", ack)

    if any(k in c for k in ("space bar", "spacebar", "space", "pause", "unpause", "play", "resume", "freeze")):
        press_key("space")
        return ("pause_resume", "Toggled playback.")

    elif any(k in c for k in ("mute", "unmute", "silence", "quiet")):
        press_key("m")
        return ("mute_toggle", "Toggled mute.")

    elif ("volume" in c or "sound" in c or "audio" in c or "louder" in c) and any(k in c for k in ("up", "louder", "raise", "increase", "boost", "more")):
        press_key("volumeup")
        return ("volume_up", "Volume up.")

    elif ("volume" in c or "sound" in c or "audio" in c or "quieter" in c or "softer" in c) and any(k in c for k in ("down", "quieter", "softer", "lower", "decrease", "reduce", "less")):
        press_key("volumedown")
        return ("volume_down", "Volume down.")

    elif "scroll" in c or "page" in c:
        if any(k in c for k in ("down", "bottom", "below")):
            scroll_screen("down")
            return ("scroll_down", "Scrolled down.")
        elif any(k in c for k in ("up", "top", "above")):
            scroll_screen("up")
            return ("scroll_up", "Scrolled up.")

    elif any(k in c for k in ("close", "kill", "exit")) and any(k in c for k in ("tab", "window", "this")):
        press_key("ctrl+w")
        return ("close_tab", "Closed tab.")

    elif any(k in c for k in ("fullscreen", "full screen")):
        press_key("f")
        return ("fullscreen", "Toggled fullscreen.")

    elif any(k in c for k in ("press enter", "hit enter")):
        press_key("enter")
        return ("enter", "Pressed enter.")

    elif any(k in c for k in ("escape", "press esc")):
        press_key("escape")
        return ("escape", "Pressed escape.")

    return None


def _check_local_app_or_tab_switch(text: str) -> Optional[str]:
    c = _clean_spoken_text(text)

    m_tab = re.search(r"^(?:switch to|go to|open up|open|show)\s+(?:the\s+)?(.+?)\s+tab$", c)
    if m_tab:
        target_tab = m_tab.group(1).strip()
        desktop_switch_tab(target_tab)
        return f"Switched to {target_tab} tab."

    m_app = re.search(r"^(?:switch to|go to|bring up|focus|open up|open|launch|start)\s+(?:the\s+)?(?:app\s+)?(.+)$", c)
    if m_app:
        target_app = m_app.group(1).strip()
        if focus_app_by_process(target_app):
            return f"Switched to {target_app}."

    return None


class ReflexDesktopAgent(BaseAgent):

    def __init__(self, model_id: str = "gemini-3.5-flash-lite") -> None:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.vision = VisionComputerUse(api_key=api_key)
        self.game_copilot = AutonomousGameCopilot(api_key=api_key)

        vision_engine = self.vision
        copilot_engine = self.game_copilot

        async def see_screen_and_act(instruction: str) -> str:
            """Visually look at the screen to find buttons, links, videos, cards, search bars, or UI elements, and interact with them using mouse and keyboard."""
            return await vision_engine.perceive_and_act(instruction)

        async def play_game_autonomously(objective: str, max_steps: int = 5) -> str:
            """Autonomously play through game sequences, advance dialogue/conversations, confirm prompts, navigate towards objectives, or interact with NPCs by reading on-screen key prompts."""
            return await copilot_engine.run_game_loop(objective, max_steps=max_steps)

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

        def hold_keyboard_key(key: str, duration: float = 1.0) -> str:
            """Hold down a key or combination (e.g. w, a, s, d, shift+w) for a given duration in seconds."""
            return hold_key(key, duration=duration)

        def move_game_character(direction: str = "forward", duration: float = 1.5, sprint: bool = False) -> str:
            """Move a video game character in a direction (forward, backward, left, right) for a duration with optional sprinting."""
            return move_game(direction, duration=duration, sprint=sprint)

        self.controller_agent = Agent(
            model=Gemini(id=model_id, api_key=api_key),
            tools=[
                open_or_switch_app,
                search_or_open_website,
                switch_browser_tab,
                type_text_into_active_window,
                press_keyboard_key,
                hold_keyboard_key,
                move_game_character,
                see_screen_and_act,
                play_game_autonomously,
            ],
            instructions=(
                "You are an autonomous desktop voice assistant controlling a Windows PC. "
                "Always use your tools to perform user requests: "
                "- open_or_switch_app: opens or switches to an application or game like Discord, Steam, Spotify. "
                "- search_or_open_website: searches Google or YouTube, or opens URLs. "
                "- switch_browser_tab: switches to an open browser tab. "
                "- type_text_into_active_window: types text into active window. "
                "- press_keyboard_key: presses any keyboard key or shortcut. "
                "- hold_keyboard_key: holds down a key for a duration in seconds (e.g. walking, sprinting, charging). "
                "- move_game_character: moves a game character forward, backward, left, or right with optional sprinting. "
                "- play_game_autonomously: when the user asks to advance dialogue, talk to an NPC, or play through a game sequence without micromanaging step-by-step. "
                "- see_screen_and_act: captures the screen and visually locates and interacts with UI elements. "
                "When the user asks to click, select, or interact with a visible element on screen, always call see_screen_and_act. "
                "When the user asks to advance a dialogue sequence or talk to a character autonomously, call play_game_autonomously. "
                "When the user asks to open or switch to an app, use open_or_switch_app with just the clean app name. "
                "After calling a tool, reply in 1 concise, natural spoken sentence confirming the action. "
                "Never use markdown formatting, bullets, or symbols."
            ),
            markdown=False,
        )

    async def warmup(self) -> None:
        await self.vision.warmup()

    async def respond(self, text: str) -> AsyncIterator[AgentEvent]:
        t0 = time.perf_counter()

        reflex = _check_local_hardware_reflex(text)
        if reflex:
            action, ack = reflex
            total_ms = (time.perf_counter() - t0) * 1000
            print(f"\n⚡ [Local Reflex] {action} -> Done in {total_ms:.1f}ms\n  ✅ {ack}", flush=True)
            yield AgentEvent.text(ack)
            return

        app_switch_ack = _check_local_app_or_tab_switch(text)
        if app_switch_ack:
            total_ms = (time.perf_counter() - t0) * 1000
            print(f"\n⚡ [Process Radar] {app_switch_ack} -> Done in {total_ms:.1f}ms", flush=True)
            yield AgentEvent.text(app_switch_ack)
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

    async def close(self) -> None:
        await self.vision.close()
        await self.game_copilot.close()
