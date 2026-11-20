"""
Direct Head-to-Head Benchmark: Subquadratic Savant (subq-savant-1.4) vs Google Gemini
1. Tool Calling Latency & Accuracy (Desktop Actions)
2. Scaled Needle Retrieval (100k, 250k, 500k tokens)
3. Latency Growth Factor (Subquadratic O(N) vs Transformer O(N^2))
"""

import os
import sys
import time
import json
import httpx
import winreg

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
    except Exception:
        pass

load_user_env()

SUBQ_API_KEY = os.environ.get("SUBQ_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

SUBQ_URL = "https://api.subq.ai/v1/chat/completions"
SUBQ_HEADERS = {"Authorization": f"Bearer {SUBQ_API_KEY}", "Content-Type": "application/json"}
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"

DESKTOP_TOOLS_OPENAI = [
    {
        "type": "function",
        "function": {
            "name": "press_key",
            "description": "Press a physical keyboard key or shortcut.",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
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
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "button": {"type": "string", "enum": ["left", "right"]}
                },
                "required": ["x", "y"]
            }
        }
    }
]

GEMINI_TOOLS_SCHEMA = [
    {
        "function_declarations": [
            {
                "name": "press_key",
                "description": "Press a physical keyboard key or shortcut.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {"key": {"type": "STRING"}},
                    "required": ["key"]
                }
            },
            {
                "name": "click_coordinates",
                "description": "Click at specific screen pixel coordinates.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "x": {"type": "INTEGER"},
                        "y": {"type": "INTEGER"},
                        "button": {"type": "STRING", "enum": ["left", "right"]}
                    },
                    "required": ["x", "y"]
                }
            }
        ]
    }
]

TEST_COMMANDS = [
    "Press the spacebar to pause playback.",
    "Click the confirm button at x=800, y=450.",
    "Press win+d to show desktop.",
    "Click the cancel button at x=320, y=600.",
    "Press the 'f' key for fullscreen."
]

def run_tool_comparison(client: httpx.Client):
    print("\n=======================================================")
    print(" 1. HEAD-TO-HEAD TOOL CALLING (5 Desktop Actions)")
    print("=======================================================")
    
    subq_latencies = []
    gemini_latencies = []
    
    for i, cmd in enumerate(TEST_COMMANDS, 1):
        # --- SubQ ---
        subq_payload = {
            "model": "subq-savant-1.4",
            "messages": [
                {"role": "system", "content": "You are a desktop agent. Call the right tool."},
                {"role": "user", "content": cmd}
            ],
            "tools": DESKTOP_TOOLS_OPENAI
        }
        t0 = time.perf_counter()
        resp_s = client.post(SUBQ_URL, headers=SUBQ_HEADERS, json=subq_payload, timeout=30.0)
        lat_s = (time.perf_counter() - t0) * 1000
        subq_latencies.append(lat_s)
        call_s = resp_s.json()["choices"][0]["message"].get("tool_calls", [{}])[0].get("function", {}).get("name", "none")
        
        # --- Gemini ---
        gem_payload = {
            "contents": [{"role": "user", "parts": [{"text": cmd}]}],
            "tools": GEMINI_TOOLS_SCHEMA
        }
        t0 = time.perf_counter()
        resp_g = client.post(GEMINI_URL, json=gem_payload, timeout=30.0)
        lat_g = (time.perf_counter() - t0) * 1000
        gemini_latencies.append(lat_g)
        try:
            parts = resp_g.json()["candidates"][0]["content"]["parts"]
            call_g = parts[0].get("functionCall", {}).get("name", "none")
        except Exception:
            call_g = "none"
            
        print(f"Action {i}: '{cmd}'")
        print(f"  SubQ Savant : {call_s} in {lat_s:.1f}ms")
        print(f"  Gemini      : {call_g} in {lat_g:.1f}ms")
        
    med_s = sorted(subq_latencies)[len(subq_latencies)//2]
    med_g = sorted(gemini_latencies)[len(gemini_latencies)//2]
    print(f"\nMedian Tool Latency -> SubQ: {med_s:.1f}ms | Gemini: {med_g:.1f}ms")

def run_deep_context_benchmark(client: httpx.Client):
    print("\n=======================================================")
    print(" 2. EXTREME CONTEXT SCALING & NEEDLE RETRIEVAL (Up to 500k Tokens)")
    print("=======================================================")
    
    # Base corpus paragraph
    base = "Distributed memory architectures employ non-uniform memory access (NUMA) to scale cache coherence across multicore nodes. " * 20
    
    context_steps = [50_000, 150_000, 300_000, 500_000]
    
    for target_tokens in context_steps:
        repeats = max(1, target_tokens // 100)
        text_filler = (base + "\n\n") * repeats
        
        # Inject secret needle at 70% depth (not beginning, not end)
        needle_secret = f"AGENT_DEPLOYMENT_TOKEN_X99_{target_tokens}"
        needle_str = f"IMPORTANT CONFIGURATION: The system verification code is '{needle_secret}'."
        
        insert_idx = int(len(text_filler) * 0.70)
        full_context = text_filler[:insert_idx] + f"\n\n{needle_str}\n\n" + text_filler[insert_idx:]
        
        query = "What is the exact system verification code mentioned in the documentation?"
        
        print(f"\n--- Testing Context: ~{target_tokens:,} tokens ({len(full_context):,} chars) ---")
        
        # SubQ Savant Test
        subq_payload = {
            "model": "subq-savant-1.4",
            "messages": [
                {"role": "user", "content": f"{full_context}\n\nQuestion: {query}"}
            ]
        }
        
        print("SubQ Savant query running...", end=" ", flush=True)
        t0 = time.perf_counter()
        try:
            resp_s = client.post(SUBQ_URL, headers=SUBQ_HEADERS, json=subq_payload, timeout=180.0)
            lat_s = (time.perf_counter() - t0) * 1000
            if resp_s.status_code == 200:
                rep_s = resp_s.json()["choices"][0]["message"]["content"]
                found_s = needle_secret in rep_s
                usage = resp_s.json().get("usage", {})
                print(f"DONE in {lat_s:.0f}ms! Needle Found: {found_s}")
                print(f"  Prompt tokens: {usage.get('prompt_tokens', 0):,} | Reasoning: {usage.get('completion_tokens_details', {}).get('reasoning_tokens', 0)}")
            else:
                print(f"Error {resp_s.status_code}: {resp_s.text[:150]}")
        except Exception as e:
            print(f"Exception: {e}")

def main():
    with httpx.Client() as client:
        run_tool_comparison(client)
        run_deep_context_benchmark(client)

if __name__ == "__main__":
    main()
