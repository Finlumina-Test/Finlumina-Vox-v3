#!/usr/bin/env python3
"""
Test ElevenLabs API access and diagnose issues
"""
import os
import asyncio
import websockets
import json
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_turbo_v2_5")

print("=" * 60)
print("ELEVENLABS API TEST")
print("=" * 60)
print(f"API Key: {API_KEY[:20]}..." if API_KEY else "API Key: NOT SET ❌")
print(f"Voice ID: {VOICE_ID}")
print(f"Model ID: {MODEL_ID}")
print()

if not API_KEY or not VOICE_ID:
    print("❌ Missing credentials!")
    print("Set ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID in .env")
    exit(1)

async def test_connection():
    ws_url = (
        f"wss://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream-input"
        f"?model_id={MODEL_ID}"
        f"&output_format=pcm_16000"
    )
    
    print(f"Connecting to: {ws_url[:80]}...")
    print()
    
    try:
        async with websockets.connect(
            ws_url,
            additional_headers={"xi-api-key": API_KEY},
            ping_interval=20,
            ping_timeout=10
        ) as ws:
            print("✅ WebSocket connected!")
            print()
            
            # Send test message
            test_message = {
                "text": "Hello, this is a test.",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.8
                }
            }
            
            print("Sending test message...")
            await ws.send(json.dumps(test_message))
            
            # Send EOS
            await ws.send(json.dumps({"text": ""}))
            
            print("Waiting for response...")
            chunk_count = 0
            
            while True:
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(response)
                    
                    if data.get("audio"):
                        chunk_count += 1
                        print(f"✅ Received audio chunk {chunk_count}")
                    
                    if data.get("error"):
                        print(f"❌ API Error: {data['error']}")
                        return False
                    
                    if data.get("isFinal"):
                        print(f"\n✅ SUCCESS! Received {chunk_count} audio chunks")
                        return True
                        
                except asyncio.TimeoutError:
                    print("❌ Timeout waiting for response")
                    return False
                    
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"❌ Connection failed with status: {e.status_code}")
        if e.status_code == 401:
            print("   → Invalid API key")
        elif e.status_code == 404:
            print("   → Voice ID not found")
        elif e.status_code == 429:
            print("   → Rate limit exceeded")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_connection())
    
    print()
    print("=" * 60)
    if result:
        print("✅ ElevenLabs API is working correctly!")
        print("The issue is likely with your account settings or usage limits.")
    else:
        print("❌ ElevenLabs API test failed")
        print("\nTroubleshooting steps:")
        print("1. Check your API key at: https://elevenlabs.io/app/settings/api-keys")
        print("2. Verify your voice ID at: https://elevenlabs.io/app/voice-library")
        print("3. Check your quota at: https://elevenlabs.io/app/usage")
        print("4. Try using a default voice ID: 21m00Tcm4TlvDq8ikWAM")
    print("=" * 60)
