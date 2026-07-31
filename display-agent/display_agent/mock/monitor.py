"""Mock Monitor implementation for testing."""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable


def _default_color_profile() -> "ColorProfile":
    return ColorProfile(name="Default")


@dataclass
class DisplayMode:
    width: int
    height: int
    refresh_rate: float = 60.0

    def __str__(self) -> str:
        return f"{self.width}x{self.height}@{self.refresh_rate}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "refresh_rate": self.refresh_rate,
        }


@dataclass
@dataclass
class ColorProfile:
    name: str
    gamma: float = 2.2
    brightness: float = 1.0
    contrast: float = 1.0
    temperature: int = 6500

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "gamma": self.gamma,
            "brightness": self.brightness,
            "contrast": self.contrast,
            "temperature": self.temperature,
        }


@dataclass
class MockMonitor:
    name: str
    connector: str
    is_connected: bool = True
    is_primary: bool = False
    position_x: int = 0
    position_y: int = 0
    rotation: str = "normal"
    scale: float = 1.0
    current_mode: Optional[DisplayMode] = None
    available_modes: List[DisplayMode] = field(default_factory=list)
    color_profile: ColorProfile = field(default_factory=_default_color_profile)
    backlight: int = 100
    backlight_range: tuple = (0, 100)

    def __post_init__(self):
        if not self.available_modes and self.current_mode:
            self.available_modes = [self.current_mode]

    def set_mode(self, mode: DisplayMode) -> bool:
        if mode in self.available_modes:
            self.current_mode = mode
            return True
        return False

    def set_position(self, x: int, y: int) -> None:
        self.position_x = x
        self.position_y = y

    def set_primary(self, is_primary: bool) -> None:
        self.is_primary = is_primary

    def set_rotation(self, rotation: str) -> bool:
        valid_rotations = ["normal", "left", "right", "inverted"]
        if rotation in valid_rotations:
            self.rotation = rotation
            return True
        return False

    def set_scale(self, scale: float) -> bool:
        if 0.25 <= scale <= 4.0:
            self.scale = scale
            return True
        return False

    def set_backlight(self, value: int) -> bool:
        min_val, max_val = self.backlight_range
        if min_val <= value <= max_val:
            self.backlight = value
            return True
        return False

    def set_color_profile(self, profile: ColorProfile) -> None:
        self.color_profile = profile

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "connector": self.connector,
            "connected": self.is_connected,
            "is_primary": self.is_primary,
            "position": {"x": self.position_x, "y": self.position_y},
            "rotation": self.rotation,
            "scale": self.scale,
            "current_mode": self.current_mode.to_dict() if self.current_mode else None,
            "available_modes": [m.to_dict() for m in self.available_modes],
            "color_profile": self.color_profile.to_dict(),
            "backlight": self.backlight,
        }

    @classmethod
    def create_common(cls, name: str, connector: str, mode: DisplayMode):
        return cls(
            name=name,
            connector=connector,
            is_connected=True,
            current_mode=mode,
            available_modes=[
                mode,
                DisplayMode(mode.width // 2, mode.height // 2, mode.refresh_rate),
            ],
        )
