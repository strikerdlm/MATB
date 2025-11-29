"""OpenAI TTS Voice Generator for ATC-style communications.

This module provides text-to-speech generation using OpenAI's gpt-4o-mini-tts model
with Air Traffic Controller voice characteristics following ICAO/FAA radio
communication standards.

Features:
- ATC-style voice with proper accent, tone, and intonation
- Configurable voice parameters (speed, emotion, accent)
- Support for multiple languages
- Integration with OpenMATB communications plugin
- Spoken instructions for scenario briefings

Usage:
    from tools.voice_generator import ATCVoiceGenerator
    
    generator = ATCVoiceGenerator()
    generator.generate_communication("November One Two Three, contact tower 118.5")

Implementation Credit: Dr Diego Malpica, Aerospace Medicine
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Final, Literal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
SOUNDS_DIR: Final[Path] = PROJECT_ROOT / "includes" / "sounds"
GENERATED_VOICES_DIR: Final[Path] = SOUNDS_DIR / "generated"
VOICE_CACHE_DIR: Final[Path] = PROJECT_ROOT / ".voice_cache"
ENV_FILE: Final[Path] = PROJECT_ROOT / ".env"

# OpenAI TTS Available Voices
AVAILABLE_VOICES: Final[tuple[str, ...]] = (
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "nova",
    "onyx",
    "sage",
    "shimmer",
    "verse",
)

# Voice descriptions for UI selection
VOICE_DESCRIPTIONS: Final[dict[str, str]] = {
    "alloy": "Neutral, balanced voice - good for general communications",
    "ash": "Warm and conversational - suitable for friendly briefings",
    "ballad": "Expressive and dramatic - good for alerts and warnings",
    "coral": "Clear and professional - excellent for ATC communications",
    "echo": "Authoritative and commanding - ideal for military scenarios",
    "fable": "Engaging storyteller - good for instructions",
    "nova": "Energetic and dynamic - suitable for urgent communications",
    "onyx": "Deep and resonant - good for male ATC voice",
    "sage": "Calm and measured - excellent for routine communications",
    "shimmer": "Bright and clear - good for female ATC voice",
    "verse": "Versatile and adaptable - general purpose",
}

# Recommended voices for different use cases
RECOMMENDED_VOICES: Final[dict[str, str]] = {
    "atc_male": "onyx",
    "atc_female": "shimmer",
    "military_male": "echo",
    "military_female": "coral",
    "instructions_male": "sage",
    "instructions_female": "nova",
    "alerts": "ballad",
    "routine": "alloy",
}

# Audio formats supported
AUDIO_FORMATS: Final[tuple[str, ...]] = ("mp3", "opus", "aac", "flac", "wav", "pcm")

# Default ATC instruction template following ICAO standards
ATC_INSTRUCTION_TEMPLATE: Final[str] = """You are a professional Air Traffic Controller.

Voice Characteristics:
- Accent: Clear, neutral international aviation English (ICAO standard)
- Emotional range: Calm, professional, authoritative but not aggressive
- Intonation: Measured, with slight emphasis on key words (callsigns, frequencies, altitudes)
- Speed: Moderate pace (~140-160 words per minute), slightly slower for critical information
- Tone: Professional, confident, reassuring

Radio Communication Standards (ICAO/FAA):
- Use standard aviation phraseology
- Pronounce numbers clearly (niner for 9, tree for 3, fife for 5)
- Pause briefly between key elements
- Maintain consistent rhythm and cadence
- End transmissions with clear finality

Style Guidelines:
- No emotional extremes or dramatic pauses
- Clear enunciation of all letters and numbers
- Consistent volume throughout
- Professional demeanor at all times
"""

# Spanish ATC instruction template
ATC_INSTRUCTION_TEMPLATE_ES: Final[str] = """Eres un Controlador de Tráfico Aéreo profesional.

Características de Voz:
- Acento: Español claro y neutro con terminología aeronáutica internacional
- Rango emocional: Calmado, profesional, autoritario pero no agresivo
- Entonación: Medida, con ligero énfasis en palabras clave (indicativos, frecuencias, altitudes)
- Velocidad: Ritmo moderado (~140-160 palabras por minuto), más lento para información crítica
- Tono: Profesional, confiado, tranquilizador

Estándares de Comunicación por Radio (OACI/FAA):
- Usar fraseología aeronáutica estándar
- Pronunciar números claramente
- Pausar brevemente entre elementos clave
- Mantener ritmo y cadencia consistentes
- Terminar transmisiones con claridad

Directrices de Estilo:
- Sin extremos emocionales ni pausas dramáticas
- Enunciación clara de todas las letras y números
- Volumen consistente
- Comportamiento profesional en todo momento
"""

# Instruction briefing template
BRIEFING_INSTRUCTION_TEMPLATE: Final[str] = """You are a flight instructor giving a pre-flight briefing.

Voice Characteristics:
- Accent: Clear, friendly, professional
- Emotional range: Encouraging, patient, supportive
- Intonation: Engaging, with emphasis on important points
- Speed: Moderate pace, pausing for comprehension
- Tone: Warm, authoritative, instructional

