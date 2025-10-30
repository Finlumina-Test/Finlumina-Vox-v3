import asyncio
import json
import base64
import websockets
from typing import Optional, Callable
from config import Config
from services.log_utils import Log


class ElevenLabsStreamingService:
    """
    Real-time ElevenLabs voice synthesis using WebSocket API.
    Optimized for low-latency phone conversations with Pakistani accent support.
    """
    
    def __init__(self):
        self.voice_id = Config.ELEVENLABS_VOICE_ID
        self.api_key = Config.ELEVENLABS_API_KEY
        self.model_id = getattr(Config, 'ELEVENLABS_MODEL_ID', 'eleven_turbo_v2_5')
        
        # WebSocket URL with query parameters
        self.ws_url = (
            f"wss://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream-input"
            f"?model_id={self.model_id}"
            f"&output_format=pcm_16000"  # 16kHz PCM for better compatibility
        )
        
        self.ws_connection: Optional[websockets.WebSocketClientProtocol] = None
        self.is_connected = False
        self._lock = asyncio.Lock()
        
    async def connect(self):
        """Establish WebSocket connection to ElevenLabs."""
        async with self._lock:
            if self.is_connected:
                Log.info("[ElevenLabs] Already connected, skipping reconnection")
                return
                
            try:
                Log.info("[ElevenLabs] ========================================")
                Log.info("[ElevenLabs] Starting connection process...")
                Log.info(f"[ElevenLabs] Voice ID: {self.voice_id}")
                Log.info(f"[ElevenLabs] Model ID: {self.model_id}")
                Log.info(f"[ElevenLabs] API Key: {self.api_key[:20]}..." if self.api_key else "[ElevenLabs] API Key: NOT SET ❌")
                Log.info(f"[ElevenLabs] WebSocket URL: {self.ws_url}")
                
                if not self.api_key:
                    Log.error("[ElevenLabs] ❌ CRITICAL: API key is missing!")
                    Log.error("[ElevenLabs] Set ELEVENLABS_API_KEY in your .env file")
                    self.is_connected = False
                    self.ws_connection = None
                    return
                
                if not self.voice_id:
                    Log.error("[ElevenLabs] ❌ CRITICAL: Voice ID is missing!")
                    Log.error("[ElevenLabs] Set ELEVENLABS_VOICE_ID in your .env file")
                    self.is_connected = False
                    self.ws_connection = None
                    return
                
                Log.info("[ElevenLabs] Attempting WebSocket connection...")
                
                self.ws_connection = await websockets.connect(
                    self.ws_url,
                    additional_headers={
                        "xi-api-key": self.api_key
                    },
                    ping_interval=20,
                    ping_timeout=10
                )
                
                self.is_connected = True
                Log.info("[ElevenLabs] ✅ WebSocket connection established")
                
                # Send initial configuration for optimal streaming
                config_message = {
                    "text": " ",  # Required initial text
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.8,
                        "style": 0.0,
                        "use_speaker_boost": True
                    },
                    "generation_config": {
                        "chunk_length_schedule": [120, 160, 250, 290]  # Optimized chunks
                    }
                }
                
                Log.info("[ElevenLabs] Sending initial configuration...")
                await self.ws_connection.send(json.dumps(config_message))
                Log.info("[ElevenLabs] ✅ Initial config sent successfully")
                Log.info("[ElevenLabs] ========================================")
                
            except websockets.exceptions.InvalidStatusCode as e:
                Log.error("[ElevenLabs] ❌ CRITICAL: WebSocket connection rejected!")
                Log.error(f"[ElevenLabs] HTTP Status Code: {e.status_code}")
                
                if e.status_code == 401:
                    Log.error("[ElevenLabs] 🔑 AUTHENTICATION FAILED")
                    Log.error("[ElevenLabs] Possible causes:")
                    Log.error("[ElevenLabs]   1. Invalid API key")
                    Log.error("[ElevenLabs]   2. API key expired")
                    Log.error("[ElevenLabs]   3. API key revoked")
                    Log.error("[ElevenLabs] Solution: Get new API key from https://elevenlabs.io/app/settings/api-keys")
                    
                elif e.status_code == 404:
                    Log.error("[ElevenLabs] 🎤 VOICE NOT FOUND")
                    Log.error(f"[ElevenLabs] Voice ID '{self.voice_id}' does not exist or you don't have access")
                    Log.error("[ElevenLabs] Possible causes:")
                    Log.error("[ElevenLabs]   1. Wrong voice ID")
                    Log.error("[ElevenLabs]   2. Voice deleted")
                    Log.error("[ElevenLabs]   3. Premium voice on free tier")
                    Log.error("[ElevenLabs] Solution: Try default voice ID: 21m00Tcm4TlvDq8ikWAM (Rachel)")
                    
                elif e.status_code == 429:
                    Log.error("[ElevenLabs] 🚦 RATE LIMIT EXCEEDED")
                    Log.error("[ElevenLabs] You've made too many requests")
                    Log.error("[ElevenLabs] Possible causes:")
                    Log.error("[ElevenLabs]   1. Exceeded API quota")
                    Log.error("[ElevenLabs]   2. Too many concurrent requests")
                    Log.error("[ElevenLabs]   3. Free tier limits reached")
                    Log.error("[ElevenLabs] Solution: Wait and retry, or upgrade plan")
                    
                elif e.status_code == 403:
                    Log.error("[ElevenLabs] 🚫 ACCESS FORBIDDEN")
                    Log.error("[ElevenLabs] You don't have permission to use this resource")
                    Log.error("[ElevenLabs] Possible causes:")
                    Log.error("[ElevenLabs]   1. Account suspended")
                    Log.error("[ElevenLabs]   2. Payment method issue")
                    Log.error("[ElevenLabs]   3. Terms of service violation")
                    Log.error("[ElevenLabs] Solution: Check account status at https://elevenlabs.io/app/usage")
                    
                elif e.status_code == 500:
                    Log.error("[ElevenLabs] 💥 SERVER ERROR")
                    Log.error("[ElevenLabs] ElevenLabs API is experiencing issues")
                    Log.error("[ElevenLabs] Solution: Wait and retry, or check status page")
                    
                else:
                    Log.error(f"[ElevenLabs] Unknown HTTP error: {e.status_code}")
                    Log.error(f"[ElevenLabs] Full error: {e}")
                
                self.is_connected = False
                self.ws_connection = None
                
            except websockets.exceptions.WebSocketException as e:
                Log.error("[ElevenLabs] ❌ WebSocket error during connection")
                Log.error(f"[ElevenLabs] Error type: {type(e).__name__}")
                Log.error(f"[ElevenLabs] Error message: {str(e)}")
                self.is_connected = False
                self.ws_connection = None
                
            except asyncio.TimeoutError:
                Log.error("[ElevenLabs] ❌ CONNECTION TIMEOUT")
                Log.error("[ElevenLabs] Could not connect to ElevenLabs API within timeout period")
                Log.error("[ElevenLabs] Possible causes:")
                Log.error("[ElevenLabs]   1. Network connectivity issues")
                Log.error("[ElevenLabs]   2. Firewall blocking connection")
                Log.error("[ElevenLabs]   3. ElevenLabs API is down")
                Log.error("[ElevenLabs] Solution: Check network and retry")
                self.is_connected = False
                self.ws_connection = None
                
            except Exception as e:
                Log.error("[ElevenLabs] ❌ UNEXPECTED ERROR during connection")
                Log.error(f"[ElevenLabs] Error type: {type(e).__name__}")
                Log.error(f"[ElevenLabs] Error message: {str(e)}")
                Log.error("[ElevenLabs] Full traceback:")
                import traceback
                Log.error(traceback.format_exc())
                self.is_connected = False
                self.ws_connection = None
    
    async def disconnect(self):
        """Close WebSocket connection."""
        async with self._lock:
            if self.ws_connection:
                try:
                    await self.ws_connection.close()
                    Log.info("[ElevenLabs] Disconnected")
                except Exception as e:
                    Log.error(f"[ElevenLabs] Disconnect error: {e}")
            self.is_connected = False
            self.ws_connection = None
    
    async def ensure_connected(self):
        """Ensure connection is active, reconnect if needed."""
        if not self.is_connected:
            await self.connect()
    
    def convert_pcm_to_ulaw(self, pcm_data: bytes) -> bytes:
        """
        Convert 16-bit PCM to 8-bit μ-law (required by Twilio).
        
        This is necessary because ElevenLabs outputs PCM but Twilio expects μ-law.
        """
        try:
            import audioop
            # Convert 16-bit PCM to 8-bit μ-law
            ulaw_data = audioop.lin2ulaw(pcm_data, 2)  # 2 = 16-bit width
            return ulaw_data
        except Exception as e:
            Log.error(f"[ElevenLabs] PCM->μ-law conversion failed: {e}")
            return pcm_data
    
    async def stream_text_to_speech(
        self, 
        text: str, 
        audio_callback: Callable[[bytes], None],
        connection_manager = None
    ):
        """
        Stream text to ElevenLabs and receive audio chunks in real-time.
        
        Args:
            text: Text to convert to speech
            audio_callback: Async function called with each audio chunk
            connection_manager: Optional connection manager for Twilio streaming
        """
        await self.ensure_connected()
        
        if not self.is_connected or not self.ws_connection:
            Log.error("[ElevenLabs] ❌ Cannot stream - not connected")
            Log.error("[ElevenLabs] Connection status:")
            Log.error(f"[ElevenLabs]   is_connected: {self.is_connected}")
            Log.error(f"[ElevenLabs]   ws_connection: {self.ws_connection is not None}")
            return
        
        try:
            Log.info("[ElevenLabs] ========================================")
            Log.info(f"[ElevenLabs] 🎙️ Starting TTS generation")
            Log.info(f"[ElevenLabs] Text length: {len(text)} characters")
            Log.info(f"[ElevenLabs] Text preview: '{text[:80]}...'")
            
            # Send text to ElevenLabs
            text_message = {
                "text": text,
                "try_trigger_generation": True,
                "flush": True  # Force immediate generation
            }
            
            Log.info("[ElevenLabs] Sending text to API...")
            try:
                await self.ws_connection.send(json.dumps(text_message))
                Log.info("[ElevenLabs] ✅ Text sent successfully")
            except Exception as e:
                Log.error(f"[ElevenLabs] ❌ Failed to send text: {e}")
                raise
            
            # Send EOS (End of Stream) marker to signal completion
            Log.info("[ElevenLabs] Sending EOS marker...")
            eos_message = {"text": ""}
            try:
                await self.ws_connection.send(json.dumps(eos_message))
                Log.info("[ElevenLabs] ✅ EOS marker sent")
            except Exception as e:
                Log.error(f"[ElevenLabs] ❌ Failed to send EOS: {e}")
                raise
            
            chunk_count = 0
            total_bytes = 0
            start_time = asyncio.get_event_loop().time()
            
            Log.info("[ElevenLabs] Waiting for audio response...")
            
            # Receive and process audio chunks
            while True:
                try:
                    response = await asyncio.wait_for(
                        self.ws_connection.recv(), 
                        timeout=10.0
                    )
                    
                    try:
                        data = json.loads(response)
                    except json.JSONDecodeError as e:
                        Log.error(f"[ElevenLabs] ❌ Invalid JSON response: {e}")
                        Log.error(f"[ElevenLabs] Raw response: {response[:200]}")
                        continue
                    
                    # Check for audio data
                    if data.get("audio"):
                        chunk_count += 1
                        
                        # Decode base64 audio chunk (PCM format from ElevenLabs)
                        try:
                            audio_chunk_pcm = base64.b64decode(data["audio"])
                            total_bytes += len(audio_chunk_pcm)
                            
                            # Convert PCM to μ-law for Twilio
                            audio_chunk_ulaw = self.convert_pcm_to_ulaw(audio_chunk_pcm)
                            
                            # Send to callback (will forward to Twilio)
                            await audio_callback(audio_chunk_ulaw)
                            
                            if chunk_count == 1:
                                elapsed = asyncio.get_event_loop().time() - start_time
                                Log.info(f"[ElevenLabs] ✅ First audio chunk received after {elapsed:.2f}s")
                            
                            Log.debug(f"[ElevenLabs] 📦 Chunk {chunk_count}: {len(audio_chunk_ulaw)} bytes")
                            
                        except Exception as e:
                            Log.error(f"[ElevenLabs] ❌ Failed to process audio chunk {chunk_count}: {e}")
                            continue
                    
                    # Check for errors
                    if data.get("error"):
                        error_msg = data.get("error")
                        Log.error(f"[ElevenLabs] ❌ API ERROR: {error_msg}")
                        
                        # Detailed error analysis
                        if "detected_unusual_activity" in str(error_msg).lower():
                            Log.error("[ElevenLabs] 🚨 UNUSUAL ACTIVITY DETECTED")
                            Log.error("[ElevenLabs] Your account has been flagged by ElevenLabs")
                            Log.error("[ElevenLabs] Common causes:")
                            Log.error("[ElevenLabs]   1. Free tier quota exhausted")
                            Log.error("[ElevenLabs]   2. Too many requests in short time")
                            Log.error("[ElevenLabs]   3. Account verification needed")
                            Log.error("[ElevenLabs]   4. Payment method issue")
                            Log.error("[ElevenLabs]   5. Suspicious usage pattern detected")
                            Log.error("[ElevenLabs] Solutions:")
                            Log.error("[ElevenLabs]   1. Check usage at https://elevenlabs.io/app/usage")
                            Log.error("[ElevenLabs]   2. Verify your email address")
                            Log.error("[ElevenLabs]   3. Add payment method")
                            Log.error("[ElevenLabs]   4. Wait 24 hours and try again")
                            Log.error("[ElevenLabs]   5. Contact support@elevenlabs.io")
                            
                        elif "quota" in str(error_msg).lower():
                            Log.error("[ElevenLabs] 📊 QUOTA EXCEEDED")
                            Log.error("[ElevenLabs] You've used up your character quota")
                            Log.error("[ElevenLabs] Solution: Wait for quota reset or upgrade plan")
                            
                        elif "invalid" in str(error_msg).lower():
                            Log.error("[ElevenLabs] ❌ INVALID REQUEST")
                            Log.error("[ElevenLabs] The request parameters are incorrect")
                            Log.error(f"[ElevenLabs] Voice ID: {self.voice_id}")
                            Log.error(f"[ElevenLabs] Model ID: {self.model_id}")
                            
                        else:
                            Log.error(f"[ElevenLabs] Unknown API error: {error_msg}")
                            Log.error(f"[ElevenLabs] Full response: {data}")
                        
                        break
                    
                    # Check if generation is complete
                    if data.get("isFinal"):
                        elapsed = asyncio.get_event_loop().time() - start_time
                        Log.info("[ElevenLabs] ✅ Generation complete!")
                        Log.info(f"[ElevenLabs] Total chunks: {chunk_count}")
                        Log.info(f"[ElevenLabs] Total bytes: {total_bytes:,}")
                        Log.info(f"[ElevenLabs] Generation time: {elapsed:.2f}s")
                        Log.info(f"[ElevenLabs] Avg chunk size: {total_bytes // chunk_count if chunk_count > 0 else 0} bytes")
                        Log.info("[ElevenLabs] ========================================")
                        break
                        
                except asyncio.TimeoutError:
                    Log.error("[ElevenLabs] ❌ TIMEOUT waiting for audio response")
                    Log.error(f"[ElevenLabs] Received {chunk_count} chunks before timeout")
                    Log.error("[ElevenLabs] Possible causes:")
                    Log.error("[ElevenLabs]   1. ElevenLabs API is slow/overloaded")
                    Log.error("[ElevenLabs]   2. Network latency issues")
                    Log.error("[ElevenLabs]   3. Text too long for processing")
                    Log.error("[ElevenLabs] Solution: Retry with shorter text")
                    break
                    
                except json.JSONDecodeError as e:
                    Log.error(f"[ElevenLabs] ❌ Invalid JSON response: {e}")
                    break
                    
        except websockets.exceptions.ConnectionClosed as e:
            Log.error("[ElevenLabs] ❌ Connection closed unexpectedly")
            Log.error(f"[ElevenLabs] Close code: {e.code if hasattr(e, 'code') else 'N/A'}")
            Log.error(f"[ElevenLabs] Close reason: {e.reason if hasattr(e, 'reason') else 'N/A'}")
            Log.error("[ElevenLabs] Possible causes:")
            Log.error("[ElevenLabs]   1. API key revoked mid-request")
            Log.error("[ElevenLabs]   2. Account quota exhausted")
            Log.error("[ElevenLabs]   3. Network interruption")
            Log.error("[ElevenLabs]   4. ElevenLabs server issue")
            self.is_connected = False
            
        except Exception as e:
            Log.error(f"[ElevenLabs] ❌ UNEXPECTED ERROR during streaming")
            Log.error(f"[ElevenLabs] Error type: {type(e).__name__}")
            Log.error(f"[ElevenLabs] Error message: {str(e)}")
            Log.error("[ElevenLabs] Full traceback:")
            import traceback
            Log.error(traceback.format_exc())
            self.is_connected = False
    
    async def send_to_twilio_realtime(
        self, 
        text: str, 
        connection_manager
    ):
        """
        Generate speech and stream directly to Twilio in real-time.
        
        This minimizes latency by forwarding each audio chunk immediately.
        
        Args:
            text: Text to convert to speech  
            connection_manager: WebSocket connection manager for Twilio
        """
        Log.info("[ElevenLabs→Twilio] ========================================")
        Log.info(f"[ElevenLabs→Twilio] Starting real-time audio streaming")
        
        # Verify stream_sid exists
        stream_sid = getattr(connection_manager.state, 'stream_sid', None)
        if not stream_sid:
            Log.error("[ElevenLabs→Twilio] ❌ CRITICAL: No stream_sid available")
            Log.error("[ElevenLabs→Twilio] Cannot send audio to Twilio without stream_sid")
            Log.error("[ElevenLabs→Twilio] Possible causes:")
            Log.error("[ElevenLabs→Twilio]   1. Twilio connection not established")
            Log.error("[ElevenLabs→Twilio]   2. Connection state not initialized")
            Log.error("[ElevenLabs→Twilio]   3. Stream was closed prematurely")
            return False
        
        Log.info(f"[ElevenLabs→Twilio] Twilio stream_sid: {stream_sid}")
        Log.info(f"[ElevenLabs→Twilio] Text to synthesize: '{text[:80]}...'")
        
        chunk_counter = 0
        total_audio_bytes = 0
        start_time = asyncio.get_event_loop().time()
        
        async def send_chunk_to_twilio(audio_chunk: bytes):
            """Send individual audio chunk to Twilio."""
            nonlocal chunk_counter
            nonlocal total_audio_bytes
            
            try:
                # Encode audio chunk to base64
                audio_base64 = base64.b64encode(audio_chunk).decode('utf-8')
                total_audio_bytes += len(audio_chunk)
                
                # Create Twilio media message
                twilio_message = {
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {
                        "payload": audio_base64
                    }
                }
                
                # Send to Twilio
                await connection_manager.send_to_twilio(twilio_message)
                
                chunk_counter += 1
                
                if chunk_counter == 1:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    Log.info(f"[ElevenLabs→Twilio] ✅ First chunk sent after {elapsed:.2f}s")
                
                Log.debug(f"[ElevenLabs→Twilio] Chunk {chunk_counter}: {len(audio_chunk)} bytes sent")
                
            except Exception as e:
                Log.error(f"[ElevenLabs→Twilio] ❌ Failed to send chunk {chunk_counter + 1}")
                Log.error(f"[ElevenLabs→Twilio] Error: {e}")
                Log.error("[ElevenLabs→Twilio] Possible causes:")
                Log.error("[ElevenLabs→Twilio]   1. Twilio WebSocket disconnected")
                Log.error("[ElevenLabs→Twilio]   2. Network issue")
                Log.error("[ElevenLabs→Twilio]   3. Call ended abruptly")
                import traceback
                Log.error(traceback.format_exc())
        
        # Stream text and forward each chunk to Twilio
        Log.info("[ElevenLabs→Twilio] Requesting audio from ElevenLabs...")
        await self.stream_text_to_speech(text, send_chunk_to_twilio, connection_manager)
        
        elapsed = asyncio.get_event_loop().time() - start_time
        
        # Send mark for synchronization
        try:
            mark_name = f"elevenlabs_complete_{int(asyncio.get_event_loop().time())}"
            mark_message = {
                "event": "mark",
                "streamSid": stream_sid,
                "mark": {"name": mark_name}
            }
            await connection_manager.send_to_twilio(mark_message)
            Log.debug(f"[ElevenLabs→Twilio] Mark sent: {mark_name}")
        except Exception as e:
            Log.error(f"[ElevenLabs→Twilio] Failed to send mark: {e}")
        
        if chunk_counter > 0:
            Log.info(f"[ElevenLabs→Twilio] ✅ Streaming complete!")
            Log.info(f"[ElevenLabs→Twilio] Total chunks sent: {chunk_counter}")
            Log.info(f"[ElevenLabs→Twilio] Total audio bytes: {total_audio_bytes:,}")
            Log.info(f"[ElevenLabs→Twilio] Total time: {elapsed:.2f}s")
            Log.info(f"[ElevenLabs→Twilio] Avg throughput: {total_audio_bytes / elapsed if elapsed > 0 else 0:.0f} bytes/sec")
        else:
            Log.error("[ElevenLabs→Twilio] ❌ NO AUDIO CHUNKS WERE SENT")
            Log.error("[ElevenLabs→Twilio] This means audio generation failed completely")
            Log.error("[ElevenLabs→Twilio] Check ElevenLabs errors above for root cause")
        
        Log.info("[ElevenLabs→Twilio] ========================================")
        
        return chunk_counter > 0


