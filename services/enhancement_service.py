"""
AI Enhancement Service using Claude 3.5 Sonnet
Adds contextual audio tags to text for ElevenLabs V3
"""

import os
import re
from typing import Optional, List
from dataclasses import dataclass
from enum import Enum


class IntensityLevel(Enum):
    MINIMAL = 1
    LIGHT = 2
    MEDIUM = 3
    HEAVY = 4
    MAXIMUM = 5


class Genre(Enum):
    DRAMA = "drama"
    COMEDY = "comedy"
    THRILLER = "thriller"
    ROMANCE = "romance"
    HORROR = "horror"
    ACTION = "action"
    DOCUMENTARY = "documentary"
    PODCAST = "podcast"


@dataclass
class EnhancementResult:
    """Result from enhancement"""
    original_text: str
    enhanced_text: str
    tags_used: List[str]
    confidence_score: float = 1.0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class UsageStats:
    """Cumulative usage statistics"""
    total_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    
    def add_request(self, input_tokens: int, output_tokens: int):
        """Add a request to the stats"""
        self.total_requests += 1
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        # Claude 3.5 Sonnet pricing: $3/M input, $15/M output
        input_cost = (input_tokens / 1_000_000) * 3.0
        output_cost = (output_tokens / 1_000_000) * 15.0
        self.total_cost_usd += input_cost + output_cost
        return input_cost + output_cost


# Global usage tracker (resets on server restart)
usage_stats = UsageStats()


# System prompt for Claude - optimized for emotional understanding
ENHANCEMENT_SYSTEM_PROMPT = """You are an expert dialogue coach who adds audio performance tags to text for text-to-speech synthesis.

Your job is to analyze text and add [audio tags] that will make the speech sound natural and emotionally authentic.

## Available Tags

**Emotions:** [happy], [sad], [angry], [excited], [fearful], [disgusted], [surprised], [calm], [serious], [worried], [relieved], [frustrated], [hopeful], [disappointed], [nervous], [confident], [nostalgic], [sarcastic], [bitter], [tender]

**Non-verbal sounds:** [sighs], [laughs], [chuckles], [giggles], [gasps], [groans], [scoffs], [sniffles], [clears throat], [coughs], [yawns], [exhales], [inhales sharply], [stammers], [gulps]

**Delivery style:** [whispers], [shouts], [mutters], [mumbles], [softly], [firmly], [gently], [harshly], [warmly], [coldly], [hesitantly], [eagerly], [reluctantly], [sarcastically]

**Pacing:** [pause], [long pause], [beat], [slowly], [quickly], [trailing off...]

## Rules

1. Read between the lines - understand subtext and unspoken emotions
2. Place tags BEFORE the words they affect
3. Don't over-tag - be selective and purposeful
4. Match the emotional journey of the text
5. Consider what a skilled voice actor would naturally do
6. Non-verbal sounds go where they'd naturally occur
7. Return ONLY the enhanced text, nothing else - no explanations, no quotes around it

## Intensity Guide

- Intensity 1: Minimal tags, only essential emotions (1 tag per 50+ words)
- Intensity 2: Light enhancement (1 tag per 30-50 words)
- Intensity 3: Balanced enhancement (1 tag per 15-30 words)  
- Intensity 4: Expressive enhancement (1 tag per 10-15 words)
- Intensity 5: Maximum expression (tags on most emotional beats)"""


