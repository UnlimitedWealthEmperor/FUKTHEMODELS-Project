"""
ElevenLabs TTS Service
Core integration with ElevenLabs API for text-to-speech

Features:
- Single speaker TTS
- Multi-speaker dialogue
- Voice listing and management
- Model selection
- Integration with enhancement service
"""

import os
import json
import httpx
from typing import Optional, Dict, List, Any, BinaryIO
from dataclasses import dataclass, field
from enum import Enum
import asyncio


# ============================================================================
# Configuration
# ============================================================================

ELEVENLABS_BASE_URL = "https://api.elevenlabs.io"
DEFAULT_MODEL = "eleven_v3"
DEFAULT_STABILITY = 0.5
DEFAULT_SIMILARITY_BOOST = 0.75


class OutputFormat(Enum):
    MP3_44100_128 = "mp3_44100_128"
    MP3_44100_192 = "mp3_44100_192"
    PCM_16000 = "pcm_16000"
    PCM_22050 = "pcm_22050"
    PCM_24000 = "pcm_24000"
    PCM_44100 = "pcm_44100"
    ULAW_8000 = "ulaw_8000"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class Voice:
    """Represents an ElevenLabs voice"""
    voice_id: str
    name: str
    category: str = ""
    description: str = ""
    preview_url: str = ""
    labels: Dict[str, str] = field(default_factory=dict)
    settings: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class TTSRequest:
    """Request for text-to-speech"""
    text: str
    voice_id: str
    model_id: str = DEFAULT_MODEL
    stability: float = DEFAULT_STABILITY
    similarity_boost: float = DEFAULT_SIMILARITY_BOOST
    style: float = 0.0
    use_speaker_boost: bool = True
    output_format: OutputFormat = OutputFormat.MP3_44100_128


@dataclass
class DialogueLine:
    """Single line in a dialogue"""
    text: str
    voice_id: str


@dataclass
class DialogueRequest:
    """Request for multi-speaker dialogue"""
    lines: List[DialogueLine]
    model_id: str = DEFAULT_MODEL
    stability: float = DEFAULT_STABILITY
    similarity_boost: float = DEFAULT_SIMILARITY_BOOST
    output_format: OutputFormat = OutputFormat.MP3_44100_128


@dataclass
class TTSResponse:
    """Response from TTS request"""
    audio_data: bytes
    character_count: int
    content_type: str
    request_id: Optional[str] = None


# ============================================================================
# Main Service
# ============================================================================

