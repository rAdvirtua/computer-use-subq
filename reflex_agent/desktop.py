from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import os
import subprocess
import time
import urllib.parse
from typing import List, Optional, Tuple

import pydirectinput
import pyautogui
import pytweening

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.15
pydirectinput.FAILSAFE = False
pydirectinput.PAUSE = 0.0

logger = logging.getLogger("reflex.desktop")
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

APP_ALIASES = {
    "discord": ["discord.exe"],
    "code": ["code.exe"],
    "vscode": ["code.exe"],
    "visual studio code": ["code.exe"],
    "my code": ["code.exe"],
    "spotify": ["spotify.exe"],
    "music": ["spotify.exe"],
    "steam": ["steam.exe"],
    "notepad": ["notepad.exe"],
    "notes": ["notepad.exe"],
    "terminal": ["windowsterminal.exe", "powershell.exe", "cmd.exe"],
    "powershell": ["powershell.exe"],
    "cmd": ["cmd.exe"],
    "browser": ["brave.exe", "chrome.exe", "msedge.exe", "firefox.exe", "opera.exe"],
    "chrome": ["chrome.exe"],
    "brave": ["brave.exe"],
    "edge": ["msedge.exe"],
    "firefox": ["firefox.exe"],
    "calculator": ["calculatorapp.exe", "calc.exe"],
    "settings": ["systemsettings.exe"],
    "explorer": ["explorer.exe"],
    "files": ["explorer.exe"],
}


def attach_to_input_desktop() -> bool:
    try:
        h_input = _user32.OpenInputDesktop(0, False, 0x01FF)
        if h_input:
            _user32.SetThreadDesktop(h_input)
            return True
    except Exception:
        pass
    return False


def get_open_process_windows() -> List[Tuple[int, str, str]]:
    attach_to_input_desktop()
    results: List[Tuple[int, str, str]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_cb(hwnd: int, _: int) -> bool:
        if _user32.IsWindowVisible(hwnd):
            length = _user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                pid = wintypes.DWORD()
                _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                h_proc = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
                if h_proc:
                    buf = ctypes.create_unicode_buffer(512)
                    size = wintypes.DWORD(512)
                    exe_name = ""
                    if _kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
                        exe_name = buf.value.split("\\")[-1].lower()
                    _kernel32.CloseHandle(h_proc)

                    title_buf = ctypes.create_unicode_buffer(length + 1)
                    _user32.GetWindowTextW(hwnd, title_buf, length + 1)
                    title = title_buf.value.strip()

                    if exe_name or title:
                        results.append((hwnd, exe_name, title))
        return True

    _user32.EnumWindows(enum_cb, 0)
    return results


def focus_window_hwnd(hwnd: int) -> bool:
    attach_to_input_desktop()
    if not _user32.IsWindow(hwnd):
        return False

    if _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, 9)
    else:
        _user32.ShowWindow(hwnd, 5)

    _user32.keybd_event(0x12, 0, 0, 0)
    _user32.SetForegroundWindow(hwnd)
    _user32.keybd_event(0x12, 0, 2, 0)
    time.sleep(0.08)
    return True


def focus_app_by_process(query: str) -> bool:
    clean = query.lower().strip()
    target_exes = APP_ALIASES.get(clean, [clean + ".exe" if not clean.endswith(".exe") else clean])

    proc_windows = get_open_process_windows()

    for hwnd, exe, _ in proc_windows:
        if exe in target_exes:
            return focus_window_hwnd(hwnd)

    for hwnd, exe, title in proc_windows:
        if clean in exe or clean in title.lower():
            return focus_window_hwnd(hwnd)

    return False


def focus_browser() -> bool:
    proc_windows = get_open_process_windows()
    browser_exes = {"brave.exe", "chrome.exe", "msedge.exe", "firefox.exe", "opera.exe"}
    for hwnd, exe, _ in proc_windows:
        if exe in browser_exes:
            return focus_window_hwnd(hwnd)
    return False


def switch_browser_tab(tab_name: str = "") -> str:
    attach_to_input_desktop()
    clean_tab = tab_name.strip()
    logger.info("Switching to tab: %s", clean_tab)
    focus_browser()
    time.sleep(0.08)

    pyautogui.hotkey("ctrl", "shift", "a")
    time.sleep(0.15)

    if clean_tab and clean_tab.lower() not in ("check", "tabs", "all", "show", "open", ""):
        pyautogui.write(clean_tab, interval=0.02)
        time.sleep(0.15)
        pyautogui.press("enter")
        time.sleep(0.08)
        return f"Switched to {clean_tab} tab."
    else:
        return "Opened tab search for your open tabs."


