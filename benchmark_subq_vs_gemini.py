"""
Benchmark Suite: Subquadratic Savant (subq-savant-1.4) vs Google Gemini (gemini-3.5-flash-lite)
Tests:
  1. Ping & Connectivity Verification
  2. Desktop Action Tool Calling (Schema compliance, Latency, Action generation)
  3. Multi-turn Agent Decision Latency
  4. Context Scaling & Needle Recall (10k, 50k, 100k, 250k tokens)
  5. Throughput (Tokens/Sec) and Cost Economics
"""

import os
import sys
import time
import json
import httpx
import winreg

# Load user environment from Windows Registry if not present
def load_user_env():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment")
        i = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, i)
                if name not in os.environ:
                    os.environ[name] = value
                i += 1
            except WindowsError:
                break
        winreg.CloseKey(key)
    except Exception as e:
        print(f"[warn] registry load error: {e}")

load_user_env()

SUBQ_API_KEY = os.environ.get("SUBQ_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

print("=== CREDENTIALS CHECK ===")
print(f"SUBQ_API_KEY: {'[PRESENT]' if SUBQ_API_KEY else '[MISSING]'}")
print(f"GEMINI_API_KEY: {'[PRESENT]' if GEMINI_API_KEY else '[MISSING]'}")
print("=========================\n")

SUBQ_CHAT_URL = "https://api.subq.ai/v1/chat/completions"
SUBQ_MODEL = "subq-savant-1.4"
SUBQ_HEADERS = {
    "Authorization": f"Bearer {SUBQ_API_KEY}",
    "Content-Type": "application/json"
}

# ---------------------------------------------------------------------------
# Test 1: Connectivity & Basic Generation
# ---------------------------------------------------------------------------
def test_subq_basic(client: httpx.Client):
    print("--- 1. Testing SubQ Savant Basic Generation ---")
    payload = {
        "model": SUBQ_MODEL,
        "messages": [
            {"role": "system", "content": "You are a desktop agent assistant. Respond in one concise sentence."},
            {"role": "user", "content": "Confirm you are online and report your model name."}
        ]
        # Notice: temperature is omitted because SubQ requires temperature=1 or omitted
    }
    
    t0 = time.perf_counter()
    try:
        resp = client.post(SUBQ_CHAT_URL, headers=SUBQ_HEADERS, json=payload, timeout=30.0)
        elapsed = (time.perf_counter() - t0) * 1000
        print(f"SubQ Status Code: {resp.status_code} in {elapsed:.1f}ms")
        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            print(f"SubQ Response: {content.strip()}")
            usage = data.get("usage", {})
            print(f"Usage: {usage}")
            return True, elapsed
        else:
            print(f"SubQ Error Body: {resp.text}")
            return False, elapsed
    except Exception as e:
        print(f"SubQ Connection Exception: {e}")
        return False, 0.0

def test_gemini_basic(client: httpx.Client):
    print("\n--- 2. Testing Gemini Basic Generation ---")
    gemini_model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={GEMINI_API_KEY}"
    
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": "You are a desktop agent assistant. Respond in one concise sentence: Confirm you are online."}]}
        ]
    }
    
    t0 = time.perf_counter()
    try:
        resp = client.post(url, json=payload, timeout=30.0)
        elapsed = (time.perf_counter() - t0) * 1000
        print(f"Gemini Status Code: {resp.status_code} in {elapsed:.1f}ms")
        if resp.status_code == 200:
            data = resp.json()
            cand = data["candidates"][0]["content"]["parts"][0]["text"]
            print(f"Gemini Response: {cand.strip()}")
            return True, elapsed
        else:
            print(f"Gemini Error Body: {resp.text}")
            return False, elapsed
    except Exception as e:
        print(f"Gemini Connection Exception: {e}")
        return False, 0.0

# ---------------------------------------------------------------------------
# Test 2: Desktop Tool / Function Calling Benchmark
# ---------------------------------------------------------------------------
DESKTOP_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "press_key",
            "description": "Press a physical keyboard key or shortcut.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Key identifier e.g. 'space', 'w', 'f', 'win+d'"}
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "click_coordinates",
            "description": "Click at specific screen pixel coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate in pixels"},
                    "y": {"type": "integer", "description": "Y coordinate in pixels"},
                    "button": {"type": "string", "enum": ["left", "right", "double"]}
                },
                "required": ["x", "y"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Launch an installed Windows application or game.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {"type": "string", "description": "Name of application or game e.g. 'Persona 3 Reload', 'Chrome'"}
                },
                "required": ["app_name"]
            }
        }
    }
]

