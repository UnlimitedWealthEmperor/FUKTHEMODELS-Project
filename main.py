"""
TTS Platform Backend API
FastAPI application providing text-to-speech with enhancement

Endpoints:
- /voices - List available voices
- /models - List available models
- /tts - Text-to-speech conversion
- /dialogue - Multi-speaker dialogue
- /enhance - Text enhancement with audio tags
- /tutorial - Audio tags reference
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
import json
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import io

# Import our services
from services.elevenlabs_service import ElevenLabsService, TTSRequest, DialogueLine, DialogueRequest, OutputFormat
from services.enhancement_service import EnhancementService, EnhancementResult, usage_stats
from services.character_service import CharacterService, CharacterProfile, SceneState, AVAILABLE_MOODS, ENERGY_LEVELS


# ============================================================================
# App Configuration
# ============================================================================

app = FastAPI(
    title="TTS Platform API",
    description="Text-to-Speech platform with ElevenLabs integration and smart enhancement",
    version="1.0.0"
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Services (initialized on startup)
elevenlabs_service: Optional[ElevenLabsService] = None
enhancement_service: Optional[EnhancementService] = None
character_service: Optional[CharacterService] = None

# Paths
BASE_DIR = Path(__file__).parent
CONFIG_DIR = BASE_DIR / "config"
DOCS_DIR = BASE_DIR / "docs"
OUTPUT_DIR = BASE_DIR / "output"
STATIC_DIR = BASE_DIR / "static"

# Mount static files
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ============================================================================
# Pydantic Models
# ============================================================================

class TTSInput(BaseModel):
    """Input for text-to-speech"""
    text: str = Field(..., description="Text to convert to speech")
    voice_id: str = Field(..., description="Voice ID to use")
    model_id: str = Field(default="eleven_v3", description="Model to use")
    stability: float = Field(default=0.5, ge=0, le=1, description="Voice stability")
    similarity_boost: float = Field(default=0.75, ge=0, le=1, description="Similarity boost")
    style: float = Field(default=0, ge=0, le=1, description="Style exaggeration")
    output_format: str = Field(default="mp3_44100_128", description="Output audio format")
    language_code: Optional[str] = Field(default=None, description="Language override (ISO 639-1 code)")
    # Enhancement options
    enhancement_mode: str = Field(
        default="none", 
        description="Enhancement mode: 'none' (manual tags only), 'v3_native' (V3 interprets tags), 'smart' (LLM-powered)"
    )
    enhance_intensity: int = Field(default=3, ge=1, le=5, description="Enhancement intensity (for smart mode)")
    enhance_genre: str = Field(default="drama", description="Genre for enhancement (for smart mode)")
    character_archetype: Optional[str] = Field(default=None, description="Character archetype (for smart mode)")


class DialogueLineInput(BaseModel):
    """Single line in dialogue"""
    text: str
    voice_id: str
    character_name: Optional[str] = None


class DialogueInput(BaseModel):
    """Input for multi-speaker dialogue"""
    lines: List[DialogueLineInput]
    model_id: str = Field(default="eleven_v3")
    stability: float = Field(default=0.5)
    similarity_boost: float = Field(default=0.75)
    output_format: str = Field(default="mp3_44100_128")
    enhancement_mode: str = Field(default="none", description="'none', 'v3_native', or 'smart'")
    enhance_intensity: int = Field(default=3)
    enhance_genre: str = Field(default="drama")


class EnhanceInput(BaseModel):
    """Input for text enhancement"""
    text: str = Field(..., description="Text to enhance")
    intensity: int = Field(default=3, ge=1, le=5, description="Enhancement intensity (1-5)")
    genre: str = Field(default="drama", description="Content genre")
    # Character context (optional)
    character_id: Optional[str] = Field(default=None, description="Character profile ID")
    mood: str = Field(default="neutral", description="Current mood: happy, sad, angry, anxious, excited, tired, scared, calm, flirty, annoyed, hopeful, defeated")
    energy: str = Field(default="medium", description="Energy level: low, medium, high")
    scene_context: Optional[str] = Field(default=None, description="What's happening in the scene")


class EnhanceResponse(BaseModel):
    """Response from enhancement"""
    original_text: str
    enhanced_text: str
    tags_used: List[str]
    confidence_score: float
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    cost_usd_x20: float = 0.0  # Client price (real cost × 20)
    # Pre-formatted strings for display
    cost_usd_formatted: str = "$0.000000"
    cost_usd_x20_formatted: str = "$0.0000"


class UsageStatsResponse(BaseModel):
    """Usage statistics response"""
    total_requests: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    total_cost_usd_x20: float  # Client price (real cost × 20)
    # Pre-formatted strings for display
    total_cost_usd_formatted: str = "$0.000000"
    total_cost_usd_x20_formatted: str = "$0.0000"


class VoiceInfo(BaseModel):
    """Voice information"""
    voice_id: str
    name: str
    category: str = ""
    description: str = ""
    preview_url: Optional[str] = None
    labels: Dict[str, str]


class ModelInfo(BaseModel):
    """Model information"""
    model_id: str
    name: str
    description: str
    languages: List[str]
    max_characters: Optional[int]
    
    
# ============================================================================
# Startup/Shutdown Events
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global elevenlabs_service, enhancement_service, character_service
    
    # Create output directory
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Initialize ElevenLabs service
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if api_key:
        elevenlabs_service = ElevenLabsService(api_key=api_key)
        print("✓ ElevenLabs service initialized")
    else:
        print("⚠ ELEVENLABS_API_KEY not set - TTS endpoints will not work")
    
    # Initialize Enhancement service (uses ANTHROPIC_API_KEY)
    enhancement_service = EnhancementService()
    if enhancement_service.is_available:
        print("✓ Enhancement service initialized (Claude 3.5 Sonnet)")
    else:
        print("⚠ Enhancement service initialized but ANTHROPIC_API_KEY not set - AI enhancement unavailable")
    
    # Initialize Character service
    character_service = CharacterService()
    print(f"✓ Character service initialized ({len(character_service.characters)} characters))")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global elevenlabs_service
    if elevenlabs_service:
        elevenlabs_service.close()


# ============================================================================
# Health & Info Endpoints
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the frontend dashboard"""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("<h1>TTS Platform API</h1><p>Frontend not found. API is running.</p>")


