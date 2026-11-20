import asyncio
import logging
import os
import sys
import winreg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("yapwrap.transport.local").setLevel(logging.WARNING)


def _load_user_env() -> None:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
        i = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, i)
                if name not in os.environ:
                    os.environ[name] = value
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)
    except Exception as exc:
        print(f"[warn] registry env read failed: {exc}")


_load_user_env()

from yapwrap import YapWrap
from yapwrap.tts import CartesiaTTS
from yapwrap.vad import SileroVAD

from reflex_agent import ReflexDesktopAgent, EchoSafeLocalTransport, ResilientDeepgramSTT


async def run_text_interactive(agent: ReflexDesktopAgent) -> None:
    print("subq-desktop-agent (interactive console)")
    print("enter command or 'exit' to quit\n")

    while True:
        try:
            user_input = await asyncio.to_thread(input, "input> ")
            user_input = user_input.strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                break

            print("output> ", end="", flush=True)
            async for event in agent.respond(user_input):
                content = getattr(event, "content", "") or ""
                print(content, end="", flush=True)
            print()

        except (KeyboardInterrupt, EOFError):
            break
        except Exception as exc:
            print(f"[error] {exc}")


async def main() -> None:
    is_text_mode = "--text" in sys.argv or "-t" in sys.argv
    backend = os.environ.get("AGENT_BACKEND", "auto").lower()
    model_name = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
    has_subq = bool(os.environ.get("SUBQ_API_KEY"))

    print(f"subq-desktop-agent [backend: {'subq-savant-1.4' if has_subq else 'gemini'}, mode: {'text' if is_text_mode else 'voice'}]")

    agent = ReflexDesktopAgent(model_id=model_name, backend=backend)
    await agent.warmup()

    if is_text_mode:
        try:
            await run_text_interactive(agent)
        finally:
            await agent.close()
        return

    stt = ResilientDeepgramSTT(
        open_timeout=30.0,
        max_retries=2,
    )
    vad = SileroVAD(
        threshold=0.35,
        min_silence_duration_ms=400,
        speech_pad_ms=60,
    )

    yapper = YapWrap(
        agent=agent,
        stt=stt,
        tts=CartesiaTTS(),
        vad=vad,
    )

    transport = EchoSafeLocalTransport()
    try:
        await yapper.run(transport)
    finally:
        transport.stop()
        await agent.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nstopped.")