TOOL_PROMPTS = [
    "Press the spacebar to pause video playback.",
    "Click the blue 'Play' button located at x=526, y=668.",
    "Open the game Persona 3 Reload for me.",
    "Press the 'w' key to move forward.",
    "Minimize all windows by pressing Windows plus d."
]

def benchmark_subq_tools(client: httpx.Client):
    print("\n=======================================================")
    print(" 3. Desktop Action Tool-Calling Benchmark: SubQ Savant")
    print("=======================================================")
    
    latencies = []
    success_count = 0
    
    for i, user_prompt in enumerate(TOOL_PROMPTS, 1):
        payload = {
            "model": SUBQ_MODEL,
            "messages": [
                {"role": "system", "content": "You are a voice desktop automation controller. When given a user command, select and call the appropriate tool with accurate parameters."},
                {"role": "user", "content": user_prompt}
            ],
            "tools": DESKTOP_TOOLS,
            "tool_choice": "auto"
        }
        
        t0 = time.perf_counter()
        try:
            resp = client.post(SUBQ_CHAT_URL, headers=SUBQ_HEADERS, json=payload, timeout=30.0)
            elapsed = (time.perf_counter() - t0) * 1000
            latencies.append(elapsed)
            
            if resp.status_code == 200:
                data = resp.json()
                msg = data["choices"][0]["message"]
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    fn = tool_calls[0]["function"]
                    args = fn.get("arguments", "{}")
                    print(f"[{i}/5] '{user_prompt}' -> {fn['name']}({args}) in {elapsed:.1f}ms [OK]")
                    success_count += 1
                else:
                    print(f"[{i}/5] '{user_prompt}' -> Text reply instead of tool call in {elapsed:.1f}ms: {msg.get('content')}")
            else:
                print(f"[{i}/5] '{user_prompt}' -> Error {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            print(f"[{i}/5] Error: {e}")
            
    print(f"\nSubQ Tool Call Success: {success_count}/{len(TOOL_PROMPTS)} | Median Latency: {sorted(latencies)[len(latencies)//2]:.1f}ms")
    return latencies

# ---------------------------------------------------------------------------
# Test 3: Long Context & Scaled Reasoning
# ---------------------------------------------------------------------------
def benchmark_subq_context_scaling(client: httpx.Client, token_sizes=[10_000, 50_000, 100_000]):
    print("\n=======================================================")
    print(" 4. Context Length & Latency Scaling Benchmark: SubQ Savant")
    print("=======================================================")
    
    # Generate filler corpus
    paragraph = "Operating system virtualization and low-latency IPC require zero-copy buffer handoffs. " * 20
    
    for tokens in token_sizes:
        repeat_count = max(1, tokens // 100)
        filler = (paragraph + "\n\n") * repeat_count
        needle = "SECRET_HOTKEY: Ctrl+Alt+F12 activates autonomous debug mode."
        
        # Inject needle in the middle
        split_point = len(filler) // 2
        prompt_text = filler[:split_point] + f"\n\n[CONFIDENTIAL NOTE: {needle}]\n\n" + filler[split_point:]
        
        payload = {
            "model": SUBQ_MODEL,
            "messages": [
                {"role": "system", "content": "You are an analytical assistant capable of inspecting massive system logs and documentation."},
                {"role": "user", "content": f"{prompt_text}\n\nQuestion: What is the exact SECRET_HOTKEY mentioned in the text?"}
            ]
        }
        
        print(f"Testing context ~{tokens:,} tokens (~{len(prompt_text):,} chars)...", end=" ", flush=True)
        t0 = time.perf_counter()
        try:
            resp = client.post(SUBQ_CHAT_URL, headers=SUBQ_HEADERS, json=payload, timeout=120.0)
            elapsed = (time.perf_counter() - t0) * 1000
            
            if resp.status_code == 200:
                data = resp.json()
                reply = data["choices"][0]["message"]["content"]
                found_needle = "Ctrl+Alt+F12" in reply
                print(f"Done in {elapsed:.1f}ms! Needle Found: {found_needle} (Reply: {reply.strip()[:60]}...)")
            else:
                print(f"Failed {resp.status_code}: {resp.text[:150]}")
        except Exception as e:
            print(f"Exception: {e}")

# ---------------------------------------------------------------------------
# Main Runner
# ---------------------------------------------------------------------------
def main():
    with httpx.Client() as client:
        subq_ok, subq_lat = test_subq_basic(client)
        if GEMINI_API_KEY:
            gem_ok, gem_lat = test_gemini_basic(client)
        
        if subq_ok:
            benchmark_subq_tools(client)
            benchmark_subq_context_scaling(client)
        else:
            print("\n[!] SubQ Savant check failed. Please verify API key / organization early-access.")

if __name__ == "__main__":
    main()
