from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import os
import subprocess
import time
import urllib.parse
from typing import List, Optional, Tuple

import pyautogui
import pytweening

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.15

logger = logging.getLogger("reflex.desktop")
_user32 = ctypes.windll.user32


def attach_to_input_desktop() -> bool:
    try:
        h_input = _user32.OpenInputDesktop(0, False, 0x01FF)
        if h_input:
            _user32.SetThreadDesktop(h_input)
            return True
    except Exception:
        pass
    return False


def get_visible_windows() -> List[Tuple[int, str]]:
    attach_to_input_desktop()
    results: List[Tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd: int, _: int) -> bool:
        if _user32.IsWindowVisible(hwnd):
            length = _user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                _user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.strip()
                if title:
                    results.append((hwnd, title))
        return True

    _user32.EnumWindows(_cb, 0)
    return results


def find_window_hwnd(query: str) -> Optional[Tuple[int, str]]:
    q = query.lower().strip()
    for hwnd, title in get_visible_windows():
        if q in title.lower():
            return hwnd, title
    return None


def focus_window(query: str) -> bool:
    attach_to_input_desktop()
    match = find_window_hwnd(query)
    if not match:
        return False

    hwnd, title = match
    logger.info("Focusing window %r (hwnd=%d)", title, hwnd)

    if _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, 9)
    else:
        _user32.ShowWindow(hwnd, 5)

    _user32.keybd_event(0x12, 0, 0, 0)
    _user32.SetForegroundWindow(hwnd)
    _user32.keybd_event(0x12, 0, 2, 0)
    time.sleep(0.15)
    return True


def focus_browser() -> bool:
    for b in ("Brave", "Chrome", "Edge", "Firefox", "Opera"):
        if focus_window(b):
            return True
    return False


def switch_browser_tab(tab_name: str = "") -> str:
    attach_to_input_desktop()
    clean_tab = tab_name.strip()
    logger.info("Switching to tab: %s", clean_tab)
    focus_browser()
    time.sleep(0.12)

    pyautogui.hotkey("ctrl", "shift", "a")
    time.sleep(0.18)

    if clean_tab and clean_tab.lower() not in ("check", "tabs", "all", "show", "open", ""):
        pyautogui.write(clean_tab, interval=0.02)
        time.sleep(0.18)
        pyautogui.press("enter")
        time.sleep(0.1)
        return f"Switched to {clean_tab} tab."
    else:
        return "Opened tab search for your open tabs."


def open_app_or_game(app_name: str) -> str:
    attach_to_input_desktop()
    clean_name = app_name.strip()
    logger.info("Opening app/game: %s", clean_name)

    if focus_window(clean_name):
        return f"Switched to {clean_name}."

    pyautogui.press("win")
    time.sleep(0.2)
    pyautogui.write(clean_name, interval=0.03)
    time.sleep(0.3)
    pyautogui.press("enter")

    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", f"Start-Process '{clean_name}'"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        pass

    return f"Launched {clean_name}."


def search_or_open_website(query_or_url: str, site: str = "") -> str:
    attach_to_input_desktop()
    clean = query_or_url.strip()
    site_lower = site.lower().strip()

    if site_lower == "youtube" or "youtube.com" in clean.lower():
        encoded = urllib.parse.quote_plus(clean)
        url = f"https://www.youtube.com/results?search_query={encoded}"
        label = f"YouTube search for '{clean}'"
    elif clean.startswith("http://") or clean.startswith("https://"):
        url = clean
        label = clean
    elif any(clean.endswith(ext) or ext + "/" in clean for ext in (".com", ".org", ".io", ".net", ".edu", ".gov", ".gg", ".ai")):
        url = f"https://{clean}"
        label = url
    else:
        encoded = urllib.parse.quote_plus(clean)
        url = f"https://www.google.com/search?q={encoded}"
        label = f"search for '{clean}'"

    logger.info("Opening URL: %s", url)
    os.system(f'start "" "{url}"')
    time.sleep(0.5)
    focus_browser()
    return f"Opened {label} in your browser."


def scroll_screen(direction: str = "down", amount: int = 3) -> str:
    attach_to_input_desktop()
    clicks = int(amount) * 150
    if direction.lower().strip() == "down":
        pyautogui.scroll(-clicks)
    else:
        pyautogui.scroll(clicks)
    return f"Scrolled {direction}."


def press_key(key: str) -> str:
    attach_to_input_desktop()
    clean_key = key.strip().lower()
    logger.info("Pressing key: %s", clean_key)
    if "+" in clean_key:
        keys = [k.strip() for k in clean_key.split("+")]
        pyautogui.hotkey(*keys)
    else:
        pyautogui.press(clean_key)
    return f"Pressed '{clean_key}'."


def type_text(text: str, press_enter: bool = False) -> str:
    attach_to_input_desktop()
    logger.info("Typing text: %s", text)
    pyautogui.write(text, interval=0.03)
    if press_enter:
        time.sleep(0.12)
        pyautogui.press("enter")
    return f"Typed '{text}'."


def move_and_click(x: int, y: int, button: str = "left", duration: float = 0.4) -> str:
    attach_to_input_desktop()
    pyautogui.moveTo(x, y, duration=duration, tween=pytweening.easeInOutQuad)
    time.sleep(0.12)
    pyautogui.mouseDown(button=button)
    time.sleep(0.06)
    pyautogui.mouseUp(button=button)
    time.sleep(0.1)
    return f"Clicked at ({x}, {y})."
