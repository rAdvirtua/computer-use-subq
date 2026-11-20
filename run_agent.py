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
        print(f"[warn] Could not read user env from registry: {exc}")


_load_user_env()

from yapwrap import YapWrap
from yapwrap.tts import CartesiaTTS
from yapwrap.vad import SileroVAD

from reflex_agent import ReflexDesktopAgent, EchoSafeLocalTransport, ResilientDeepgramSTT


async def run_text_interactive(agent: ReflexDesktopAgent) -> None:
    print("\n" + "=" * 60)
    print("  ⌨️  Interactive Text Console Mode")
    print("  Type any command (e.g. 'press space', 'open discord', 'help')")
    print("  Type 'exit' or 'quit' to stop.")
    print("=" * 60 + "\n")

    while True:
        try:
            user_input = await asyncio.to_thread(input, "\nYou > ")
            user_input = user_input.strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("Exiting interactive console.")
                break

            print("Agent > ", end="", flush=True)
            async for event in agent.respond(user_input):
                content = getattr(event, "content", "") or ""
                print(content, end="", flush=True)
            print()

        except (KeyboardInterrupt, EOFError):
            print("\nExiting interactive console.")
            break
        except Exception as exc:
            print(f"\n[Error] {exc}")


async def main() -> None:
    is_text_mode = "--text" in sys.argv or "-t" in sys.argv
    backend = os.environ.get("AGENT_BACKEND", "auto").lower()
    model_name = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
    has_subq = bool(os.environ.get("SUBQ_API_KEY"))
    has_gemini = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))

    print("\n" + "=" * 60)
    print("  Superhuman Desktop Agent v2 (Voice & SubQ Savant)")
    print("=" * 60)

    if backend == "auto":
        primary = "SubQ Savant" if has_subq else "Gemini"
        fallback = "Gemini" if has_subq and has_gemini else ("SubQ Savant" if has_gemini and has_subq else "None")
        print(f"  Routing        : Auto (Primary: {primary}, Fallback: {fallback})")
    elif backend == "subq":
        print(f"  Routing        : SubQ Savant Only")
    else:
        print(f"  Routing        : Gemini Only")

    print(f"  SubQ Savant    : {'OK (subq-savant-1.4, 4M ctx)' if has_subq else 'MISSING'}")
    print(f"  Gemini Model   : {model_name} {'(OK)' if has_gemini else '(MISSING)'}")
    print(f"  Deepgram STT   : {'OK (Resilient nova-3)' if os.environ.get('DEEPGRAM_API_KEY') else 'MISSING'}")
    print(f"  Cartesia TTS   : {'OK' if os.environ.get('CARTESIA_API_KEY') else 'MISSING'}")
    print(f"  SubQ Snap      : {'OK' if has_subq else 'MISSING'}")
    print(f"  Fast Radar     : Local Reflex (<1ms) + Win32 Process Snap (<5ms)")
    print(f"  Visual Loop    : Gemini Multimodal Vision + SubQ Snap Verifier (<300ms)")
    print(f"  Mode           : {'Text Console' if is_text_mode else 'Full Real-Time Voice'}")
    print("=" * 60)

    agent = ReflexDesktopAgent(model_id=model_name, backend=backend)
    await agent.warmup()

    if is_text_mode:
        try:
            await run_text_interactive(agent)
        finally:
            await agent.close()
        return

    print("\nWaiting for audio session to come online...\n")

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
        print("\nSession ended.")
