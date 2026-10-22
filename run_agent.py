import asyncio
import logging
import os
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
from yapwrap.stt import DeepgramSTT
from yapwrap.tts import CartesiaTTS
from yapwrap.vad import SileroVAD

from reflex_agent import ReflexDesktopAgent, EchoSafeLocalTransport


async def main() -> None:
    print("\n" + "=" * 60)
    print("  YapWrap Voice Agent (SubQ Snap Reflex + Gemini Tool Control)")
    print("=" * 60)
    model_name = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")
    print(f"  Gemini Model   : {model_name}")
    print(f"  Deepgram STT   : {'OK' if os.environ.get('DEEPGRAM_API_KEY') else 'MISSING'}")
    print(f"  Cartesia TTS   : {'OK' if os.environ.get('CARTESIA_API_KEY') else 'MISSING'}")
    print(f"  SubQ Snap      : {'OK' if os.environ.get('SUBQ_API_KEY') else 'MISSING'}")
    print(f"  System 1 Reflex: SubQ Snap (<80ms)")
    print(f"  System 2 Tools : Native Windows + Chromium Tab Search + Vision")
    print("=" * 60)
    print("\nWaiting for audio session to come online...\n")

    agent = ReflexDesktopAgent(model_id=model_name)
    await agent.warmup()

    yapper = YapWrap(
        agent=agent,
        stt=DeepgramSTT(),
        tts=CartesiaTTS(),
        vad=SileroVAD(),
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