Style Guidelines:
- Speak clearly and at a measured pace
- Emphasize key safety points
- Use encouraging language
- Maintain a supportive, educational tone
"""

BRIEFING_INSTRUCTION_TEMPLATE_ES: Final[str] = """Eres un instructor de vuelo dando una sesión informativa previa al vuelo.

Características de Voz:
- Acento: Español claro, amigable, profesional
- Rango emocional: Alentador, paciente, comprensivo
- Entonación: Atractiva, con énfasis en puntos importantes
- Velocidad: Ritmo moderado, pausando para comprensión
- Tono: Cálido, autoritario, instructivo

Directrices de Estilo:
- Hablar claramente y a un ritmo medido
- Enfatizar puntos clave de seguridad
- Usar lenguaje alentador
- Mantener un tono de apoyo educativo
"""


class VoiceStyle(Enum):
    """Predefined voice styles for different scenarios."""

    ATC_ROUTINE = "atc_routine"
    ATC_URGENT = "atc_urgent"
    ATC_EMERGENCY = "atc_emergency"
    MILITARY_TACTICAL = "military_tactical"
    BRIEFING_CALM = "briefing_calm"
    BRIEFING_URGENT = "briefing_urgent"
    INSTRUCTION_STANDARD = "instruction_standard"
    INSTRUCTION_DETAILED = "instruction_detailed"


@dataclass(frozen=True, slots=True)
class VoicePreset:
    """Voice configuration preset."""

    name: str
    voice: str
    instructions: str
    speed: float = 1.0
    format: str = "mp3"
    language: str = "en"


# Predefined voice presets
VOICE_PRESETS: Final[dict[str, VoicePreset]] = {
    "atc_male_en": VoicePreset(
        name="ATC Male (English)",
        voice="onyx",
        instructions=ATC_INSTRUCTION_TEMPLATE,
        speed=1.0,
        language="en",
    ),
    "atc_female_en": VoicePreset(
        name="ATC Female (English)",
        voice="shimmer",
        instructions=ATC_INSTRUCTION_TEMPLATE,
        speed=1.0,
        language="en",
    ),
    "atc_male_es": VoicePreset(
        name="ATC Male (Spanish)",
        voice="onyx",
        instructions=ATC_INSTRUCTION_TEMPLATE_ES,
        speed=0.95,
        language="es",
    ),
    "atc_female_es": VoicePreset(
        name="ATC Female (Spanish)",
        voice="shimmer",
        instructions=ATC_INSTRUCTION_TEMPLATE_ES,
        speed=0.95,
        language="es",
    ),
    "military_tactical": VoicePreset(
        name="Military Tactical",
        voice="echo",
        instructions=ATC_INSTRUCTION_TEMPLATE + "\nAdditional: Use concise, tactical language. Be direct and commanding.",
        speed=1.1,
        language="en",
    ),
    "briefing_instructor_en": VoicePreset(
        name="Briefing Instructor (English)",
        voice="sage",
        instructions=BRIEFING_INSTRUCTION_TEMPLATE,
        speed=0.9,
        language="en",
    ),
    "briefing_instructor_es": VoicePreset(
        name="Briefing Instructor (Spanish)",
        voice="sage",
        instructions=BRIEFING_INSTRUCTION_TEMPLATE_ES,
        speed=0.85,
        language="es",
    ),
    "urgent_alert": VoicePreset(
        name="Urgent Alert",
        voice="ballad",
        instructions=ATC_INSTRUCTION_TEMPLATE + "\nAdditional: Speak with urgency but remain professional. Emphasize critical information.",
        speed=1.15,
        language="en",
    ),
}


@dataclass(slots=True)
class VoiceConfig:
    """Configuration for voice generation.
    
    Attributes:
        voice: OpenAI voice identifier (e.g., 'coral', 'onyx', 'shimmer')
        speed: Speech speed multiplier (0.25 to 4.0, default 1.0)
        format: Audio output format (mp3, wav, etc.)
        instructions: Custom instructions for voice style
        accent: Accent preference (e.g., 'american', 'british', 'neutral')
        emotional_range: Emotional intensity ('calm', 'moderate', 'intense')
        intonation: Intonation style ('flat', 'measured', 'expressive')
        language: Target language code (e.g., 'en', 'es', 'fr')
    """

    voice: str = "coral"
    speed: float = 1.0
    format: str = "mp3"
    instructions: str = ""
    accent: str = "neutral"
    emotional_range: str = "moderate"
    intonation: str = "measured"
    language: str = "en"

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.voice not in AVAILABLE_VOICES:
            raise ValueError(f"Invalid voice '{self.voice}'. Available: {AVAILABLE_VOICES}")
        if not 0.25 <= self.speed <= 4.0:
            raise ValueError(f"Speed must be between 0.25 and 4.0, got {self.speed}")
        if self.format not in AUDIO_FORMATS:
            raise ValueError(f"Invalid format '{self.format}'. Available: {AUDIO_FORMATS}")

    def build_instructions(self, base_template: str = "") -> str:
        """Build complete instructions string from configuration.
        
        Args:
            base_template: Base instruction template to use
            
        Returns:
            Complete instructions string for TTS API
        """
        parts: list[str] = []

        # Use provided base template or default ATC template
        if base_template:
            parts.append(base_template)
        elif self.language == "es":
            parts.append(ATC_INSTRUCTION_TEMPLATE_ES)
        else:
            parts.append(ATC_INSTRUCTION_TEMPLATE)

        # Add custom instructions if provided
        if self.instructions:
            parts.append(f"\nAdditional Instructions:\n{self.instructions}")

        # Add accent specification
        if self.accent != "neutral":
            parts.append(f"\nAccent: Speak with a {self.accent} accent while maintaining clarity.")

        # Add emotional range
        if self.emotional_range == "calm":
            parts.append("\nEmotional Range: Maintain an extremely calm and steady voice throughout.")
        elif self.emotional_range == "intense":
            parts.append("\nEmotional Range: Add appropriate urgency and intensity while remaining professional.")

        # Add intonation style
        if self.intonation == "flat":
            parts.append("\nIntonation: Keep a relatively flat, monotone delivery.")
        elif self.intonation == "expressive":
            parts.append("\nIntonation: Use more expressive intonation to emphasize key points.")

        return "\n".join(parts)


@dataclass(slots=True)
class GenerationResult:
    """Result of a voice generation operation.
    
    Attributes:
        success: Whether generation was successful
        file_path: Path to the generated audio file (if successful)
        error_message: Error message (if failed)
        text: Original text that was converted
        duration_ms: Estimated duration in milliseconds
        cache_hit: Whether result was from cache
        generation_time_ms: Time taken to generate (if not cached)
    """

    success: bool
    file_path: Path | None = None
    error_message: str = ""
    text: str = ""
    duration_ms: int = 0
    cache_hit: bool = False
    generation_time_ms: int = 0


def load_api_key() -> str | None:
    """Load OpenAI API key from environment or .env file.
    
    Returns:
        API key string or None if not found
        
    Note:
        Checks in order:
        1. OPENAI_API_KEY environment variable
        2. .env file in project root
    """
    # Check environment variable first
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        return api_key

    # Check .env file
    if ENV_FILE.exists():
        with ENV_FILE.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("OPENAI_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")

    return None


def _compute_cache_key(text: str, config: VoiceConfig) -> str:
    """Compute a cache key for the given text and configuration.
    
    Args:
        text: Text to be converted to speech
        config: Voice configuration
        
    Returns:
        MD5 hash string for cache key
    """
    cache_data = f"{text}|{config.voice}|{config.speed}|{config.instructions}|{config.language}"
    return hashlib.md5(cache_data.encode()).hexdigest()


class ATCVoiceGenerator:
    """Generate ATC-style voice communications using OpenAI TTS.
    
    This class provides methods to generate realistic Air Traffic Controller
    voice communications following ICAO/FAA radio communication standards.
    
    Attributes:
        config: Voice configuration settings
        api_key: OpenAI API key (loaded from environment)
        use_cache: Whether to cache generated audio files
        
    Example:
        >>> generator = ATCVoiceGenerator()
        >>> result = generator.generate_communication(
        ...     "November One Two Three, contact tower 118.5"
        ... )
        >>> if result.success:
        ...     print(f"Audio saved to: {result.file_path}")
    """

    def __init__(
        self,
        config: VoiceConfig | None = None,
        api_key: str | None = None,
        use_cache: bool = True,
    ) -> None:
        """Initialize the ATC Voice Generator.
        
        Args:
            config: Voice configuration (uses defaults if None)
            api_key: OpenAI API key (loads from env if None)
            use_cache: Whether to cache generated audio files
            
        Raises:
            ValueError: If API key is not found and not provided
        """
        self.config = config or VoiceConfig()
        self.api_key = api_key or load_api_key()
        self.use_cache = use_cache
        self._client: object | None = None  # Lazy-loaded OpenAI client

        # Ensure directories exist
        GENERATED_VOICES_DIR.mkdir(parents=True, exist_ok=True)
        if use_cache:
            VOICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _get_client(self) -> object:
        """Get or create the OpenAI client.
        
        Returns:
            OpenAI client instance
            
        Raises:
            ImportError: If openai package is not installed
            ValueError: If API key is not available
        """
        if self._client is not None:
            return self._client

        if not self.api_key:
            raise ValueError(
                "OpenAI API key not found. Set OPENAI_API_KEY environment variable "
                "or add it to .env file in project root."
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError(
                "OpenAI package not installed. Run: pip install openai"
            ) from exc

        self._client = OpenAI(api_key=self.api_key)
        return self._client

    def generate_communication(
        self,
        text: str,
        output_path: Path | str | None = None,
        config_override: VoiceConfig | None = None,
    ) -> GenerationResult:
        """Generate ATC-style voice communication.
        
        Args:
            text: Text to convert to speech
            output_path: Custom output path (auto-generated if None)
            config_override: Override default configuration
            
        Returns:
            GenerationResult with success status and file path
            
        Raises:
            ValueError: If text is empty
        """
        import time

        if not text or not text.strip():
            return GenerationResult(
                success=False,
                error_message="Text cannot be empty",
                text=text,
            )

        config = config_override or self.config
        start_time = time.monotonic()

        # Check cache first
        if self.use_cache:
            cache_key = _compute_cache_key(text, config)
            cache_path = VOICE_CACHE_DIR / f"{cache_key}.{config.format}"
            if cache_path.exists():
                return GenerationResult(
                    success=True,
                    file_path=cache_path,
                    text=text,
                    cache_hit=True,
                    duration_ms=self._estimate_duration(text),
                )

        # Generate output path if not provided
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_text = re.sub(r'[^\w\s-]', '', text[:30]).strip().replace(' ', '_')
            filename = f"atc_{timestamp}_{safe_text}.{config.format}"
            output_path = GENERATED_VOICES_DIR / filename
        else:
            output_path = Path(output_path)

        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            client = self._get_client()
            instructions = config.build_instructions()

            # Generate speech using OpenAI API
            with client.audio.speech.with_streaming_response.create(
                model="gpt-4o-mini-tts",
                voice=config.voice,
                input=text,
                instructions=instructions,
                response_format=config.format,
                speed=config.speed,
            ) as response:
                response.stream_to_file(str(output_path))

            # Copy to cache if enabled
            if self.use_cache:
                cache_key = _compute_cache_key(text, config)
                cache_path = VOICE_CACHE_DIR / f"{cache_key}.{config.format}"
                import shutil
                shutil.copy2(output_path, cache_path)

            generation_time = int((time.monotonic() - start_time) * 1000)

            return GenerationResult(
                success=True,
                file_path=output_path,
                text=text,
                duration_ms=self._estimate_duration(text),
                cache_hit=False,
                generation_time_ms=generation_time,
            )

        except ImportError as exc:
            return GenerationResult(
                success=False,
                error_message=f"OpenAI package not installed: {exc}",
                text=text,
            )
        except ValueError as exc:
            return GenerationResult(
                success=False,
                error_message=f"Configuration error: {exc}",
                text=text,
            )
        except Exception as exc:  # noqa: BLE001 - Catch all for API errors
            return GenerationResult(
                success=False,
                error_message=f"Generation failed: {exc}",
                text=text,
            )

    def generate_phonetic_alphabet(
        self,
        output_dir: Path | str | None = None,
    ) -> dict[str, GenerationResult]:
        """Generate NATO phonetic alphabet audio files.
        
        Args:
            output_dir: Directory for output files (uses default if None)
            
        Returns:
            Dictionary mapping letters/numbers to GenerationResult
        """
        phonetic_alphabet = {
            "a": "Alpha", "b": "Bravo", "c": "Charlie", "d": "Delta",
            "e": "Echo", "f": "Foxtrot", "g": "Golf", "h": "Hotel",
            "i": "India", "j": "Juliet", "k": "Kilo", "l": "Lima",
            "m": "Mike", "n": "November", "o": "Oscar", "p": "Papa",
            "q": "Quebec", "r": "Romeo", "s": "Sierra", "t": "Tango",
            "u": "Uniform", "v": "Victor", "w": "Whiskey", "x": "X-ray",
            "y": "Yankee", "z": "Zulu",
            "0": "Zero", "1": "One", "2": "Two", "3": "Tree",
            "4": "Four", "5": "Fife", "6": "Six", "7": "Seven",
            "8": "Eight", "9": "Niner",
            "point": "Point", "decimal": "Decimal",
        }

        output_dir = Path(output_dir) if output_dir else GENERATED_VOICES_DIR / "phonetic"
        output_dir.mkdir(parents=True, exist_ok=True)

        results: dict[str, GenerationResult] = {}
        for key, word in phonetic_alphabet.items():
            output_path = output_dir / f"{key}.{self.config.format}"
            results[key] = self.generate_communication(word, output_path)

        return results

    def generate_common_phrases(
        self,
        output_dir: Path | str | None = None,
    ) -> dict[str, GenerationResult]:
        """Generate common ATC phrases.
        
        Args:
            output_dir: Directory for output files (uses default if None)
            
        Returns:
            Dictionary mapping phrase keys to GenerationResult
        """
        common_phrases = {
            "radio": "Radio",
            "frequency": "Frequency",
            "contact": "Contact",
            "tower": "Tower",
            "approach": "Approach",
            "departure": "Departure",
            "ground": "Ground",
            "center": "Center",
            "roger": "Roger",
            "wilco": "Wilco",
            "affirm": "Affirm",
            "negative": "Negative",
            "standby": "Standby",
            "say_again": "Say again",
            "cleared": "Cleared",
            "hold_short": "Hold short",
            "line_up": "Line up and wait",
            "takeoff": "Cleared for takeoff",
            "landing": "Cleared to land",
            "go_around": "Go around",
            "mayday": "Mayday, Mayday, Mayday",
            "pan_pan": "Pan Pan, Pan Pan, Pan Pan",
            "nav_1": "NAV One",
            "nav_2": "NAV Two",
            "com_1": "COM One",
            "com_2": "COM Two",
        }

        output_dir = Path(output_dir) if output_dir else GENERATED_VOICES_DIR / "phrases"
        output_dir.mkdir(parents=True, exist_ok=True)

        results: dict[str, GenerationResult] = {}
        for key, phrase in common_phrases.items():
            output_path = output_dir / f"{key}.{self.config.format}"
            results[key] = self.generate_communication(phrase, output_path)

        return results

    def generate_instruction_audio(
        self,
        instruction_text: str,
        scenario_name: str,
        language: str = "en",
        output_dir: Path | str | None = None,
        config_override: VoiceConfig | None = None,
    ) -> GenerationResult:
        """Generate spoken instructions for a scenario.
        
        Args:
            instruction_text: Full instruction text to speak
            scenario_name: Name of the scenario (for filename)
            language: Language code ('en' or 'es')
            output_dir: Output directory (uses default if None)
            config_override: Optional config to override self.config. If None,
                uses self.config (which respects the user's preset selection).
            
        Returns:
            GenerationResult with audio file path
        """
        # Use provided config override, or fall back to instance config
        config = config_override or self.config

        output_dir = Path(output_dir) if output_dir else GENERATED_VOICES_DIR / "instructions"
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"instruction_{scenario_name}_{language}_{timestamp}.{config.format}"
        output_path = output_dir / filename

        return self.generate_communication(instruction_text, output_path, config)

    def generate_callsign_audio(
        self,
        callsign: str,
        output_dir: Path | str | None = None,
    ) -> GenerationResult:
        """Generate audio for a specific callsign.
        
        Args:
            callsign: Aircraft callsign (e.g., 'ABC123')
            output_dir: Output directory (uses default if None)
            
        Returns:
            GenerationResult with audio file path
        """
        # Convert callsign to phonetic pronunciation
        phonetic_callsign = self._callsign_to_phonetic(callsign)

        output_dir = Path(output_dir) if output_dir else GENERATED_VOICES_DIR / "callsigns"
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / f"{callsign.lower()}.{self.config.format}"
        return self.generate_communication(phonetic_callsign, output_path)

    def generate_frequency_audio(
        self,
        frequency: float,
        output_dir: Path | str | None = None,
    ) -> GenerationResult:
        """Generate audio for a radio frequency.
        
        Args:
            frequency: Radio frequency (e.g., 118.5)
            output_dir: Output directory (uses default if None)
            
        Returns:
            GenerationResult with audio file path
        """
        # Format frequency for pronunciation
        freq_str = f"{frequency:.1f}"
        parts = freq_str.split(".")
        whole = " ".join(self._digit_to_phonetic(d) for d in parts[0])
        decimal = " ".join(self._digit_to_phonetic(d) for d in parts[1])
        phonetic_freq = f"{whole} point {decimal}"

        output_dir = Path(output_dir) if output_dir else GENERATED_VOICES_DIR / "frequencies"
        output_dir.mkdir(parents=True, exist_ok=True)

        freq_filename = freq_str.replace(".", "_")
        output_path = output_dir / f"freq_{freq_filename}.{self.config.format}"
        return self.generate_communication(phonetic_freq, output_path)

    def _callsign_to_phonetic(self, callsign: str) -> str:
        """Convert a callsign to phonetic pronunciation.
        
        Args:
            callsign: Aircraft callsign (e.g., 'ABC123')
            
        Returns:
            Phonetic pronunciation string
        """
        phonetic_map = {
            "A": "Alpha", "B": "Bravo", "C": "Charlie", "D": "Delta",
            "E": "Echo", "F": "Foxtrot", "G": "Golf", "H": "Hotel",
            "I": "India", "J": "Juliet", "K": "Kilo", "L": "Lima",
            "M": "Mike", "N": "November", "O": "Oscar", "P": "Papa",
            "Q": "Quebec", "R": "Romeo", "S": "Sierra", "T": "Tango",
            "U": "Uniform", "V": "Victor", "W": "Whiskey", "X": "X-ray",
            "Y": "Yankee", "Z": "Zulu",
            "0": "Zero", "1": "One", "2": "Two", "3": "Tree",
            "4": "Four", "5": "Fife", "6": "Six", "7": "Seven",
            "8": "Eight", "9": "Niner",
        }

        return " ".join(
            phonetic_map.get(char.upper(), char)
            for char in callsign
        )

    def _digit_to_phonetic(self, digit: str) -> str:
        """Convert a single digit to phonetic pronunciation.
        
        Args:
            digit: Single digit character
            
        Returns:
            Phonetic pronunciation
        """
        digit_map = {
            "0": "Zero", "1": "One", "2": "Two", "3": "Tree",
            "4": "Four", "5": "Fife", "6": "Six", "7": "Seven",
            "8": "Eight", "9": "Niner",
        }
        return digit_map.get(digit, digit)

    def _estimate_duration(self, text: str) -> int:
        """Estimate audio duration in milliseconds.
        
        Args:
            text: Text to estimate duration for
            
        Returns:
            Estimated duration in milliseconds
            
        Note:
            Based on average speaking rate of ~150 words per minute
        """
        word_count = len(text.split())
        # ~150 words per minute = 400ms per word on average
        base_duration = word_count * 400
        # Adjust for speed setting
        adjusted_duration = int(base_duration / self.config.speed)
        return adjusted_duration

    def set_preset(self, preset_name: str) -> None:
        """Apply a predefined voice preset.
        
        Args:
            preset_name: Name of the preset to apply
            
        Raises:
            ValueError: If preset name is not found
        """
        if preset_name not in VOICE_PRESETS:
            raise ValueError(
                f"Unknown preset '{preset_name}'. Available: {list(VOICE_PRESETS.keys())}"
            )

        preset = VOICE_PRESETS[preset_name]
        self.config = VoiceConfig(
            voice=preset.voice,
            speed=preset.speed,
            instructions=preset.instructions,
            language=preset.language,
        )

    def clear_cache(self) -> int:
        """Clear the voice cache directory.
        
        Returns:
            Number of files deleted
        """
        if not VOICE_CACHE_DIR.exists():
            return 0

        count = 0
        for file in VOICE_CACHE_DIR.iterdir():
            if file.is_file():
                file.unlink()
                count += 1
        return count

    def get_cache_size(self) -> tuple[int, int]:
        """Get cache statistics.
        
        Returns:
            Tuple of (file_count, total_size_bytes)
        """
        if not VOICE_CACHE_DIR.exists():
            return 0, 0

        file_count = 0
        total_size = 0
        for file in VOICE_CACHE_DIR.iterdir():
            if file.is_file():
                file_count += 1
                total_size += file.stat().st_size
        return file_count, total_size


def generate_matb_voice_files(
    voice_idiom: str = "english",
    voice_gender: str = "male",
    api_key: str | None = None,
) -> dict[str, GenerationResult]:
    """Generate all voice files needed for MATB communications plugin.
    
    This function generates voice files compatible with the existing
    MATB communications plugin structure.
    
    Args:
        voice_idiom: Language ('english', 'spanish', 'french')
        voice_gender: Gender ('male', 'female')
        api_key: OpenAI API key (uses environment if None)
        
    Returns:
        Dictionary mapping file names to GenerationResult
    """
    # Map idiom to language code
    lang_map = {"english": "en", "spanish": "es", "french": "fr"}
    language = lang_map.get(voice_idiom, "en")

    # Select appropriate voice based on gender
    if voice_gender == "male":
        voice = "onyx" if language == "en" else "echo"
    else:
        voice = "shimmer" if language == "en" else "coral"

    # Select instruction template
    if language == "es":
        instructions = ATC_INSTRUCTION_TEMPLATE_ES
    else:
        instructions = ATC_INSTRUCTION_TEMPLATE

    config = VoiceConfig(
        voice=voice,
        speed=1.0,
        format="wav",  # WAV for compatibility with pyglet
        instructions=instructions,
        language=language,
    )

    generator = ATCVoiceGenerator(config=config, api_key=api_key)

    # Output directory matching MATB structure
    output_dir = SOUNDS_DIR / voice_idiom / voice_gender
    output_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, GenerationResult] = {}

    # Generate phonetic alphabet
    phonetic = generator.generate_phonetic_alphabet(output_dir)
    results.update(phonetic)

    # Generate common phrases
    phrases = generator.generate_common_phrases(output_dir)
    results.update(phrases)

    # Generate empty sound (silence)
    # Note: This should be a short silence file
    empty_path = output_dir / "empty.wav"
    if not empty_path.exists():
        # Generate a very short "silence" placeholder
        results["empty"] = generator.generate_communication(
            "...",  # Short pause
            empty_path,
        )

    return results


# ---------------------------------------------------------------------------
# Streamlit Integration Functions
# ---------------------------------------------------------------------------
def render_voice_config_ui() -> VoiceConfig:
    """Render Streamlit UI for voice configuration.
    
    Returns:
        VoiceConfig based on user selections
        
    Note:
        Must be called within a Streamlit context
    """
    import streamlit as st

    st.subheader("🎙️ Voice Configuration")

    col1, col2 = st.columns(2)

    with col1:
        voice = st.selectbox(
            "Voice",
            options=list(AVAILABLE_VOICES),
            index=AVAILABLE_VOICES.index("coral"),
            help="Select the voice for TTS generation",
        )

        st.caption(VOICE_DESCRIPTIONS.get(voice, ""))

        speed = st.slider(
            "Speed",
            min_value=0.25,
            max_value=2.0,
            value=1.0,
            step=0.05,
            help="Speech speed multiplier",
        )

        audio_format = st.selectbox(
            "Format",
            options=list(AUDIO_FORMATS),
            index=0,
            help="Audio output format",
        )

    with col2:
        accent = st.selectbox(
            "Accent",
            options=["neutral", "american", "british", "international"],
            index=0,
            help="Accent preference",
        )

        emotional_range = st.selectbox(
            "Emotional Range",
            options=["calm", "moderate", "intense"],
            index=1,
            help="Emotional intensity",
        )

        intonation = st.selectbox(
            "Intonation",
            options=["flat", "measured", "expressive"],
            index=1,
            help="Intonation style",
        )

        language = st.selectbox(
            "Language",
            options=["en", "es", "fr"],
            index=0,
            help="Target language",
        )

    custom_instructions = st.text_area(
        "Custom Instructions",
        value="",
        help="Additional instructions for voice style (optional)",
        height=100,
    )

    return VoiceConfig(
        voice=voice,
        speed=speed,
        format=audio_format,
        instructions=custom_instructions,
        accent=accent,
        emotional_range=emotional_range,
        intonation=intonation,
        language=language,
    )


def render_voice_generator_tab() -> None:
    """Render the voice generator tab in Streamlit.
    
    Note:
        Must be called within a Streamlit context
    """
    import streamlit as st

    st.header("🎙️ ATC Voice Generator")
    st.markdown(
        "Generate Air Traffic Controller style voice communications using OpenAI's "
        "gpt-4o-mini-tts model. Voices follow ICAO/FAA radio communication standards."
    )

    # Check for API key
    api_key = load_api_key()
    if not api_key:
        st.error(
            "⚠️ **OpenAI API Key Required**\n\n"
            "Set the `OPENAI_API_KEY` environment variable or add it to a `.env` file "
            "in the project root.\n\n"
            "```\nOPENAI_API_KEY=sk-your-key-here\n```"
        )
        return

    st.success("✅ OpenAI API key found")

    # Voice configuration
    config = render_voice_config_ui()

    st.markdown("---")

    # Generation mode selection
    mode = st.radio(
        "Generation Mode",
        options=[
            "📝 Single Text",
            "📞 Callsign",
            "📻 Frequency",
            "📖 Instruction Script",
            "🔤 Full Phonetic Alphabet",
            "📦 MATB Voice Pack",
        ],
        horizontal=True,
    )

    st.markdown("---")

    generator = ATCVoiceGenerator(config=config, api_key=api_key)

    if mode == "📝 Single Text":
        text = st.text_area(
            "Text to Convert",
            value="November One Two Three, contact tower on 118.5",
            height=100,
        )

        if st.button("🎤 Generate Audio", type="primary"):
            with st.spinner("Generating audio..."):
                result = generator.generate_communication(text)

            if result.success:
                st.success(f"✅ Audio generated: {result.file_path}")
                st.audio(str(result.file_path))
                if result.cache_hit:
                    st.caption("(from cache)")
                else:
                    st.caption(f"Generation time: {result.generation_time_ms}ms")
            else:
                st.error(f"❌ Generation failed: {result.error_message}")

    elif mode == "📞 Callsign":
        callsign = st.text_input("Callsign", value="ABC123")

        if st.button("🎤 Generate Callsign Audio", type="primary"):
            with st.spinner("Generating callsign audio..."):
                result = generator.generate_callsign_audio(callsign)

            if result.success:
                st.success(f"✅ Audio generated: {result.file_path}")
                st.audio(str(result.file_path))
            else:
                st.error(f"❌ Generation failed: {result.error_message}")

    elif mode == "📻 Frequency":
        frequency = st.number_input(
            "Frequency (MHz)",
            min_value=108.0,
            max_value=137.0,
            value=118.5,
            step=0.1,
        )

        if st.button("🎤 Generate Frequency Audio", type="primary"):
            with st.spinner("Generating frequency audio..."):
                result = generator.generate_frequency_audio(frequency)

            if result.success:
                st.success(f"✅ Audio generated: {result.file_path}")
                st.audio(str(result.file_path))
            else:
                st.error(f"❌ Generation failed: {result.error_message}")

    elif mode == "📖 Instruction Script":
        scenario_name = st.text_input("Scenario Name", value="test_scenario")
        instruction_text = st.text_area(
            "Instruction Text",
            value=(
                "Welcome to the Multi-Attribute Task Battery. "
                "In this test, you will perform multiple tasks simultaneously. "
                "Pay attention to the system monitoring gauges on the left. "
                "Use the joystick to keep the cursor centered in the tracking task."
            ),
            height=200,
        )
        language = st.selectbox("Language", options=["en", "es"], index=0)

        if st.button("🎤 Generate Instruction Audio", type="primary"):
            with st.spinner("Generating instruction audio..."):
                result = generator.generate_instruction_audio(
                    instruction_text, scenario_name, language
                )

            if result.success:
                st.success(f"✅ Audio generated: {result.file_path}")
                st.audio(str(result.file_path))
            else:
                st.error(f"❌ Generation failed: {result.error_message}")

    elif mode == "🔤 Full Phonetic Alphabet":
        st.info("This will generate all NATO phonetic alphabet audio files.")

        if st.button("🎤 Generate Phonetic Alphabet", type="primary"):
            with st.spinner("Generating phonetic alphabet (this may take a few minutes)..."):
                results = generator.generate_phonetic_alphabet()

            success_count = sum(1 for r in results.values() if r.success)
            st.success(f"✅ Generated {success_count}/{len(results)} files")

            # Show results in expandable section
            with st.expander("View Results"):
                for key, result in results.items():
                    if result.success:
                        st.write(f"✅ {key}: {result.file_path}")
                    else:
                        st.write(f"❌ {key}: {result.error_message}")

    elif mode == "📦 MATB Voice Pack":
        st.info(
            "Generate a complete voice pack compatible with the MATB communications plugin. "
            "This includes phonetic alphabet, common phrases, and radio terms."
        )

        col1, col2 = st.columns(2)
        with col1:
            voice_idiom = st.selectbox(
                "Voice Idiom",
                options=["english", "spanish", "french"],
                index=0,
            )
        with col2:
            voice_gender = st.selectbox(
                "Voice Gender",
                options=["male", "female"],
                index=0,
            )

        if st.button("🎤 Generate MATB Voice Pack", type="primary"):
            with st.spinner("Generating MATB voice pack (this may take several minutes)..."):
                results = generate_matb_voice_files(
                    voice_idiom=voice_idiom,
                    voice_gender=voice_gender,
                    api_key=api_key,
                )

            success_count = sum(1 for r in results.values() if r.success)
            st.success(
                f"✅ Generated {success_count}/{len(results)} files to "
                f"`includes/sounds/{voice_idiom}/{voice_gender}/`"
            )

    # Cache management
    st.markdown("---")
    st.subheader("🗄️ Cache Management")

    file_count, total_size = generator.get_cache_size()
    st.caption(f"Cache: {file_count} files, {total_size / 1024:.1f} KB")

    if st.button("🧹 Clear Cache"):
        deleted = generator.clear_cache()
        st.success(f"Cleared {deleted} cached files")
        st.rerun()


# ---------------------------------------------------------------------------
# CLI Interface
# ---------------------------------------------------------------------------
def main() -> None:
    """Command-line interface for voice generation."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate ATC-style voice communications using OpenAI TTS"
    )
    parser.add_argument(
        "text",
        nargs="?",
        help="Text to convert to speech",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file path",
    )
    parser.add_argument(
        "-v", "--voice",
        choices=AVAILABLE_VOICES,
        default="coral",
        help="Voice to use",
    )
    parser.add_argument(
        "-s", "--speed",
        type=float,
        default=1.0,
        help="Speech speed (0.25-4.0)",
    )
    parser.add_argument(
        "-f", "--format",
        choices=AUDIO_FORMATS,
        default="mp3",
        help="Output format",
    )
    parser.add_argument(
        "-l", "--language",
        choices=["en", "es", "fr"],
        default="en",
        help="Language",
    )
    parser.add_argument(
        "--preset",
        choices=list(VOICE_PRESETS.keys()),
        help="Use a predefined voice preset",
    )
    parser.add_argument(
        "--phonetic",
        action="store_true",
        help="Generate full phonetic alphabet",
    )
    parser.add_argument(
        "--matb-pack",
        action="store_true",
        help="Generate MATB voice pack",
    )
    parser.add_argument(
        "--idiom",
        choices=["english", "spanish", "french"],
        default="english",
        help="Voice idiom for MATB pack",
    )
    parser.add_argument(
        "--gender",
        choices=["male", "female"],
        default="male",
        help="Voice gender for MATB pack",
    )

    args = parser.parse_args()

    # Build configuration
    if args.preset:
        preset = VOICE_PRESETS[args.preset]
        config = VoiceConfig(
            voice=preset.voice,
            speed=preset.speed,
            format=args.format,
            instructions=preset.instructions,
            language=preset.language,
        )
    else:
        config = VoiceConfig(
            voice=args.voice,
            speed=args.speed,
            format=args.format,
            language=args.language,
        )

    generator = ATCVoiceGenerator(config=config)

    if args.matb_pack:
        print(f"Generating MATB voice pack ({args.idiom}/{args.gender})...")
        results = generate_matb_voice_files(
            voice_idiom=args.idiom,
            voice_gender=args.gender,
        )
        success_count = sum(1 for r in results.values() if r.success)
        print(f"Generated {success_count}/{len(results)} files")
        return

    if args.phonetic:
        print("Generating phonetic alphabet...")
        results = generator.generate_phonetic_alphabet()
        success_count = sum(1 for r in results.values() if r.success)
        print(f"Generated {success_count}/{len(results)} files")
        return

    if not args.text:
        parser.error("Text is required unless using --phonetic or --matb-pack")

    print(f"Generating audio for: {args.text[:50]}...")
    result = generator.generate_communication(args.text, args.output)

    if result.success:
        print(f"✅ Audio saved to: {result.file_path}")
        if result.cache_hit:
            print("   (from cache)")
        else:
            print(f"   Generation time: {result.generation_time_ms}ms")
    else:
        print(f"❌ Failed: {result.error_message}")
        exit(1)


if __name__ == "__main__":
    main()