@app.get("/api")
async def api_info():
    """API info endpoint"""
    return {
        "status": "ok",
        "service": "TTS Platform API",
        "version": "1.0.0",
        "elevenlabs_configured": elevenlabs_service is not None
    }


@app.get("/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "services": {
            "elevenlabs": elevenlabs_service is not None,
            "enhancement": enhancement_service is not None
        },
        "timestamp": datetime.utcnow().isoformat()
    }


# ============================================================================
# Voice Endpoints
# ============================================================================

@app.get("/voices", response_model=List[VoiceInfo])
async def list_voices(
    search: Optional[str] = Query(None, description="Search query"),
    category: Optional[str] = Query(None, description="Filter by category")
):
    """List available voices"""
    if not elevenlabs_service:
        raise HTTPException(status_code=503, detail="ElevenLabs service not configured")
    
    voices = elevenlabs_service.get_voices()
    
    # Apply search filter
    if search:
        voices = elevenlabs_service.search_voices(search)
    
    # Apply category filter
    if category:
        voices = [v for v in voices if v.category.lower() == category.lower()]
    
    return [
        VoiceInfo(
            voice_id=v.voice_id,
            name=v.name,
            category=v.category,
            description=v.description,
            preview_url=v.preview_url,
            labels=v.labels
        )
        for v in voices
    ]


@app.get("/voices/{voice_id}", response_model=VoiceInfo)
async def get_voice(voice_id: str):
    """Get specific voice details"""
    if not elevenlabs_service:
        raise HTTPException(status_code=503, detail="ElevenLabs service not configured")
    
    voice = elevenlabs_service.get_voice(voice_id)
    if not voice:
        raise HTTPException(status_code=404, detail="Voice not found")
    
    return VoiceInfo(
        voice_id=voice.voice_id,
        name=voice.name,
        category=voice.category,
        description=voice.description,
        preview_url=voice.preview_url,
        labels=voice.labels
    )