class ElevenLabsService:
    """
    Service for interacting with ElevenLabs API
    """
    
    def __init__(self, api_key: str = None):
        """
        Initialize the ElevenLabs service
        
        Args:
            api_key: ElevenLabs API key. If not provided, reads from ELEVENLABS_API_KEY env var
        """
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        if not self.api_key:
            raise ValueError(
                "API key required. Set ELEVENLABS_API_KEY environment variable "
                "or pass api_key parameter"
            )
        
        self.base_url = ELEVENLABS_BASE_URL
        self._client = None
        self._async_client = None
        
        # Cache for voices and models
        self._voices_cache: Optional[List[Voice]] = None
        self._models_cache: Optional[List[Dict]] = None
    
    @property
    def headers(self) -> Dict[str, str]:
        """Request headers with authentication"""
        return {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json"
        }
    
    @property
    def client(self) -> httpx.Client:
        """Synchronous HTTP client"""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                headers=self.headers,
                timeout=60.0
            )
        return self._client
    
    @property
    def async_client(self) -> httpx.AsyncClient:
        """Asynchronous HTTP client"""
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self.headers,
                timeout=60.0
            )
        return self._async_client
    
    def close(self):
        """Close HTTP clients"""
        if self._client:
            self._client.close()
            self._client = None
        if self._async_client:
            asyncio.get_event_loop().run_until_complete(
                self._async_client.aclose()
            )
            self._async_client = None
    
    # ========================================================================
    # Voice Management
    # ========================================================================
    
    def get_voices(self, refresh: bool = False) -> List[Voice]:
        """
        Get list of available voices
        
        Args:
            refresh: Force refresh the cache
            
        Returns:
            List of Voice objects
        """
        if not refresh and self._voices_cache:
            return self._voices_cache
        
        response = self.client.get("/v2/voices")
        response.raise_for_status()
        
        data = response.json()
        voices = []
        
        for v in data.get("voices", []):
            voice = Voice(
                voice_id=v.get("voice_id", ""),
                name=v.get("name", ""),
                category=v.get("category", ""),
                description=v.get("description", ""),
                preview_url=v.get("preview_url", ""),
                labels=v.get("labels", {}),
                settings=v.get("settings", {})
            )
            voices.append(voice)
        
        self._voices_cache = voices
        return voices
    
    def get_voice(self, voice_id: str) -> Optional[Voice]:
        """Get a specific voice by ID"""
        voices = self.get_voices()
        for voice in voices:
            if voice.voice_id == voice_id:
                return voice
        return None
    
    def search_voices(self, query: str) -> List[Voice]:
        """Search voices by name or description"""
        voices = self.get_voices()
        query_lower = query.lower()
        
        results = []
        for voice in voices:
            if (query_lower in voice.name.lower() or 
                query_lower in voice.description.lower() or
                any(query_lower in v.lower() for v in voice.labels.values())):
                results.append(voice)
        
        return results
    
    # ========================================================================
    # Model Management
    # ========================================================================
    
    def get_models(self, refresh: bool = False) -> List[Dict]:
        """
        Get list of available models
        
        Returns:
            List of model information dictionaries
        """
        if not refresh and self._models_cache:
            return self._models_cache
        
        response = self.client.get("/v1/models")
        response.raise_for_status()
        
        self._models_cache = response.json()
        return self._models_cache
    
    def get_model(self, model_id: str) -> Optional[Dict]:
        """Get a specific model by ID"""
        models = self.get_models()
        for model in models:
            if model.get("model_id") == model_id:
                return model
        return None
    
    # ========================================================================
    # Text-to-Speech
    # ========================================================================
    
    def text_to_speech(self, request: TTSRequest) -> TTSResponse:
        """
        Convert text to speech using specified voice
        
        Args:
            request: TTSRequest with text, voice, and settings
            
        Returns:
            TTSResponse with audio data
        """
        url = f"/v1/text-to-speech/{request.voice_id}"
        
        # Build request body
        body = {
            "text": request.text,
            "model_id": request.model_id,
            "voice_settings": {
                "stability": request.stability,
                "similarity_boost": request.similarity_boost,
                "style": request.style,
                "use_speaker_boost": request.use_speaker_boost
            }
        }
        
        # Make request
        response = self.client.post(
            url,
            json=body,
            params={"output_format": request.output_format.value}
        )
        response.raise_for_status()
        
        return TTSResponse(
            audio_data=response.content,
            character_count=len(request.text),
            content_type=response.headers.get("content-type", "audio/mpeg"),
            request_id=response.headers.get("request-id")
        )
    
    def text_to_speech_simple(
        self, 
        text: str, 
        voice_id: str,
        model_id: str = DEFAULT_MODEL,
        stability: float = DEFAULT_STABILITY
    ) -> bytes:
        """
        Simple text-to-speech conversion
        
        Args:
            text: Text to convert
            voice_id: Voice ID to use
            model_id: Model ID (default: eleven_v3)
            stability: Voice stability (default: 0.5)
            
        Returns:
            Audio data as bytes
        """
        request = TTSRequest(
            text=text,
            voice_id=voice_id,
            model_id=model_id,
            stability=stability
        )
        response = self.text_to_speech(request)
        return response.audio_data
    
    async def text_to_speech_async(self, request: TTSRequest) -> TTSResponse:
        """
        Async version of text_to_speech
        """
        url = f"/v1/text-to-speech/{request.voice_id}"
        
        body = {
            "text": request.text,
            "model_id": request.model_id,
            "voice_settings": {
                "stability": request.stability,
                "similarity_boost": request.similarity_boost,
                "style": request.style,
                "use_speaker_boost": request.use_speaker_boost
            }
        }
        
        response = await self.async_client.post(
            url,
            json=body,
            params={"output_format": request.output_format.value}
        )
        response.raise_for_status()
        
        return TTSResponse(
            audio_data=response.content,
            character_count=len(request.text),
            content_type=response.headers.get("content-type", "audio/mpeg"),
            request_id=response.headers.get("request-id")
        )
    
    def text_to_speech_stream(
        self, 
        request: TTSRequest,
        chunk_callback: callable = None
    ):
        """
        Stream text-to-speech audio
        
        Args:
            request: TTSRequest with text, voice, and settings
            chunk_callback: Called with each audio chunk
        """
        url = f"/v1/text-to-speech/{request.voice_id}/stream"
        
        body = {
            "text": request.text,
            "model_id": request.model_id,
            "voice_settings": {
                "stability": request.stability,
                "similarity_boost": request.similarity_boost,
                "style": request.style,
                "use_speaker_boost": request.use_speaker_boost
            }
        }
        
        with self.client.stream(
            "POST",
            url,
            json=body,
            params={"output_format": request.output_format.value}
        ) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                if chunk_callback:
                    chunk_callback(chunk)
                yield chunk
    
    # ========================================================================
    # Multi-Speaker Dialogue
    # ========================================================================
    
    def text_to_dialogue(self, request: DialogueRequest) -> TTSResponse:
        """
        Convert multi-speaker dialogue to audio
        
        NOTE: Maximum 10 unique voices per request
        
        Args:
            request: DialogueRequest with lines and settings
            
        Returns:
            TTSResponse with concatenated audio
        """
        # Verify voice limit
        unique_voices = set(line.voice_id for line in request.lines)
        if len(unique_voices) > 10:
            raise ValueError(f"Maximum 10 unique voices allowed, got {len(unique_voices)}")
        
        url = "/v1/text-to-dialogue"
        
        # Build dialogue body
        dialogue = []
        for line in request.lines:
            dialogue.append({
                "text": line.text,
                "voice_id": line.voice_id,
                "voice_settings": {
                    "stability": request.stability,
                    "similarity_boost": request.similarity_boost
                }
            })
        
        body = {
            "model_id": request.model_id,
            "dialogue": dialogue
        }
        
        response = self.client.post(
            url,
            json=body,
            params={"output_format": request.output_format.value}
        )
        response.raise_for_status()
        
        total_chars = sum(len(line.text) for line in request.lines)
        
        return TTSResponse(
            audio_data=response.content,
            character_count=total_chars,
            content_type=response.headers.get("content-type", "audio/mpeg"),
            request_id=response.headers.get("request-id")
        )
    
    def dialogue_simple(
        self,
        lines: List[Dict[str, str]],  # [{"text": "...", "voice_id": "..."}]
        model_id: str = DEFAULT_MODEL
    ) -> bytes:
        """
        Simple dialogue conversion
        
        Args:
            lines: List of dicts with "text" and "voice_id" keys
            model_id: Model to use
            
        Returns:
            Audio data as bytes
        """
        dialogue_lines = [
            DialogueLine(text=line["text"], voice_id=line["voice_id"])
            for line in lines
        ]
        
        request = DialogueRequest(
            lines=dialogue_lines,
            model_id=model_id
        )
        
        response = self.text_to_dialogue(request)
        return response.audio_data
    
    # ========================================================================
    # Utility Methods
    # ========================================================================
    
    def save_audio(self, audio_data: bytes, filepath: str) -> str:
        """
        Save audio data to file
        
        Args:
            audio_data: Audio bytes
            filepath: Output file path
            
        Returns:
            Absolute path to saved file
        """
        # Ensure directory exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, "wb") as f:
            f.write(audio_data)
        
        return os.path.abspath(filepath)
    
    def get_character_count(self) -> Dict[str, int]:
        """
        Get current subscription character usage
        """
        response = self.client.get("/v1/user/subscription")
        response.raise_for_status()
        
        data = response.json()
        return {
            "character_count": data.get("character_count", 0),
            "character_limit": data.get("character_limit", 0),
            "remaining": data.get("character_limit", 0) - data.get("character_count", 0)
        }


