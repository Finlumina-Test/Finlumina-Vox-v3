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
                return
                
            try:
                Log.info("[ElevenLabs] Connecting to WebSocket...")
                
                self.ws_connection = await websockets.connect(
                    self.ws_url,
                    extra_headers={
                        "xi-api-key": self.api_key
                    },
                    ping_interval=20,
                    ping_timeout=10
                )
                
                self.is_connected = True
                Log.info("[ElevenLabs] ✅ WebSocket connected")
                
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
                
                await self.ws_connection.send(json.dumps(config_message))
                Log.debug("[ElevenLabs] Sent initial config")
                
            except Exception as e:
                Log.error(f"[ElevenLabs] Connection failed: {e}")
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
            Log.error("[ElevenLabs] Cannot stream - not connected")
            return
        
        try:
            # Send text to ElevenLabs
            text_message = {
                "text": text,
                "try_trigger_generation": True,
                "flush": True  # Force immediate generation
            }
            
            Log.info(f"[ElevenLabs] 🎙️ Generating: '{text[:60]}...'")
            await self.ws_connection.send(json.dumps(text_message))
            
            # Send EOS (End of Stream) marker to signal completion
            eos_message = {"text": ""}
            await self.ws_connection.send(json.dumps(eos_message))
            
            chunk_count = 0
            total_bytes = 0
            
            # Receive and process audio chunks
            while True:
                try:
                    response = await asyncio.wait_for(
                        self.ws_connection.recv(), 
                        timeout=10.0
                    )
                    
                    data = json.loads(response)
                    
                    # Check for audio data
                    if data.get("audio"):
                        chunk_count += 1
                        
                        # Decode base64 audio chunk (PCM format from ElevenLabs)
                        audio_chunk_pcm = base64.b64decode(data["audio"])
                        total_bytes += len(audio_chunk_pcm)
                        
                        # Convert PCM to μ-law for Twilio
                        audio_chunk_ulaw = self.convert_pcm_to_ulaw(audio_chunk_pcm)
                        
                        # Send to callback (will forward to Twilio)
                        await audio_callback(audio_chunk_ulaw)
                        
                        Log.debug(f"[ElevenLabs] 📦 Chunk {chunk_count}: {len(audio_chunk_ulaw)} bytes")
                    
                    # Check for errors
                    if data.get("error"):
                        Log.error(f"[ElevenLabs] API error: {data['error']}")
                        break
                    
                    # Check if generation is complete
                    if data.get("isFinal"):
                        Log.info(f"[ElevenLabs] ✅ Complete: {chunk_count} chunks, {total_bytes} bytes")
                        break
                        
                except asyncio.TimeoutError:
                    Log.error("[ElevenLabs] Timeout waiting for audio response")
                    break
                except json.JSONDecodeError as e:
                    Log.error(f"[ElevenLabs] Invalid JSON response: {e}")
                    break
                    
        except websockets.exceptions.ConnectionClosed:
            Log.error("[ElevenLabs] Connection closed unexpectedly")
            self.is_connected = False
        except Exception as e:
            Log.error(f"[ElevenLabs] Streaming error: {e}")
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
        stream_sid = getattr(connection_manager.state, 'stream_sid', None)
        if not stream_sid:
            Log.error("[ElevenLabs] No stream_sid available - cannot send to Twilio")
            return False
        
        chunk_counter = 0
        
        async def send_chunk_to_twilio(audio_chunk: bytes):
            """Send individual audio chunk to Twilio."""
            nonlocal chunk_counter
            
            try:
                # Encode audio chunk to base64
                audio_base64 = base64.b64encode(audio_chunk).decode('utf-8')
                
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
                Log.debug(f"[ElevenLabs→Twilio] Sent chunk {chunk_counter} ({len(audio_chunk)} bytes)")
                
            except Exception as e:
                Log.error(f"[ElevenLabs→Twilio] Failed to send chunk: {e}")
        
        # Stream text and forward each chunk to Twilio
        await self.stream_text_to_speech(text, send_chunk_to_twilio, connection_manager)
        
        # Send mark for synchronization
        try:
            mark_message = {
                "event": "mark",
                "streamSid": stream_sid,
                "mark": {"name": f"elevenlabs_complete_{int(asyncio.get_event_loop().time())}"}
            }
            await connection_manager.send_to_twilio(mark_message)
        except Exception as e:
            Log.error(f"[ElevenLabs] Failed to send mark: {e}")
        
        Log.info(f"[ElevenLabs] ✅ Streamed {chunk_counter} chunks to Twilio")
        return True


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