def get_user_prompt(text: str, intensity: int, genre: str, character_prompt: str = None, mood: str = None) -> str:
    """Build the user prompt for enhancement"""
    
    genre_hints = {
        "drama": "Focus on emotional depth, pauses, and subtle delivery changes.",
        "comedy": "Add timing beats, chuckles, and playful delivery tags.",
        "thriller": "Emphasize tension, whispers, nervous sounds, and sharp intakes of breath.",
        "romance": "Use tender, soft, and warm delivery. Add sighs and gentle pauses.",
        "horror": "Focus on fear, gasps, trembling voice, and unsettling pauses.",
        "action": "Keep it punchy. Short pauses, urgent delivery, heavy breathing.",
        "documentary": "Minimal tags. Calm, serious, measured delivery.",
        "podcast": "Conversational. Natural laughs, thinking pauses, casual delivery."
    }
    
    hint = genre_hints.get(genre, genre_hints["drama"])
    
    parts = [f"Enhance this text with audio tags.\n"]
    
    # Add character info if provided
    if character_prompt:
        parts.append(character_prompt)
        parts.append("")
    elif mood and mood != "neutral":
        # Just mood without full character
        parts.append(f"Current mood: {mood}")
        parts.append("")
    
    parts.append(f"Genre: {genre}")
    parts.append(f"Style hint: {hint}")
    parts.append(f"Intensity: {intensity}/5")
    parts.append("")
    parts.append(f"Text to enhance:\n{text}")
    parts.append("")
    parts.append("Return ONLY the enhanced text with [tags] added:")
    
    return "\n".join(parts)


class EnhancementService:
    """
    Enhancement service using Claude 3.5 Sonnet
    """
    
    def __init__(self, config_path: str = None):
        """Initialize the enhancement service"""
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.client = None
        self.config_path = config_path
        
        # For backwards compatibility
        self.system_config = {}
        self.character_profiles = {}
        
        if self.api_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=self.api_key)
                print("✓ Claude enhancement service initialized")
            except Exception as e:
                print(f"⚠ Failed to initialize Claude: {e}")
        else:
            print("⚠ ANTHROPIC_API_KEY not set - AI enhancement unavailable")
    
    @property
    def is_available(self) -> bool:
        """Check if enhancement service is available"""
        return self.client is not None
    
    def enhance(self, text: str, intensity: int = 3, genre: str = "drama", 
                character_prompt: str = None, mood: str = None) -> EnhancementResult:
        """
        Enhance text with audio tags using Claude 3.5 Sonnet
        
        Args:
            text: Text to enhance
            intensity: 1-5, how many tags to add
            genre: Content genre for style hints
            character_prompt: Optional character context from CharacterService
            mood: Optional mood override (if no character)
            
        Returns:
            EnhancementResult with original and enhanced text
        """
        if not self.client:
            return EnhancementResult(
                original_text=text,
                enhanced_text=text,
                tags_used=[],
                confidence_score=0.0
            )
        
        try:
            # Call Claude 3.5 Sonnet
            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                messages=[
                    {
                        "role": "user",
                        "content": get_user_prompt(text, intensity, genre, character_prompt, mood)
                    }
                ],
                system=ENHANCEMENT_SYSTEM_PROMPT
            )
            
            enhanced_text = message.content[0].text.strip()
            
            # Extract token usage from response
            input_tokens = message.usage.input_tokens
            output_tokens = message.usage.output_tokens
            
            # Track usage and calculate cost
            request_cost = usage_stats.add_request(input_tokens, output_tokens)
            
            # Clean up any extra quotes or formatting Claude might add
            if enhanced_text.startswith('"') and enhanced_text.endswith('"'):
                enhanced_text = enhanced_text[1:-1]
            if enhanced_text.startswith("```") and enhanced_text.endswith("```"):
                enhanced_text = enhanced_text[3:-3].strip()
            
            # Extract tags used
            tags_used = list(set(re.findall(r'\[([^\]]+)\]', enhanced_text)))
            
            return EnhancementResult(
                original_text=text,
                enhanced_text=enhanced_text,
                tags_used=tags_used,
                confidence_score=1.0,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=request_cost
            )
            
        except Exception as e:
            print(f"Enhancement error: {e}")
            return EnhancementResult(
                original_text=text,
                enhanced_text=text,
                tags_used=[],
                confidence_score=0.0
            )
    
    def enhance_simple(self, text: str, genre: str = "drama", intensity: int = 3) -> str:
        """Simple enhancement - returns just the enhanced text"""
        result = self.enhance(text, intensity, genre)
        return result.enhanced_text


# For backwards compatibility
def enhance_dialogue(text: str, genre: str = "drama", intensity: int = 3) -> str:
    """Quick enhancement function"""
    service = EnhancementService()
    return service.enhance_simple(text, genre, intensity)
