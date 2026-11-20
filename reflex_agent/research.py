from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import List

import httpx

from .memory import global_memory

logger = logging.getLogger("reflex.research")


async def search_web_snippets(query: str, max_results: int = 4) -> List[str]:
    clean_query = query.strip()
    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    data = {"q": clean_query}

    try:
        async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
            resp = await client.post(url, data=data, headers=headers)
            if resp.status_code == 200:
                raw_snippets = re.findall(r"result__snippet[^>]*>(.*?)</a>", resp.text, re.DOTALL)
                clean_snippets = [
                    re.sub(r"<[^>]+>", "", s).replace("&#x27;", "'").replace("&quot;", '"').strip()
                    for s in raw_snippets
                    if s.strip()
                ]
                return clean_snippets[:max_results]
    except Exception as exc:
        logger.warning("[research] search failed: %s", exc)

    return []


async def research_game_knowledge(query: str, game_name: str = "") -> str:
    search_term = f"{game_name} {query}".strip() if game_name and game_name.lower() not in query.lower() else query
    print(f"[research] query: '{search_term}'", flush=True)

    snippets = await search_web_snippets(search_term, max_results=4)
    if not snippets:
        return f"No web results for '{search_term}'."

    joined_snippets = "\n".join(f"- {s}" for s in snippets)

    subq_key = os.environ.get("SUBQ_API_KEY", "")
    if subq_key:
        prompt = (
            f"Question: {query}\n"
            f"Context: {game_name or 'PC Game'}\n"
            f"Snippets:\n{joined_snippets}\n"
            "Provide a 2-sentence actionable guide on keyboard keys or menu options in brackets, e.g. [Enter], [Space]."
        )
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(
                    "https://api.subq.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {subq_key}"},
                    json={
                        "model": "subq-savant-1.4",
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                if r.status_code == 200:
                    answer = r.json()["choices"][0]["message"]["content"].strip()
                    print(f"[research] result: {answer}", flush=True)
                    target_game = game_name or "active_game"
                    global_memory.record_learned_rule(target_game, answer)
                    return answer
        except Exception as exc:
            logger.warning("[research] subq synthesis failed: %s", exc)

    return f"Web findings for {search_term}:\n{joined_snippets}"