def open_app_or_game(app_name: str) -> str:
    attach_to_input_desktop()
    clean_name = app_name.strip()
    logger.info("Opening app/game: %s", clean_name)

    if focus_app_by_process(clean_name):
        return f"Switched to {clean_name}."

    pyautogui.press("win")
    time.sleep(0.18)
    pyautogui.write(clean_name, interval=0.03)
    time.sleep(0.25)
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
    time.sleep(0.4)
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


def press_key(key: str, hold_duration: float = 0.06) -> str:
    attach_to_input_desktop()
    clean_key = key.strip().lower()
    logger.info("Pressing key: %s", clean_key)
    if "+" in clean_key:
        keys = [k.strip() for k in clean_key.split("+")]
        try:
            for k in keys:
                mapped = "escape" if k == "esc" else k
                if mapped in pydirectinput.KEYBOARD_MAPPING:
                    pydirectinput.keyDown(mapped)
                else:
                    pyautogui.keyDown(k)
            time.sleep(hold_duration)
            for k in reversed(keys):
                mapped = "escape" if k == "esc" else k
                if mapped in pydirectinput.KEYBOARD_MAPPING:
                    pydirectinput.keyUp(mapped)
                else:
                    pyautogui.keyUp(k)
        except Exception:
            pyautogui.hotkey(*keys)
    else:
        mapped = "escape" if clean_key == "esc" else clean_key
        if mapped in pydirectinput.KEYBOARD_MAPPING:
            try:
                pydirectinput.keyDown(mapped)
                time.sleep(hold_duration)
                pydirectinput.keyUp(mapped)
            except Exception:
                pyautogui.press(clean_key)
        else:
            pyautogui.press(clean_key)
    return f"Pressed '{clean_key}'."


def hold_key(key: str, duration: float = 1.0) -> str:
    attach_to_input_desktop()
    clean_key = key.strip().lower()
    clamped_duration = max(0.05, min(duration, 15.0))
    logger.info("Holding key: %s for %.2fs", clean_key, clamped_duration)
    press_key(clean_key, hold_duration=clamped_duration)
    return f"Held '{clean_key}' for {clamped_duration:.1f}s."


def repeat_key(key: str, times: int = 1, interval: float = 0.12) -> str:
    attach_to_input_desktop()
    clean_key = key.strip().lower()
    count = max(1, min(times, 20))
    logger.info("Repeating key: %s %d times", clean_key, count)
    for i in range(count):
        press_key(clean_key, hold_duration=0.07)
        if i < count - 1:
            time.sleep(interval)
    return f"Pressed '{clean_key}' {count} times."


def move_game(direction: str = "forward", duration: float = 1.5, sprint: bool = False) -> str:
    attach_to_input_desktop()
    clean_dir = direction.strip().lower()
    dir_map = {
        "forward": "w",
        "front": "w",
        "ahead": "w",
        "up": "w",
        "backward": "s",
        "back": "s",
        "reverse": "s",
        "down": "s",
        "left": "a",
        "right": "d",
    }
    key = dir_map.get(clean_dir, "w")
    target = f"shift+{key}" if sprint else key
    hold_key(target, duration=duration)
    mode = "Sprinted" if sprint else "Moved"
    return f"{mode} {clean_dir} for {duration:.1f}s."


def type_text(text: str, press_enter: bool = False) -> str:
    attach_to_input_desktop()
    logger.info("Typing text: %s", text)
    for char in text:
        char_lower = char.lower()
        if char_lower in pydirectinput.KEYBOARD_MAPPING:
            try:
                pydirectinput.keyDown(char_lower)
                time.sleep(0.02)
                pydirectinput.keyUp(char_lower)
            except Exception:
                pyautogui.write(char)
        else:
            pyautogui.write(char)
        time.sleep(0.02)
    if press_enter:
        time.sleep(0.08)
        press_key("enter")
    return f"Typed '{text}'."


def move_and_click(x: int, y: int, button: str = "left", duration: float = 0.35) -> str:
    attach_to_input_desktop()
    pyautogui.moveTo(x, y, duration=duration, tween=pytweening.easeInOutQuad)
    time.sleep(0.1)
    pyautogui.mouseDown(button=button)
    time.sleep(0.05)
    pyautogui.mouseUp(button=button)
    time.sleep(0.08)
    return f"Clicked at ({x}, {y})."