# ============================================================================
# Model Endpoints
# ============================================================================

@app.get("/models")
async def list_models():
    """List available TTS models"""
    if not elevenlabs_service:
        raise HTTPException(status_code=503, detail="ElevenLabs service not configured")
    
    models = elevenlabs_service.get_models()
    return [
        {
            "model_id": m.get("model_id"),
            "name": m.get("name"),
            "description": m.get("description", ""),
            "languages": [lang.get("name") for lang in m.get("languages", [])],
            "max_characters": m.get("max_characters_request_free_user")
        }
        for m in models
    ]


# ============================================================================
# TTS Endpoints
# ============================================================================

@app.post("/tts")
async def text_to_speech(input: TTSInput, background_tasks: BackgroundTasks):
    """
    Convert text to speech
    
    Enhancement modes:
    - none: Send text as-is (you add [tags] manually)
    - v3_native: V3 model interprets [tags] natively (FREE, built-in)
    - smart: Our LLM adds contextual tags before sending to V3
    
    Returns audio file directly
    """
    if not elevenlabs_service:
        raise HTTPException(status_code=503, detail="ElevenLabs service not configured")
    
    text = input.text
    enhanced_text = None
    
    # Handle enhancement modes
    if input.enhancement_mode == "smart" and enhancement_service:
        # Our LLM-powered enhancement - adds contextual audio tags
        enhanced_text = enhancement_service.enhance_simple(
            text=text,
            genre=input.enhance_genre,
            intensity=input.enhance_intensity
        )
        text = enhanced_text
    elif input.enhancement_mode == "v3_native":
        # V3 native - text goes directly to V3 which interprets [tags]
        # No modification needed, V3 handles tags natively
        pass
    # else: "none" - text sent as-is
    
    # Build TTS request
    try:
        output_format = OutputFormat(input.output_format)
    except ValueError:
        output_format = OutputFormat.MP3_44100_128
    
    request = TTSRequest(
        text=text,
        voice_id=input.voice_id,
        model_id=input.model_id,
        stability=input.stability,
        similarity_boost=input.similarity_boost,
        style=input.style,
        output_format=output_format,
        language_code=input.language_code
    )
    
    try:
        response = elevenlabs_service.text_to_speech(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    # Return audio as streaming response
    headers = {
        "Content-Disposition": f"attachment; filename=speech_{uuid.uuid4().hex[:8]}.mp3",
        "X-Character-Count": str(response.character_count),
        "X-Request-ID": response.request_id or "",
        "X-Enhancement-Mode": input.enhancement_mode
    }
    
    # Include enhanced text in header if smart enhancement was used
    if enhanced_text:
        import urllib.parse
        headers["X-Enhanced-Text"] = urllib.parse.quote(enhanced_text[:500])  # Limit for header size
    
    return StreamingResponse(
        io.BytesIO(response.audio_data),
        media_type=response.content_type,
        headers=headers
    )


@app.post("/tts/stream")
async def text_to_speech_stream(input: TTSInput):
    """
    Stream text-to-speech audio
    """
    if not elevenlabs_service:
        raise HTTPException(status_code=503, detail="ElevenLabs service not configured")
    
    text = input.text
    
    if input.enhance and enhancement_service:
        text = enhancement_service.enhance_simple(
            text=text,
            genre=input.enhance_genre,
            intensity=input.enhance_intensity
        )
    
    try:
        output_format = OutputFormat(input.output_format)
    except ValueError:
        output_format = OutputFormat.MP3_44100_128
    
    request = TTSRequest(
        text=text,
        voice_id=input.voice_id,
        model_id=input.model_id,
        stability=input.stability,
        similarity_boost=input.similarity_boost,
        style=input.style,
        output_format=output_format,
        language_code=input.language_code
    )
    
    def generate():
        for chunk in elevenlabs_service.text_to_speech_stream(request):
            yield chunk
    
    return StreamingResponse(
        generate(),
        media_type="audio/mpeg"
    )


# ============================================================================
# Dialogue Endpoints
# ============================================================================

@app.post("/dialogue")
async def text_to_dialogue(input: DialogueInput):
    """
    Convert multi-speaker dialogue to audio
    
    Maximum 10 unique voices per request
    """
    if not elevenlabs_service:
        raise HTTPException(status_code=503, detail="ElevenLabs service not configured")
    
    # Check voice limit
    unique_voices = set(line.voice_id for line in input.lines)
    if len(unique_voices) > 10:
        raise HTTPException(
            status_code=400, 
            detail=f"Maximum 10 unique voices allowed, got {len(unique_voices)}"
        )
    
    # Prepare lines (optionally enhance)
    dialogue_lines = []
    for line in input.lines:
        text = line.text
        
        if input.enhance and enhancement_service:
            text = enhancement_service.enhance_simple(
                text=text,
                genre=input.enhance_genre,
                intensity=input.enhance_intensity
            )
        
        dialogue_lines.append(DialogueLine(text=text, voice_id=line.voice_id))
    
    # Build request
    try:
        output_format = OutputFormat(input.output_format)
    except ValueError:
        output_format = OutputFormat.MP3_44100_128
    
    request = DialogueRequest(
        lines=dialogue_lines,
        model_id=input.model_id,
        stability=input.stability,
        similarity_boost=input.similarity_boost,
        output_format=output_format
    )
    
    try:
        response = elevenlabs_service.text_to_dialogue(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    return StreamingResponse(
        io.BytesIO(response.audio_data),
        media_type=response.content_type,
        headers={
            "Content-Disposition": f"attachment; filename=dialogue_{uuid.uuid4().hex[:8]}.mp3",
            "X-Character-Count": str(response.character_count),
            "X-Request-ID": response.request_id or ""
        }
    )


# ============================================================================
# Enhancement Endpoints
# ============================================================================

@app.post("/enhance", response_model=EnhanceResponse)
async def enhance_text(input: EnhanceInput):
    """
    Enhance text with audio tags using Claude 3.5 Sonnet
    
    Analyzes text for emotional context and adds appropriate [audio tags].
    Optionally uses character profile and scene state for consistency.
    """
    if not enhancement_service:
        raise HTTPException(status_code=503, detail="Enhancement service not configured")
    
    if not enhancement_service.is_available:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not set - AI enhancement unavailable")
    
    # Build character context if provided
    character_prompt = None
    if input.character_id and character_service:
        character = character_service.get(input.character_id)
        if character:
            scene = SceneState(
                mood=input.mood,
                energy=input.energy,
                context=input.scene_context
            )
            character_prompt = character_service.get_prompt_section(character, scene)
    
    # Run enhancement with Claude
    result = enhancement_service.enhance(
        text=input.text,
        intensity=input.intensity,
        genre=input.genre,
        character_prompt=character_prompt,
        mood=input.mood if not input.character_id else None  # Use mood directly if no character
    )
    
    # Calculate costs in backend
    cost_x20 = result.cost_usd * 20
    
    return EnhanceResponse(
        original_text=result.original_text,
        enhanced_text=result.enhanced_text,
        tags_used=result.tags_used,
        confidence_score=result.confidence_score,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
        cost_usd_x20=cost_x20,
        cost_usd_formatted=f"${result.cost_usd:.6f}",
        cost_usd_x20_formatted=f"${cost_x20:.4f}"
    )


@app.get("/usage", response_model=UsageStatsResponse)
async def get_usage_stats():
    """
    Get cumulative usage statistics for AI enhancement.
    Shows actual API cost and client price (×20 markup).
    Resets when server restarts.
    """
    # Calculate all values in backend
    total_cost = round(usage_stats.total_cost_usd, 6)
    total_cost_x20 = round(usage_stats.total_cost_usd * 20, 4)
    
    return UsageStatsResponse(
        total_requests=usage_stats.total_requests,
        total_input_tokens=usage_stats.total_input_tokens,
        total_output_tokens=usage_stats.total_output_tokens,
        total_cost_usd=total_cost,
        total_cost_usd_x20=total_cost_x20,
        total_cost_usd_formatted=f"${total_cost:.6f}",
        total_cost_usd_x20_formatted=f"${total_cost_x20:.4f}"
    )


@app.post("/enhance/simple")
async def enhance_text_simple(
    text: str = Query(..., description="Text to enhance"),
    intensity: int = Query(3, ge=1, le=5, description="Enhancement intensity"),
    genre: str = Query("drama", description="Content genre")
):
    """Simple enhancement endpoint - just pass text and get enhanced text back"""
    if not enhancement_service:
        raise HTTPException(status_code=503, detail="Enhancement service not configured")
    
    enhanced = enhancement_service.enhance_simple(text, genre, intensity)
    
    return {
        "original": text,
        "enhanced": enhanced
    }


@app.get("/enhance/archetypes")
async def list_archetypes():
    """List available character archetypes for enhancement (legacy endpoint)"""
    # Character archetypes are no longer used with the Claude enhancement
    # Keeping endpoint for backwards compatibility
    return []


@app.get("/enhance/genres")
async def list_genres():
    """List available genres for enhancement"""
    return [
        {"id": "drama", "name": "Drama", "description": "Emotional depth, pauses, subtle delivery changes"},
        {"id": "comedy", "name": "Comedy", "description": "Timing beats, chuckles, playful delivery"},
        {"id": "thriller", "name": "Thriller", "description": "Tension, whispers, nervous sounds"},
        {"id": "romance", "name": "Romance", "description": "Tender, soft, warm delivery with sighs"},
        {"id": "horror", "name": "Horror", "description": "Fear, gasps, trembling voice"},
        {"id": "action", "name": "Action", "description": "Punchy, urgent, short pauses"},
        {"id": "documentary", "name": "Documentary", "description": "Calm, serious, measured delivery"},
        {"id": "podcast", "name": "Podcast", "description": "Conversational, natural laughs, thinking pauses"}
    ]


@app.get("/enhance/modes")
async def get_enhancement_modes():
    """
    Get information about available enhancement modes
    """
    return {
        "modes": [
            {
                "id": "none",
                "name": "Manual / None",
                "description": "No automatic enhancement. You manually add [audio tags] to your text.",
                "cost": "Free",
                "latency": "None",
                "best_for": "When you want full control over tag placement",
                "example_input": "I can't believe this happened.",
                "example_output": "I can't believe this happened."
            },
            {
                "id": "smart",
                "name": "AI Enhancement (Claude)",
                "description": "Claude 3.5 Sonnet analyzes your text and intelligently adds contextual audio tags.",
                "cost": "Uses Anthropic API",
                "latency": "+1-2 seconds",
                "best_for": "Automated enhancement with emotional understanding and genre-specific styling",
                "features": [
                    "Emotional context analysis",
                    "Genre-specific tag selection",
                    "Intensity control (1-5)",
                    "Understanding of subtext and sarcasm"
                ],
                "example_input": "I can't believe this happened.",
                "example_output": "[sighs deeply] I can't believe this happened."
            }
        ],
        "recommendation": "Use 'AI Enhancement' for intelligent, context-aware enhancement. Use 'Manual' if you prefer full control."
    }


@app.get("/enhance/moods")
async def list_moods():
    """List available moods for enhancement"""
    return AVAILABLE_MOODS


@app.get("/enhance/energy-levels")
async def list_energy_levels():
    """List available energy levels"""
    return ENERGY_LEVELS


# ============================================================================
# Character Endpoints
# ============================================================================

class CharacterInput(BaseModel):
    """Input for creating/updating a character"""
    name: str = Field(..., description="Character name")
    age: Optional[int] = Field(default=None, description="Character age")
    background: Optional[str] = Field(default=None, description="Background (e.g., 'NYC nurse', 'retired marine')")
    personality: Optional[str] = Field(default=None, description="Personality traits (e.g., 'introverted, sarcastic, warm')")
    speaking_style: Optional[str] = Field(default=None, description="How they speak (e.g., 'formal', 'uses filler words')")
    voice_direction: Optional[str] = Field(default=None, description="Voice actor direction (e.g., 'think tired nurse')")
    quirks: Optional[str] = Field(default=None, description="Speech quirks (e.g., 'clears throat when nervous')")


@app.get("/characters")
async def list_characters():
    """List all character profiles"""
    if not character_service:
        raise HTTPException(status_code=503, detail="Character service not available")
    
    return [
        {
            "id": c.id,
            "name": c.name,
            "age": c.age,
            "background": c.background,
            "personality": c.personality,
            "speaking_style": c.speaking_style,
            "voice_direction": c.voice_direction,
            "quirks": c.quirks,
            "created_at": c.created_at
        }
        for c in character_service.list_all()
    ]


@app.post("/characters")
async def create_character(input: CharacterInput):
    """Create a new character profile"""
    if not character_service:
        raise HTTPException(status_code=503, detail="Character service not available")
    
    char = character_service.create(
        name=input.name,
        age=input.age,
        background=input.background,
        personality=input.personality,
        speaking_style=input.speaking_style,
        voice_direction=input.voice_direction,
        quirks=input.quirks
    )
    
    return {
        "id": char.id,
        "name": char.name,
        "message": f"Character '{char.name}' created"
    }


@app.get("/characters/{character_id}")
async def get_character(character_id: str):
    """Get a character by ID"""
    if not character_service:
        raise HTTPException(status_code=503, detail="Character service not available")
    
    char = character_service.get(character_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")
    
    return {
        "id": char.id,
        "name": char.name,
        "age": char.age,
        "background": char.background,
        "personality": char.personality,
        "speaking_style": char.speaking_style,
        "voice_direction": char.voice_direction,
        "quirks": char.quirks,
        "created_at": char.created_at
    }


@app.put("/characters/{character_id}")
async def update_character(character_id: str, input: CharacterInput):
    """Update a character profile"""
    if not character_service:
        raise HTTPException(status_code=503, detail="Character service not available")
    
    char = character_service.update(
        character_id,
        name=input.name,
        age=input.age,
        background=input.background,
        personality=input.personality,
        speaking_style=input.speaking_style,
        voice_direction=input.voice_direction,
        quirks=input.quirks
    )
    
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")
    
    return {"message": f"Character '{char.name}' updated"}


@app.delete("/characters/{character_id}")
async def delete_character(character_id: str):
    """Delete a character profile"""
    if not character_service:
        raise HTTPException(status_code=503, detail="Character service not available")
    
    if not character_service.delete(character_id):
        raise HTTPException(status_code=404, detail="Character not found")
    
    return {"message": "Character deleted"}


# ============================================================================
# Tutorial Endpoints
# ============================================================================

@app.get("/tutorial/audio-tags")
async def get_audio_tags_tutorial():
    """Get the full audio tags tutorial"""
    tutorial_path = DOCS_DIR / "audio-tags-tutorial.json"
    
    if not tutorial_path.exists():
        raise HTTPException(status_code=404, detail="Tutorial not found")
    
    with open(tutorial_path, "r") as f:
        return json.load(f)


@app.get("/tutorial/audio-tags/categories")
async def get_tag_categories():
    """Get just the tag categories"""
    tutorial_path = DOCS_DIR / "audio-tags-tutorial.json"
    
    if not tutorial_path.exists():
        raise HTTPException(status_code=404, detail="Tutorial not found")
    
    with open(tutorial_path, "r") as f:
        data = json.load(f)
    
    return data.get("categories", [])


@app.get("/tutorial/audio-tags/quick-reference")
async def get_quick_reference():
    """Get quick reference for all audio tags"""
    tutorial_path = DOCS_DIR / "audio-tags-tutorial.json"
    
    if not tutorial_path.exists():
        raise HTTPException(status_code=404, detail="Tutorial not found")
    
    with open(tutorial_path, "r") as f:
        data = json.load(f)
    
    categories = data.get("categories", [])
    reference = {}
    
    for cat in categories:
        cat_name = cat.get("name", "Unknown")
        reference[cat_name] = [tag.get("tag") for tag in cat.get("tags", [])]
    
    return reference


# ============================================================================
# Usage & Stats Endpoints
# ============================================================================

@app.get("/usage")
async def get_usage():
    """Get current API usage statistics"""
    if not elevenlabs_service:
        raise HTTPException(status_code=503, detail="ElevenLabs service not configured")
    
    try:
        usage = elevenlabs_service.get_character_count()
        return usage
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Run Server
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True
    )
