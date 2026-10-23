from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import List, Optional

from google.genai import types
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
        logger.warning("[Research] Web snippet search failed: %s", exc)

    return []


async def research_game_knowledge(query: str, game_name: str = "") -> str:
    search_term = f"{game_name} {query}".strip() if game_name and game_name.lower() not in query.lower() else query
    logger.info("[Research] Searching internet for: '%s'", search_term)
    print(f"\n🌐 [Web Research] Searching internet for: '{search_term}'...", flush=True)

    snippets = await search_web_snippets(search_term, max_results=4)
    if not snippets:
        return f"Could not find live web results for '{search_term}'."

    joined_snippets = "\n".join(f"- {s}" for s in snippets)

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return f"Web findings for {search_term}:\n{joined_snippets}"

    from google import genai
    client = genai.Client(api_key=api_key)

    prompt = (
        f"You are a gaming expert assisting an autonomous computer-use agent.\n"
        f"Question: {query}\n"
        f"Game Context: {game_name or 'PC Game'}\n\n"
        f"Web Search Snippets:\n{joined_snippets}\n\n"
        f"Provide a clear, 2-sentence actionable guide on the exact PC keyboard keys, menu options, or steps to perform this in the game.\n"
        f"Format key names explicitly in brackets, e.g. [Enter], [Space], [Tab], [Esc], [E], [C]."
    )

    try:
        resp = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=300,
            ),
        )
        answer = resp.text.strip()
        print(f"  💡 [Web Research Answer] {answer}", flush=True)

        target_game = game_name or "active_game"
        global_memory.record_learned_rule(target_game, answer)

        return answer
    except Exception as exc:
        logger.warning("[Research] Gemini synthesis failed: %s", exc)
        return f"Web findings for {search_term}:\n{joined_snippets}"
