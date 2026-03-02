# TTS Platform

A Text-to-Speech platform with ElevenLabs integration and smart audio tag enhancement.

## Features

- **ElevenLabs Integration**: Full TTS API support with Eleven V3 model
- **Multi-Speaker Dialogue**: Up to 10 unique voices per request
- **Smart Enhancement**: Context-aware audio tag insertion using LLM
- **Audio Tags**: Native support for emotions, non-verbals, and pacing
- **Simple Dashboard**: Clean interface mimicking ElevenLabs' UI

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and add your ELEVENLABS_API_KEY
```

### 3. Run Server

```bash
python main.py
# or
uvicorn main:app --reload
```

### 4. Open Dashboard

Navigate to `http://localhost:8000` in your browser.

## API Endpoints

### Text-to-Speech

```bash
POST /tts
{
  "text": "[sighs] I never thought it would come to this.",
  "voice_id": "your-voice-id",
  "model_id": "eleven_v3",
  "stability": 0.5,
  "enhance": true,
  "enhance_intensity": 3,
  "enhance_genre": "drama"
}
```

### Multi-Speaker Dialogue

```bash
POST /dialogue
{
  "lines": [
    {"text": "Hello there!", "voice_id": "voice-1"},
    {"text": "Hi! How are you?", "voice_id": "voice-2"}
  ],
  "model_id": "eleven_v3"
}
```

### Text Enhancement

```bash
POST /enhance
{
  "text": "I thought you loved me. After everything we've been through.",
  "intensity": 4,
  "genre": "drama"
}
```

### Get Voices

```bash
GET /voices
GET /voices?search=sarah
GET /voices/{voice_id}
```

### Audio Tags Tutorial

```bash
GET /tutorial/audio-tags
GET /tutorial/audio-tags/quick-reference
```

## Audio Tags Reference

### Emotions
`[happy]` `[sad]` `[angry]` `[excited]` `[fearful]` `[disgusted]` `[surprised]` `[calm]` `[serious]`

### Non-Verbal
`[sighs]` `[laughs]` `[chuckles]` `[gasps]` `[clears throat]` `[sniffles]` `[groans]` `[yawns]`

### Delivery
`[whispers]` `[shouts]` `[monotone]` `[sarcastic]`

### Pacing
`[pause]` `[long pause]` `[beat]` `[slowly]` `[quickly]`

## Enhancement System

The platform includes a sophisticated enhancement system that:

1. **Analyzes** text for emotional content and structure
2. **Plans** optimal tag placement based on genre/style
3. **Enhances** by inserting appropriate audio tags
4. **Refines** output for natural delivery

### Intensity Levels

| Level | Description |
|-------|-------------|
| 1 | Minimal - 1 tag per 100 words |
| 2 | Light - 2-3 tags per 100 words |
| 3 | Medium - 4-5 tags per 100 words |
| 4 | Heavy - 6-8 tags per 100 words |
| 5 | Maximum - 10+ tags per 100 words |

### Supported Genres

- Drama, Comedy, Thriller, Romance
- Horror, Action, Documentary, Podcast

## Project Structure

```
├── main.py                 # FastAPI application
├── requirements.txt        # Python dependencies
├── .env.example           # Environment template
├── services/
│   ├── elevenlabs_service.py   # ElevenLabs API client
│   └── enhancement_service.py  # LLM enhancement logic
├── config/
│   ├── enhancement-system.json    # System config
│   ├── enhancement-prompts.json   # LLM prompts
│   ├── character-profiles.json    # Character archetypes
│   └── voice-capabilities.json    # Voice tag ratings
├── docs/
│   ├── audio-tags-tutorial.json   # Structured tutorial
│   └── audio-tags-tutorial.md     # Markdown tutorial
└── static/
    └── index.html          # Dashboard UI
```

## Configuration

### voice-capabilities.json

Define which audio tags work best with specific voices:

```json
{
  "voice_id": "example_voice",
  "tag_ratings": {
    "whisper": 5,
    "excited": 4,
    "angry": 2
  }
}
```

### character-profiles.json

Create character archetypes for consistent enhancement:

```json
{
  "nervous_character": {
    "preferred_tags": ["nervous", "hesitant", "stammers"],
    "avoided_tags": ["confident", "booming"]
  }
}
```

## License

MIT