# ============================================================================
# Convenience Functions
# ============================================================================

def quick_tts(text: str, voice_id: str, output_path: str = None) -> bytes:
    """
    Quick text-to-speech conversion
    
    Args:
        text: Text to convert
        voice_id: Voice ID to use
        output_path: Optional path to save audio
        
    Returns:
        Audio data as bytes
    """
    service = ElevenLabsService()
    audio = service.text_to_speech_simple(text, voice_id)
    
    if output_path:
        service.save_audio(audio, output_path)
    
    return audio


def list_voices() -> List[Dict]:
    """List all available voices"""
    service = ElevenLabsService()
    voices = service.get_voices()
    return [
        {
            "voice_id": v.voice_id,
            "name": v.name,
            "category": v.category,
            "labels": v.labels
        }
        for v in voices
    ]


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    # NOTE: Set ELEVENLABS_API_KEY environment variable before running
    
    print("ElevenLabs TTS Service Examples")
    print("=" * 50)
    
    try:
        service = ElevenLabsService()
        
        # List voices
        print("\nAvailable voices:")
        voices = service.get_voices()
        for voice in voices[:5]:  # Show first 5
            print(f"  - {voice.name} ({voice.voice_id})")
        
        # List models
        print("\nAvailable models:")
        models = service.get_models()
        for model in models:
            print(f"  - {model.get('name')} ({model.get('model_id')})")
        
        # Example TTS (uncomment to test)
        # audio = service.text_to_speech_simple(
        #     text="[sighs] I never thought it would come to this.",
        #     voice_id="YOUR_VOICE_ID",
        #     model_id="eleven_v3"
        # )
        # service.save_audio(audio, "output/test.mp3")
        # print("\nSaved audio to output/test.mp3")
        
        service.close()
        
    except ValueError as e:
        print(f"\nConfiguration error: {e}")
    except Exception as e:
        print(f"\nError: {e}")