class ElevenLabsTextBuffer:
    """
    Buffers text from OpenAI and sends complete sentences to ElevenLabs.
    
    This prevents choppy audio by ensuring we send natural sentence breaks
    rather than arbitrary text chunks.
    """
    
    def __init__(self, streaming_service: ElevenLabsStreamingService):
        self.streaming_service = streaming_service
        self.text_buffer = ""
        
        # Sentence endings for English, Urdu, and Hindi
        self.sentence_endings = ['.', '!', '?', '।', '۔']  
        
        self._processing = False
        self._queue = asyncio.Queue()
        
    async def add_text_delta(self, text_delta: str, connection_manager):
        """
        Add incremental text from OpenAI.
        
        Buffers until complete sentence, then streams to ElevenLabs.
        """
        if not text_delta:
            return
        
        self.text_buffer += text_delta
        
        # Check for complete sentence
        has_sentence_end = any(
            ending in self.text_buffer 
            for ending in self.sentence_endings
        )
        
        if has_sentence_end:
            # Find the last sentence ending position
            last_ending_pos = -1
            for ending in self.sentence_endings:
                pos = self.text_buffer.rfind(ending)
                if pos > last_ending_pos:
                    last_ending_pos = pos
            
            if last_ending_pos >= 0:
                # Extract complete sentence(s)
                text_to_send = self.text_buffer[:last_ending_pos + 1].strip()
                self.text_buffer = self.text_buffer[last_ending_pos + 1:].strip()
                
                if text_to_send:
                    # Send to ElevenLabs immediately
                    await self._send_to_elevenlabs(text_to_send, connection_manager)
    
    async def flush(self, connection_manager):
        """Force send any remaining buffered text."""
        if self.text_buffer.strip():
            text = self.text_buffer.strip()
            self.text_buffer = ""
            await self._send_to_elevenlabs(text, connection_manager)
    
    async def _send_to_elevenlabs(self, text: str, connection_manager):
        """Internal method to send text to ElevenLabs."""
        try:
            Log.info(f"[TextBuffer] 📤 Sending: '{text[:60]}...'")
            await self.streaming_service.send_to_twilio_realtime(
                text,
                connection_manager
            )
        except Exception as e:
            Log.error(f"[TextBuffer] Failed to send text: {e}")
    
    def clear(self):
        """Clear the text buffer."""
        self.text_buffer = ""


# Global service instances (initialized in server.py)
_elevenlabs_service: Optional[ElevenLabsStreamingService] = None
_text_buffer: Optional[ElevenLabsTextBuffer] = None


def get_elevenlabs_service() -> ElevenLabsStreamingService:
    """Get or create the global ElevenLabs service instance."""
    global _elevenlabs_service
    if _elevenlabs_service is None:
        _elevenlabs_service = ElevenLabsStreamingService()
    return _elevenlabs_service


def get_text_buffer() -> ElevenLabsTextBuffer:
    """Get or create the global text buffer instance."""
    global _text_buffer
    if _text_buffer is None:
        _text_buffer = ElevenLabsTextBuffer(get_elevenlabs_service())
    return _text_buffer
