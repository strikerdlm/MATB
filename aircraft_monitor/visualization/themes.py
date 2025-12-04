"""Color themes for the monitoring dashboard."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Theme:
    """Dashboard color theme."""

    # Primary colors
    primary: str
    secondary: str
    accent: str

    # Status colors
    success: str
    warning: str
    error: str
    critical: str

    # UI colors
    background: str
    border: str
    text: str
    text_dim: str

    # Special colors
    radar_blip: str
    threat: str
    friendly: str
    unknown: str


# Military-style dark theme
MILITARY_THEME = Theme(
    primary="bright_green",
    secondary="cyan",
    accent="bright_yellow",
    success="green",
    warning="yellow",
    error="red",
    critical="bold red",
    background="black",
    border="bright_green",
    text="white",
    text_dim="bright_black",
    radar_blip="bright_green",
    threat="red",
    friendly="blue",
    unknown="yellow",
)

# Night vision theme
NIGHT_VISION_THEME = Theme(
    primary="green",
    secondary="bright_green",
    accent="green",
    success="bright_green",
    warning="green",
    error="bright_green",
    critical="bold bright_green",
    background="black",
    border="green",
    text="green",
    text_dim="dark_green",
    radar_blip="bright_green",
    threat="bright_green",
    friendly="green",
    unknown="green",
)

# Combat theme
COMBAT_THEME = Theme(
    primary="red",
    secondary="bright_red",
    accent="yellow",
    success="green",
    warning="yellow",
    error="red",
    critical="bold white on red",
    background="black",
    border="red",
    text="white",
    text_dim="bright_black",
    radar_blip="red",
    threat="bright_red",
    friendly="blue",
    unknown="yellow",
)
