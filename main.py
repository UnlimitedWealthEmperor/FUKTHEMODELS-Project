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

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, Request, Depends, Cookie
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import io

# Import our services
from services.elevenlabs_service import ElevenLabsService, TTSRequest, DialogueLine, DialogueRequest, OutputFormat
from services.enhancement_service import EnhancementService, EnhancementResult, usage_stats
from services.character_service import CharacterService, CharacterProfile, SceneState, AVAILABLE_MOODS, ENERGY_LEVELS
from services.storage_service import StorageService, get_storage_service
from services.sheets_service import get_sheets_service
from services.auth_service import get_auth_service, AuthService


# ============================================================================
# App Configuration
# ============================================================================

app = FastAPI(
    title="FuckTheModels API",
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


# ============================================================================
# Authentication Middleware
# ============================================================================

# Routes that don't require authentication
PUBLIC_ROUTES = {"/", "/auth/status", "/auth/setup", "/auth/login", "/auth/logout", "/docs", "/openapi.json", "/redoc"}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Check authentication for protected routes"""
    path = request.url.path
    
    # Allow public routes
    if path in PUBLIC_ROUTES or path.startswith("/static"):
        return await call_next(request)
    
    # Get auth service
    auth = get_auth_service()
    
    # If password not set up, allow all (setup will be forced on frontend)
    if not auth.is_setup:
        return await call_next(request)
    
    # Check session token from cookie or header
    session_token = request.cookies.get("session_token")
    if not session_token:
        # Also check Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            session_token = auth_header[7:]
    
    if not session_token or not auth.verify_session(session_token):
        return JSONResponse(
            status_code=401,
            content={"detail": "Not authenticated", "needs_login": True}
        )
    
    return await call_next(request)

# Services (initialized on startup)
elevenlabs_service: Optional[ElevenLabsService] = None
enhancement_service: Optional[EnhancementService] = None
character_service: Optional[CharacterService] = None
storage_service: Optional[StorageService] = None
sheets_service = None  # Google Sheets database service
auth_service: Optional[AuthService] = None  # Password authentication

# Paths
BASE_DIR = Path(__file__).parent
CONFIG_DIR = BASE_DIR / "config"
DOCS_DIR = BASE_DIR / "docs"
OUTPUT_DIR = BASE_DIR / "output"
STATIC_DIR = BASE_DIR / "static"
GENERATED_DIR = BASE_DIR / "generated"  # Audio file storage
HISTORY_FILE = BASE_DIR / "history.json"  # History persistence

# History storage (in-memory, persisted to JSON)
generation_history: List[Dict[str, Any]] = []

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
    # Separate Claude and ElevenLabs stats
    claude_requests: int = 0
    claude_input_tokens: int = 0
    claude_output_tokens: int = 0
    claude_cost_usd: float = 0.0
    elevenlabs_requests: int = 0
    elevenlabs_characters: int = 0
    elevenlabs_cost_usd: float = 0.0


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


class HistoryItem(BaseModel):
    """History item for generation tracking"""
    id: str
    text: str
    text_preview: str  # Truncated for display
    voice_id: str
    voice_name: str
    model_id: str
    timestamp: str
    timestamp_relative: str  # "3 hours ago"
    audio_filename: str
    character_count: int
    
    
# ============================================================================
# Startup/Shutdown Events
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global elevenlabs_service, enhancement_service, character_service, storage_service, sheets_service, auth_service, generation_history
    
    # Initialize Authentication service
    auth_service = get_auth_service()
    if auth_service.is_setup:
        print("✓ Authentication enabled (password protected)")
    else:
        print("⚠ Password not set - setup required on first access")
    
    # Create output directory
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Create generated audio directory (for local fallback)
    GENERATED_DIR.mkdir(exist_ok=True)
    
    # Initialize Storage service (GCS or local fallback)
    storage_service = StorageService(local_fallback_dir=GENERATED_DIR)
    
    # Initialize Google Sheets database service
    sheets_service = get_sheets_service()
    if sheets_service.is_available:
        await sheets_service.ensure_headers()
        # Load history from Sheets
        generation_history = await sheets_service.get_all_entries()
        # Update relative timestamps
        for item in generation_history:
            item["timestamp_relative"] = get_relative_time(item.get("timestamp", ""))
            item["text_preview"] = item["text"][:60] + "..." if len(item.get("text", "")) > 60 else item.get("text", "")
        print(f"✓ Google Sheets database initialized ({len(generation_history)} history items)")
    else:
        # Fallback to local JSON file
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, 'r') as f:
                    generation_history = json.load(f)
                print(f"✓ Loaded {len(generation_history)} history items from local file")
            except Exception as e:
                print(f"⚠ Could not load history: {e}")
                generation_history = []
        print("⚠ Using local JSON for history (set GOOGLE_SHEETS_ID for cloud persistence)")
    
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
# History Helpers
# ============================================================================

def get_relative_time(timestamp_str: str) -> str:
    """Convert ISO timestamp to relative time string"""
    try:
        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        now = datetime.now(timestamp.tzinfo) if timestamp.tzinfo else datetime.now()
        diff = now - timestamp
        
        seconds = diff.total_seconds()
        if seconds < 60:
            return f"{int(seconds)} seconds ago"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        else:
            days = int(seconds / 86400)
            return f"{days} day{'s' if days != 1 else ''} ago"
    except:
        return "just now"


def save_history():
    """Persist history to JSON file"""
    try:
        with open(HISTORY_FILE, 'w') as f:
            json.dump(generation_history, f, indent=2)
    except Exception as e:
        print(f"⚠ Could not save history: {e}")


async def add_to_history(
    text: str,
    voice_id: str,
    voice_name: str,
    model_id: str,
    audio_data: bytes,
    character_count: int,
    language_code: Optional[str] = None
) -> Dict[str, Any]:
    """Add a new item to generation history"""
    global generation_history
    
    # Generate unique ID and filename
    item_id = uuid.uuid4().hex[:12]
    timestamp = datetime.now().isoformat()
    audio_filename = f"gen_{item_id}.mp3"
    
    # Save audio file using storage service (GCS or local)
    if storage_service:
        storage_service.save_audio(audio_data, audio_filename)
    else:
        # Fallback to direct local save
        audio_path = GENERATED_DIR / audio_filename
        with open(audio_path, 'wb') as f:
            f.write(audio_data)
    
    # Create history item for in-memory storage
    history_item = {
        "id": item_id,
        "text": text,
        "text_preview": text[:60] + "..." if len(text) > 60 else text,
        "voice_id": voice_id,
        "voice_name": voice_name,
        "model_id": model_id,
        "timestamp": timestamp,
        "timestamp_relative": get_relative_time(timestamp),
        "audio_filename": audio_filename,
        "character_count": character_count,
        "storage_type": storage_service.storage_type if storage_service else "local"
    }
    
    # Save to Google Sheets database
    if sheets_service and sheets_service.is_available:
        sheets_entry = {
            "id": item_id,
            "text": text,
            "voice_id": voice_id,
            "voice_name": voice_name,
            "model": model_id,
            "language": language_code or "",
            "characters": character_count,
            "cost": round(character_count * 0.00003, 6),  # Approximate cost
            "timestamp": timestamp,
            "audio_path": audio_filename
        }
        await sheets_service.add_entry(sheets_entry)
    
    # Add to beginning of list (most recent first)
    generation_history.insert(0, history_item)
    
    # Keep only last 100 items in memory
    if len(generation_history) > 100:
        generation_history = generation_history[:100]
    
    # Also persist to local JSON as backup
    save_history()
    
    return history_item


async def track_ai_usage(
    service: str,
    usage_type: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    characters: int = 0,
    cost_usd: float = 0.0,
    description: str = ""
):
    """
    Track AI service usage in Google Sheets for persistent cost tracking
    
    Args:
        service: "claude" or "elevenlabs"
        usage_type: "enhancement" for Claude, "tts" for ElevenLabs  
        input_tokens: Input tokens (Claude only)
        output_tokens: Output tokens (Claude only)
        characters: Characters used (ElevenLabs only)
        cost_usd: Cost in USD
        description: Optional description
    """
    if sheets_service and sheets_service.is_available:
        await sheets_service.add_usage_entry(
            service=service,
            usage_type=usage_type,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            characters=characters,
            cost_usd=cost_usd,
            description=description
        )


# ============================================================================
# Authentication Endpoints
# ============================================================================

class SetupPasswordRequest(BaseModel):
    password: str = Field(..., min_length=1, description="Password to set")


class LoginRequest(BaseModel):
    password: str = Field(..., description="Password to verify")


@app.get("/auth/status")
async def get_auth_status():
    """Check authentication status"""
    auth = get_auth_service()
    return {
        "is_setup": auth.is_setup,
        "needs_setup": not auth.is_setup
    }


@app.post("/auth/setup")
async def setup_password(request: SetupPasswordRequest):
    """
    Set up the initial password (first-time only)
    
    Once set, cannot be changed through this endpoint
    """
    auth = get_auth_service()
    
    if auth.is_setup:
        raise HTTPException(
            status_code=400,
            detail="Password already configured. Cannot change through this endpoint."
        )
    
    if not request.password:
        raise HTTPException(status_code=400, detail="Password cannot be empty")
    
    success = auth.setup_password(request.password)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to set up password")
    
    # Auto-login after setup
    token = auth.create_session(request.password)
    
    response = JSONResponse(content={
        "success": True,
        "message": "Password configured successfully"
    })
    
    # Set session cookie
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        max_age=86400,  # 24 hours
        samesite="lax"
    )
    
    return response


@app.post("/auth/login")
async def login(request: LoginRequest):
    """
    Login with password
    
    Returns session token in cookie
    """
    auth = get_auth_service()
    
    if not auth.is_setup:
        raise HTTPException(
            status_code=400,
            detail="Password not set up yet. Use /auth/setup first."
        )
    
    token = auth.create_session(request.password)
    
    if not token:
        raise HTTPException(status_code=401, detail="Invalid password")
    
    response = JSONResponse(content={
        "success": True,
        "message": "Login successful"
    })
    
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        max_age=86400,  # 24 hours
        samesite="lax"
    )
    
    return response


@app.post("/auth/logout")
async def logout(request: Request):
    """Logout and invalidate session"""
    auth = get_auth_service()
    
    # Get session token
    session_token = request.cookies.get("session_token")
    if session_token:
        auth.invalidate_session(session_token)
    
    response = JSONResponse(content={
        "success": True,
        "message": "Logged out successfully"
    })
    
    # Clear cookie
    response.delete_cookie(key="session_token")
    
    return response


# ============================================================================
# History Endpoints
# ============================================================================

@app.get("/history")
async def get_history(
    search: Optional[str] = Query(None, description="Search text"),
    voice: Optional[str] = Query(None, description="Filter by voice name"),
    model: Optional[str] = Query(None, description="Filter by model"),
    date: Optional[str] = Query(None, description="Filter by date: today, week, month"),
    limit: int = Query(50, description="Max items to return")
):
    """Get generation history with optional filters"""
    global generation_history
    
    # Update relative timestamps
    for item in generation_history:
        item["timestamp_relative"] = get_relative_time(item["timestamp"])
    
    filtered = generation_history.copy()
    
    # Apply search filter
    if search:
        search_lower = search.lower()
        filtered = [
            item for item in filtered 
            if search_lower in item["text"].lower() or 
               search_lower in item["voice_name"].lower()
        ]
    
    # Apply voice filter
    if voice:
        voice_lower = voice.lower()
        filtered = [
            item for item in filtered 
            if voice_lower in item["voice_name"].lower()
        ]
    
    # Apply model filter
    if model:
        filtered = [
            item for item in filtered 
            if model.lower() in item["model_id"].lower()
        ]
    
    # Apply date filter
    if date:
        now = datetime.now()
        filtered_by_date = []
        for item in filtered:
            try:
                item_date = datetime.fromisoformat(item["timestamp"].replace('Z', '+00:00'))
                if item_date.tzinfo:
                    item_date = item_date.replace(tzinfo=None)
                
                if date == "today":
                    if item_date.date() == now.date():
                        filtered_by_date.append(item)
                elif date == "week":
                    if (now - item_date).days <= 7:
                        filtered_by_date.append(item)
                elif date == "month":
                    if (now - item_date).days <= 30:
                        filtered_by_date.append(item)
                else:
                    filtered_by_date.append(item)
            except:
                filtered_by_date.append(item)
        filtered = filtered_by_date
    
    return filtered[:limit]


@app.get("/history/{item_id}/audio")
async def get_history_audio(item_id: str):
    """Get audio file for a history item"""
    # Find the item
    item = next((h for h in generation_history if h["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="History item not found")
    
    filename = item["audio_filename"]
    
    # Try to get from storage service
    if storage_service:
        audio_data = storage_service.get_audio(filename)
        if audio_data:
            return StreamingResponse(
                io.BytesIO(audio_data),
                media_type="audio/mpeg",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
    
    # Fallback to local file
    audio_path = GENERATED_DIR / filename
    if audio_path.exists():
        return FileResponse(
            audio_path,
            media_type="audio/mpeg",
            filename=filename
        )
    
    raise HTTPException(status_code=404, detail="Audio file not found")


@app.delete("/history/{item_id}")
async def delete_history_item(item_id: str):
    """Delete a history item"""
    global generation_history
    
    # Find and remove the item
    item = next((h for h in generation_history if h["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="History item not found")
    
    # Delete audio file using storage service
    filename = item.get("audio_filename", "")
    if storage_service and filename:
        storage_service.delete_audio(filename)
    else:
        audio_path = GENERATED_DIR / filename
        if audio_path.exists():
            audio_path.unlink()
    
    # Delete from Google Sheets database
    if sheets_service and sheets_service.is_available:
        await sheets_service.delete_entry(item_id)
    
    # Remove from in-memory list
    generation_history = [h for h in generation_history if h["id"] != item_id]
    save_history()
    
    return {"status": "deleted", "id": item_id}


# ============================================================================
# Health & Info Endpoints
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the frontend dashboard"""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("<h1>FuckTheModels API</h1><p>Frontend not found. API is running.</p>")


@app.get("/api")
async def api_info():
    """API info endpoint"""
    return {
        "status": "ok",
        "service": "FuckTheModels API",
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
    enhancement_result = None
    
    # Handle enhancement modes
    if input.enhancement_mode == "smart" and enhancement_service:
        # Our LLM-powered enhancement - adds contextual audio tags
        enhancement_result = enhancement_service.enhance(
            text=text,
            intensity=input.enhance_intensity,
            genre=input.enhance_genre
        )
        enhanced_text = enhancement_result.enhanced_text
        text = enhanced_text
        
        # Track Claude usage if enhancement was successful and had tokens
        if enhancement_result.input_tokens > 0:
            await track_ai_usage(
                service="claude",
                usage_type="enhancement",
                input_tokens=enhancement_result.input_tokens,
                output_tokens=enhancement_result.output_tokens,
                cost_usd=enhancement_result.cost_usd,
                description=f"Smart enhancement ({input.enhance_genre}, intensity {input.enhance_intensity})"
            )
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
    
    # Get voice name for history
    voice_name = "Unknown Voice"
    try:
        voice = elevenlabs_service.get_voice(input.voice_id)
        if voice:
            voice_name = voice.name
    except:
        pass
    
    # Save to history
    history_item = await add_to_history(
        text=input.text,
        voice_id=input.voice_id,
        voice_name=voice_name,
        model_id=input.model_id,
        audio_data=response.audio_data,
        character_count=response.character_count,
        language_code=input.language_code
    )
    
    # Track ElevenLabs usage (cost ~$0.30 per 1000 characters for most plans)
    elevenlabs_cost = round(response.character_count * 0.0003, 6)  # $0.30/1000 chars
    await track_ai_usage(
        service="elevenlabs",
        usage_type="tts",
        characters=response.character_count,
        cost_usd=elevenlabs_cost,
        description=f"TTS: {voice_name} ({input.model_id})"
    )
    
    # Return audio as streaming response
    headers = {
        "Content-Disposition": f"attachment; filename=speech_{uuid.uuid4().hex[:8]}.mp3",
        "X-Character-Count": str(response.character_count),
        "X-Request-ID": response.request_id or "",
        "X-Enhancement-Mode": input.enhancement_mode,
        "X-History-ID": history_item["id"]  # Include history ID in response
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
    Get cumulative usage statistics for AI services (Claude + ElevenLabs).
    Data persists in Google Sheets across server restarts.
    Shows actual API cost and client price (×20 markup).
    """
    # Get persistent totals from Google Sheets
    totals = {"claude_requests": 0, "claude_input_tokens": 0, "claude_output_tokens": 0,
              "claude_cost_usd": 0.0, "elevenlabs_requests": 0, "elevenlabs_characters": 0,
              "elevenlabs_cost_usd": 0.0, "total_cost_usd": 0.0}
    
    if sheets_service and sheets_service.is_available:
        totals = await sheets_service.get_usage_totals()
    
    total_cost = round(totals["total_cost_usd"], 6)
    total_cost_x20 = round(totals["total_cost_usd"] * 20, 4)
    
    return UsageStatsResponse(
        total_requests=totals["claude_requests"] + totals["elevenlabs_requests"],
        total_input_tokens=totals["claude_input_tokens"],
        total_output_tokens=totals["claude_output_tokens"],
        total_cost_usd=total_cost,
        total_cost_usd_x20=total_cost_x20,
        total_cost_usd_formatted=f"${total_cost:.6f}",
        total_cost_usd_x20_formatted=f"${total_cost_x20:.4f}",
        claude_requests=totals["claude_requests"],
        claude_input_tokens=totals["claude_input_tokens"],
        claude_output_tokens=totals["claude_output_tokens"],
        claude_cost_usd=round(totals["claude_cost_usd"], 6),
        elevenlabs_requests=totals["elevenlabs_requests"],
        elevenlabs_characters=totals["elevenlabs_characters"],
        elevenlabs_cost_usd=round(totals["elevenlabs_cost_usd"], 6)
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
# ElevenLabs Subscription Endpoint
# ============================================================================

@app.get("/usage/subscription")
async def get_elevenlabs_subscription():
    """Get ElevenLabs subscription character usage (quota remaining)"""
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
