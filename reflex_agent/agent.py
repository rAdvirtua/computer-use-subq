from __future__ import annotations

import asyncio
import json
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

from yapwrap.core.base import BaseAgent
from yapwrap.core.events import AgentEvent

from .vision import VisionComputerUse
from .game_copilot import AutonomousGameCopilot
from .memory import global_memory
from .research import research_game_knowledge
from .subq_client import SubQSavantClient
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

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "show_desktop",
            "description": "Show the Windows desktop or minimize all open windows (Win+D).",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_or_switch_app",
            "description": "Open or switch to any application or game by name.",
            "parameters": {
                "type": "object",
                "properties": {"app_name": {"type": "string"}},
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_or_open_website",
            "description": "Search Google or YouTube, or open a URL/domain directly.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_or_url": {"type": "string"},
                    "site": {"type": "string", "default": ""},
                },
                "required": ["query_or_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "switch_browser_tab",
            "description": "Switch to an open browser tab using Chromium Tab Search.",
            "parameters": {
                "type": "object",
                "properties": {"tab_name": {"type": "string", "default": ""}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text_into_active_window",
            "description": "Type text into the currently active window, optionally pressing Enter.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "press_enter": {"type": "boolean", "default": True},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "press_keyboard_key",
            "description": "Press any keyboard key or shortcut (e.g. enter, esc, tab, space, win+d, ctrl+w, backspace).",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hold_keyboard_key",
            "description": "Hold down a key or combination for a given duration in seconds.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "duration": {"type": "number", "default": 1.0},
                },
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_game_character",
            "description": "Move a video game character in a direction for a duration with optional sprinting.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["forward", "backward", "left", "right"], "default": "forward"},
                    "duration": {"type": "number", "default": 1.5},
                    "sprint": {"type": "boolean", "default": False},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "see_screen_and_act",
            "description": "Visually look at the screen using SubQ Savant vision to find desktop icons, buttons, links, or UI elements and click or interact with them.",
            "parameters": {
                "type": "object",
                "properties": {"instruction": {"type": "string"}},
                "required": ["instruction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "play_game_autonomously",
            "description": "Autonomously play through game sequences, advance dialogue, confirm prompts, navigate towards objectives.",
            "parameters": {
                "type": "object",
                "properties": {
                    "objective": {"type": "string"},
                    "max_steps": {"type": "integer", "default": 5},
                },
                "required": ["objective"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "research_game_controls_or_guide",
            "description": "Search the internet for PC keyboard controls, menu navigation, or walkthrough tips.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "game_name": {"type": "string", "default": "Persona 3 Reload"},
                },
                "required": ["question"],
            },
        },
    },
]

_SYSTEM_PROMPT = (
    "You are an autonomous desktop voice assistant controlling a Windows PC.\n"
    "{learned_guidance}\n"
    "Always use your tools to perform user requests:\n"
    "- show_desktop: minimizes all windows and shows the desktop. Call this when user wants to go to desktop or see desktop icons.\n"
    "- open_or_switch_app: opens or switches to an application or game like Discord, Steam, Spotify.\n"
    "- search_or_open_website: searches Google or YouTube, or opens URLs. Only use when user explicitly asks to browse the web.\n"
    "- switch_browser_tab: switches to an open browser tab.\n"
    "- type_text_into_active_window: types text into active window.\n"
    "- press_keyboard_key: presses any keyboard key or shortcut (e.g. enter, esc, space, win+d).\n"
    "- hold_keyboard_key: holds down a key for a duration in seconds (e.g. walking, sprinting, charging).\n"
    "- move_game_character: moves a game character forward, backward, left, or right with optional sprinting.\n"
    "- play_game_autonomously: when the user asks to advance dialogue, talk to an NPC, or play through a game sequence.\n"
    "- see_screen_and_act: captures the screen and visually locates and interacts with UI elements (like desktop icons or buttons).\n"
    "- research_game_controls_or_guide: searches the internet for game controls or guides.\n"
    "When the user asks to click, double click, or find an icon on the desktop or screen, call see_screen_and_act.\n"
    "If the desktop is not currently visible, you can first call show_desktop or press_keyboard_key('win+d') before see_screen_and_act.\n"
    "After calling a tool, reply in 1 concise, natural spoken sentence confirming the action.\n"
    "Never use markdown formatting, bullets, or symbols."
)


def _clean_spoken_text(text: str) -> str:
    cleaned = text.lower().strip()
    cleaned = re.sub(r"[^\w\s]", "", cleaned)
    cleaned = re.sub(r"^(?:can you|could you|please|would you|just|hey|agent)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*(?:please|for me|now|right now)?$", "", cleaned)
    for misheard, intended in global_memory.get_stt_aliases().items():
        cleaned = re.sub(rf"\b{re.escape(misheard)}\b", intended, cleaned)
    return cleaned.strip()


def _check_local_hardware_reflex(text: str) -> Optional[Tuple[str, str]]:
    c = _clean_spoken_text(text)
    num_map = {
        "once": 1, "twice": 2, "two": 2, "three": 3, "four": 4,
        "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    }

    # Desktop navigation reflexes
    if any(k in c for k in ("go to desktop", "go to my desktop", "show desktop", "minimize all", "back to desktop", "switch to desktop", "open desktop")):
        press_key("win+d")
        return ("show_desktop", "Showed desktop.")

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

    is_game_intent = any(k in c for k in ("game", "character", "play through", "autopilot", "shapes", "hexagon", "screen", "figure it out"))
    if not is_game_intent:
        if c in ("pause", "unpause", "play", "resume", "freeze", "toggle playback", "pause playback", "play music", "pause music", "stop music"):
            press_key("space")
            return ("pause_resume", "Toggled playback.")
        elif any(k in c for k in ("space bar", "spacebar", "hit space", "press space", "tap space")):
            press_key("space")
            return ("press_key", "Pressed space.")

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

    def __init__(self, model_id: str = "gemini-3.5-flash-lite", backend: str = "auto") -> None:
        self.backend = backend
        self.model_id = model_id
        self._gemini_agent = None
        self._subq_client: Optional[SubQSavantClient] = None
        self._subq_available = False
        self._gemini_available = False
        self._active_backend = "none"
        self._request_count = 0
        self._subq_failures = 0
        self._gemini_failures = 0

        gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        subq_key = os.environ.get("SUBQ_API_KEY", "")

        self.vision = VisionComputerUse(api_key=gemini_key)
        self.game_copilot = AutonomousGameCopilot(api_key=gemini_key)

        if subq_key:
            self._subq_client = SubQSavantClient(api_key=subq_key)
            learned_guidance = global_memory.get_learned_prompt_context()
            system_prompt = _SYSTEM_PROMPT.format(learned_guidance=learned_guidance)
            self._subq_client.push_system_message(system_prompt)
            self._subq_available = True
            logger.info("[Agent] SubQ Savant client initialized (subq-savant-1.4)")

        if gemini_key:
            from agno.agent import Agent
            from agno.models.google import Gemini

            vision_engine = self.vision
            copilot_engine = self.game_copilot

            async def see_screen_and_act(instruction: str) -> str:
                return await vision_engine.perceive_and_act(instruction)

            async def play_game_autonomously(objective: str, max_steps: int = 5) -> str:
                return await copilot_engine.run_game_loop(objective, max_steps=max_steps)

            def show_desktop() -> str:
                press_key("win+d")
                return "Showed desktop."

            def open_or_switch_app(app_name: str) -> str:
                return open_app_or_game(app_name)

            def search_or_open_website(query_or_url: str, site: str = "") -> str:
                return desktop_search_or_open(query_or_url, site)

            def switch_browser_tab(tab_name: str = "") -> str:
                return desktop_switch_tab(tab_name)

            def type_text_into_active_window(text: str, press_enter: bool = True) -> str:
                return type_text(text, press_enter=press_enter)

            def press_keyboard_key(key: str) -> str:
                return press_key(key)

            def hold_keyboard_key(key: str, duration: float = 1.0) -> str:
                return hold_key(key, duration=duration)

            def move_game_character(direction: str = "forward", duration: float = 1.5, sprint: bool = False) -> str:
                return move_game(direction, duration=duration, sprint=sprint)

            async def research_game_controls_or_guide(question: str, game_name: str = "Persona 3 Reload") -> str:
                return await research_game_knowledge(question, game_name)

            learned_guidance = global_memory.get_learned_prompt_context()

            self._gemini_agent = Agent(
                model=Gemini(id=model_id, api_key=gemini_key),
                tools=[
                    show_desktop,
                    open_or_switch_app,
                    search_or_open_website,
                    switch_browser_tab,
                    type_text_into_active_window,
                    press_keyboard_key,
                    hold_keyboard_key,
                    move_game_character,
                    see_screen_and_act,
                    play_game_autonomously,
                    research_game_controls_or_guide,
                ],
                instructions=_SYSTEM_PROMPT.format(learned_guidance=learned_guidance),
                markdown=False,
            )
            self._gemini_available = True

        if backend == "auto":
            self._active_backend = "subq" if self._subq_available else "gemini"
        elif backend == "subq":
            self._active_backend = "subq"
        else:
            self._active_backend = "gemini"

    def _select_backend(self) -> str:
        if self.backend != "auto":
            return self._active_backend

        # SubQ Savant is 100% the primary model for everything
        if self._subq_available and self._subq_failures < 3:
            return "subq"

        if self._gemini_available:
            return "gemini"

        return self._active_backend

    async def _execute_tool(self, name: str, args: dict) -> str:
        dispatch = {
            "show_desktop": lambda a: (press_key("win+d"), "Showed desktop.")[1],
            "open_or_switch_app": lambda a: open_app_or_game(a.get("app_name", "")),
            "search_or_open_website": lambda a: desktop_search_or_open(a.get("query_or_url", ""), a.get("site", "")),
            "switch_browser_tab": lambda a: desktop_switch_tab(a.get("tab_name", "")),
            "type_text_into_active_window": lambda a: type_text(a.get("text", ""), press_enter=a.get("press_enter", True)),
            "press_keyboard_key": lambda a: press_key(a.get("key", "")),
            "hold_keyboard_key": lambda a: hold_key(a.get("key", ""), duration=float(a.get("duration", 1.0))),
            "move_game_character": lambda a: move_game(
                a.get("direction", "forward"),
                duration=float(a.get("duration", 1.5)),
                sprint=bool(a.get("sprint", False)),
            ),
        }

        async_dispatch = {
            "see_screen_and_act": lambda a: self.vision.perceive_and_act(a.get("instruction", "")),
            "play_game_autonomously": lambda a: self.game_copilot.run_game_loop(
                a.get("objective", ""), max_steps=int(a.get("max_steps", 5))
            ),
            "research_game_controls_or_guide": lambda a: research_game_knowledge(
                a.get("question", ""), a.get("game_name", "Persona 3 Reload")
            ),
        }

        if name in dispatch:
            return await asyncio.to_thread(dispatch[name], args)
        elif name in async_dispatch:
            return await async_dispatch[name](args)
        else:
            return f"Unknown tool: {name}"

    async def warmup(self) -> None:
        await self.vision.warmup()

    async def respond(self, text: str) -> AsyncIterator[AgentEvent]:
        t0 = time.perf_counter()
        self._request_count += 1

        reflex = _check_local_hardware_reflex(text)
        if reflex:
            action, ack = reflex
            total_ms = (time.perf_counter() - t0) * 1000
            print(f"\n  ⚡ [Local Reflex] {action} -> Done in {total_ms:.1f}ms\n  ✅ {ack}", flush=True)
            yield AgentEvent.text(ack)
            return

        app_switch_ack = _check_local_app_or_tab_switch(text)
        if app_switch_ack:
            total_ms = (time.perf_counter() - t0) * 1000
            print(f"\n  ⚡ [Process Radar] {app_switch_ack} -> Done in {total_ms:.1f}ms", flush=True)
            yield AgentEvent.text(app_switch_ack)
            return

        backend = self._select_backend()
        print(f"\n  🧠 [SubQ Controller] Reasoning on: '{text}'...", flush=True)

        if backend == "subq" and self._subq_client:
            try:
                response_text = await self._subq_client.run_tool_loop(
                    user_input=text,
                    tools_openai=OPENAI_TOOLS,
                    tool_executor=self._execute_tool,
                    max_rounds=5,
                )
                total_ms = (time.perf_counter() - t0) * 1000
                print(f"  ⚡ [SubQ Savant] Done in {total_ms:.0f}ms: {response_text[:120]}", flush=True)
                self._subq_failures = 0
                yield AgentEvent.text(response_text)
                return

            except Exception as exc:
                self._subq_failures += 1
                err_str = str(exc)
                logger.warning("[Agent] SubQ error (%d/3): %s", self._subq_failures, err_str)
                print(f"  ⚠️ [SubQ Savant] Error, falling back to Gemini: {err_str[:80]}", flush=True)

                if self._gemini_available and self._gemini_agent:
                    backend = "gemini"
                else:
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        yield AgentEvent.text("I'm hitting a quick API quota limit, please give me a few seconds.")
                    else:
                        yield AgentEvent.text("Sorry, I had a momentary connection hiccup.")
                    return

        if backend == "gemini" and self._gemini_agent:
            try:
                stream = self._gemini_agent.arun(text, stream=True, stream_events=True)
                async for event in stream:
                    kind = getattr(event, "event", "")
                    content = getattr(event, "content", None)
                    if kind == "RunContent" and isinstance(content, str) and content:
                        yield AgentEvent.text(content)
                self._gemini_failures = 0
                return

            except Exception as exc:
                self._gemini_failures += 1
                err_str = str(exc)
                logger.warning("[Agent] Gemini error: %s", err_str)
                yield AgentEvent.text("Sorry, I had a momentary connection hiccup.")
                return

        yield AgentEvent.text("No AI backend is available. Please check your API keys.")

    def get_status(self) -> dict:
        return {
            "active_backend": self._active_backend,
            "subq_available": self._subq_available,
            "gemini_available": self._gemini_available,
            "total_requests": self._request_count,
            "subq_failures": self._subq_failures,
            "gemini_failures": self._gemini_failures,
        }

    async def close(self) -> None:
        await self.vision.close()
        await self.game_copilot.close()
        if self._subq_client:
            await self._subq_client.close()
