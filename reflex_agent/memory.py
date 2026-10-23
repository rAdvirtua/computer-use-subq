from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("reflex.memory")

_DEFAULT_MEMORY: Dict[str, Any] = {
    "games": {
        "persona 3 reload": {
            "controls": {
                "interact": ["enter", "e", "space"],
                "advance_dialogue": ["space", "enter"],
                "menu": "tab",
                "confirm": "enter",
                "cancel": "esc",
                "save": "tab -> system -> enter",
            },
            "successful_actions": {
                "dialogue_advance": "space",
                "menu_confirm": "enter",
                "menu_open": "tab",
            },
            "failed_actions": {
                "npc_interact_c": 5,
            },
            "rules": [
                "Press space to advance dialogue and text boxes.",
                "To interact with NPCs or objects, try Enter or E if C does not trigger conversation.",
                "To save: press Tab to open menu, navigate down to System, press Enter, select Save.",
                "In confirmation prompts like Return to Title, use Enter to confirm, not mouse clicks.",
            ],
        }
    },
    "stt_aliases": {
        "recipes": "press c",
        "recipe": "press c",
        "bar": "space bar",
        "breastfeed": "press space",
        "breastpiece": "press space",
        "piece": "space",
        "peace": "space",
        "sieve": "save",
        "squeeze work": "space bar",
        "squeeze bar": "space bar",
        "space where": "space bar",
    },
    "history": [],
}


class MemoryManager:

    def __init__(self, file_path: Optional[Path] = None) -> None:
        if file_path is None:
            data_dir = Path(__file__).parent / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            self.file_path = data_dir / "learned_memory.json"
        else:
            self.file_path = file_path
        self._data: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        if self.file_path.exists():
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                    return
            except Exception as exc:
                logger.warning("Failed to load memory from %s: %s", self.file_path, exc)
        self._data = dict(_DEFAULT_MEMORY)
        self.save()

    def save(self) -> None:
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.file_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
            tmp_path.replace(self.file_path)
        except Exception as exc:
            logger.warning("Failed to save memory to %s: %s", self.file_path, exc)

    def get_stt_aliases(self) -> Dict[str, str]:
        return self._data.get("stt_aliases", {})

    def add_stt_alias(self, misheard: str, intended: str) -> None:
        aliases = self._data.setdefault("stt_aliases", {})
        aliases[misheard.lower().strip()] = intended.lower().strip()
        self.save()

    def get_game_profile(self, game_name: str) -> Dict[str, Any]:
        games = self._data.setdefault("games", {})
        clean = game_name.lower().strip()
        for k, v in games.items():
            if k in clean or clean in k:
                return v
        profile: Dict[str, Any] = {
            "controls": {},
            "successful_actions": {},
            "failed_actions": {},
            "rules": [],
        }
        games[clean] = profile
        self.save()
        return profile

    def record_action_outcome(self, game_name: str, context: str, action: str, success: bool) -> None:
        profile = self.get_game_profile(game_name)
        if success:
            succ = profile.setdefault("successful_actions", {})
            succ[context] = action
            logger.info("[Memory] Learned successful action for %s (%s): %s", game_name, context, action)
        else:
            fails = profile.setdefault("failed_actions", {})
            key = f"{context}_{action}"
            fails[key] = fails.get(key, 0) + 1
            logger.info("[Memory] Recorded failed action for %s (%s): %s (%d times)", game_name, context, action, fails[key])
        self.save()

    def record_learned_rule(self, game_name: str, rule: str) -> None:
        profile = self.get_game_profile(game_name)
        rules: List[str] = profile.setdefault("rules", [])
        if rule not in rules:
            rules.append(rule)
            logger.info("[Memory] Added learned rule for %s: %s", game_name, rule)
            self.save()

    def get_learned_prompt_context(self, active_game: str = "") -> str:
        lines: List[str] = []
        games = self._data.get("games", {})
        for g_name, profile in games.items():
            if active_game and (g_name not in active_game.lower() and active_game.lower() not in g_name):
                continue
            lines.append(f"Game: {g_name.title()}")
            controls = profile.get("controls", {})
            if controls:
                lines.append(f"  Key Controls: {json.dumps(controls)}")
            rules = profile.get("rules", [])
            for r in rules[-4:]:
                lines.append(f"  Learned Rule: {r}")
            succ = profile.get("successful_actions", {})
            if succ:
                lines.append(f"  Proven Actions: {json.dumps(succ)}")
        if not lines:
            return ""
        return "LEARNED GAMEPLAY MEMORY & PROVEN CONTROLS:\n" + "\n".join(lines)


global_memory = MemoryManager()
