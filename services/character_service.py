"""
Character Service
Manages character profiles for consistent TTS enhancement
"""

import json
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime


# Available moods for scene state
AVAILABLE_MOODS = [
    "neutral",
    "happy",
    "sad", 
    "angry",
    "anxious",
    "excited",
    "tired",
    "scared",
    "calm",
    "flirty",
    "annoyed",
    "hopeful",
    "defeated"
]

# Energy levels
ENERGY_LEVELS = ["low", "medium", "high"]


@dataclass
class CharacterProfile:
    """Fixed character profile"""
    id: str
    name: str
    age: Optional[int] = None
    background: Optional[str] = None  # "NYC nurse", "retired marine", etc.
    personality: Optional[str] = None  # "introverted, sarcastic, warm"
    speaking_style: Optional[str] = None  # "formal", "uses filler words", "curses"
    voice_direction: Optional[str] = None  # "think tired nurse who's seen too much"
    quirks: Optional[str] = None  # "clears throat when nervous", "laughs at own jokes"
    created_at: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


@dataclass 
class SceneState:
    """Variable scene state for a request"""
    mood: str = "neutral"
    energy: str = "medium"
    context: Optional[str] = None  # "just got bad news", "hiding a secret"


class CharacterService:
    """
    Service for managing character profiles
    Stores characters in a JSON file
    """
    
    def __init__(self, storage_path: str = None):
        """Initialize character service"""
        if storage_path:
            self.storage_path = Path(storage_path)
        else:
            self.storage_path = Path(__file__).parent.parent / "data" / "characters.json"
        
        # Ensure directory exists
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing characters
        self.characters: Dict[str, CharacterProfile] = {}
        self._load()
    
    def _load(self):
        """Load characters from storage"""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    for char_data in data.get("characters", []):
                        char = CharacterProfile(**char_data)
                        self.characters[char.id] = char
                print(f"✓ Loaded {len(self.characters)} character(s)")
            except Exception as e:
                print(f"⚠ Failed to load characters: {e}")
    
    def _save(self):
        """Save characters to storage"""
        try:
            data = {
                "characters": [asdict(c) for c in self.characters.values()]
            }
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"⚠ Failed to save characters: {e}")
    
    def create(self, 
               name: str,
               age: int = None,
               background: str = None,
               personality: str = None,
               speaking_style: str = None,
               voice_direction: str = None,
               quirks: str = None) -> CharacterProfile:
        """Create a new character"""
        char = CharacterProfile(
            id=str(uuid.uuid4())[:8],
            name=name,
            age=age,
            background=background,
            personality=personality,
            speaking_style=speaking_style,
            voice_direction=voice_direction,
            quirks=quirks
        )
        self.characters[char.id] = char
        self._save()
        return char
    
    def get(self, character_id: str) -> Optional[CharacterProfile]:
        """Get a character by ID"""
        return self.characters.get(character_id)
    
    def get_by_name(self, name: str) -> Optional[CharacterProfile]:
        """Get a character by name"""
        for char in self.characters.values():
            if char.name.lower() == name.lower():
                return char
        return None
    
    def list_all(self) -> List[CharacterProfile]:
        """List all characters"""
        return list(self.characters.values())
    
    def update(self, character_id: str, **updates) -> Optional[CharacterProfile]:
        """Update a character"""
        char = self.characters.get(character_id)
        if not char:
            return None
        
        for key, value in updates.items():
            if hasattr(char, key) and key not in ('id', 'created_at'):
                setattr(char, key, value)
        
        self._save()
        return char
    
    def delete(self, character_id: str) -> bool:
        """Delete a character"""
        if character_id in self.characters:
            del self.characters[character_id]
            self._save()
            return True
        return False
    
    def get_prompt_section(self, character: CharacterProfile, scene: SceneState) -> str:
        """
        Build the prompt section for a character + scene state
        This gets injected into the enhancement prompt
        """
        parts = []
        
        # Character info
        parts.append(f"## Character: {character.name}")
        
        if character.age:
            parts.append(f"- Age: {character.age}")
        
        if character.background:
            parts.append(f"- Background: {character.background}")
        
        if character.personality:
            parts.append(f"- Personality: {character.personality}")
        
        if character.speaking_style:
            parts.append(f"- Speaking style: {character.speaking_style}")
        
        if character.voice_direction:
            parts.append(f"- Voice direction: {character.voice_direction}")
        
        if character.quirks:
            parts.append(f"- Quirks: {character.quirks}")
        
        # Scene state
        parts.append(f"\n## Current Scene State")
        parts.append(f"- Mood: {scene.mood}")
        parts.append(f"- Energy level: {scene.energy}")
        
        if scene.context:
            parts.append(f"- What's happening: {scene.context}")
        
        parts.append("\nEnhance the text to match this character's voice and current emotional state.")
        
        return "\n".join(parts)
