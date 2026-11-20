from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("reflex.subq")

_BASE_URL = "https://api.subq.ai/v1"
_DEFAULT_MODEL = "subq-savant-1.4"
_MAX_RETRIES = 2
_TIMEOUT = 30.0


class SubQSavantClient:

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = _DEFAULT_MODEL,
    ) -> None:
        self.api_key = api_key or os.environ.get("SUBQ_API_KEY", "")
        self.model = model
        self._client: Optional[httpx.AsyncClient] = None
        self._conversation_history: List[Dict[str, Any]] = []
        self._max_history = 50

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=_BASE_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=_TIMEOUT,
                limits=httpx.Limits(
                    max_keepalive_connections=5,
                    keepalive_expiry=120.0,
                ),
            )
        return self._client

    def push_system_message(self, content: str) -> None:
        if self._conversation_history and self._conversation_history[0]["role"] == "system":
            self._conversation_history[0]["content"] = content
        else:
            self._conversation_history.insert(0, {"role": "system", "content": content})

    def push_user_message(self, content: str) -> None:
        self._conversation_history.append({"role": "user", "content": content})
        self._trim_history()

    def push_assistant_message(self, content: str) -> None:
        self._conversation_history.append({"role": "assistant", "content": content})
        self._trim_history()

    def push_tool_result(self, tool_call_id: str, name: str, content: str) -> None:
        self._conversation_history.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": content,
        })

    def _trim_history(self) -> None:
        sys_msg = None
        if self._conversation_history and self._conversation_history[0]["role"] == "system":
            sys_msg = self._conversation_history[0]
            rest = self._conversation_history[1:]
        else:
            rest = self._conversation_history

        if len(rest) > self._max_history:
            rest = rest[-self._max_history:]

        self._conversation_history = ([sys_msg] if sys_msg else []) + rest

    def clear_history(self) -> None:
        sys_msg = None
        if self._conversation_history and self._conversation_history[0]["role"] == "system":
            sys_msg = self._conversation_history[0]
        self._conversation_history = [sys_msg] if sys_msg else []

    async def chat_completion(
        self,
        messages: Optional[List[Dict[str, Any]]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        client = self._get_client()
        msgs = messages if messages is not None else list(self._conversation_history)

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": msgs,
        }
        if tools:
            payload["tools"] = tools

        last_error = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                t0 = time.perf_counter()
                resp = await client.post("/chat/completions", json=payload)
                latency_ms = (time.perf_counter() - t0) * 1000

                if resp.status_code == 429:
                    wait = min(2 ** attempt, 8)
                    logger.warning("[subq] rate limited (429), retry in %ds", wait)
                    await asyncio.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()
                data["_latency_ms"] = latency_ms
                return data

            except httpx.HTTPStatusError as exc:
                last_error = exc
                if exc.response.status_code >= 500:
                    wait = min(2 ** attempt, 8)
                    logger.warning("[subq] server error %d, retry in %ds", exc.response.status_code, wait)
                    await asyncio.sleep(wait)
                    continue
                raise
            except (httpx.ConnectError, httpx.ReadTimeout) as exc:
                last_error = exc
                wait = min(2 ** attempt, 8)
                logger.warning("[subq] connect error, retry in %ds", wait)
                await asyncio.sleep(wait)
                continue

        raise last_error or RuntimeError("subq request failed after retries")

    async def run_tool_loop(
        self,
        user_input: str,
        tools_openai: List[Dict[str, Any]],
        tool_executor: Any,
        max_rounds: int = 5,
    ) -> str:
        self.push_user_message(user_input)

        for _ in range(max_rounds):
            result = await self.chat_completion(
                messages=list(self._conversation_history),
                tools=tools_openai,
            )
            latency = result.get("_latency_ms", 0)
            choice = result["choices"][0]
            message = choice["message"]

            if message.get("tool_calls"):
                self._conversation_history.append(message)

                for tc in message["tool_calls"]:
                    fn_name = tc["function"]["name"]
                    fn_args_raw = tc["function"].get("arguments", "{}")
                    try:
                        fn_args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else fn_args_raw
                    except json.JSONDecodeError:
                        fn_args = {}

                    logger.info("[subq] tool: %s(%s) (%.0fms)", fn_name, fn_args, latency)
                    print(f"[tool] {fn_name}({fn_args}) ({latency:.0f}ms)", flush=True)

                    try:
                        tool_result = await tool_executor(fn_name, fn_args)
                    except Exception as exc:
                        tool_result = f"Error: {exc}"

                    self.push_tool_result(tc["id"], fn_name, str(tool_result))

                continue

            content = message.get("content", "")
            if content:
                self.push_assistant_message(content)
            return content or "Done."

        return "Completed."

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
