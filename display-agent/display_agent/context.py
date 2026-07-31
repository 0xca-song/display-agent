"""Context management: system prompt, memory, and state bar."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime


@dataclass
class UserMemory:
    display_preferences: Dict[str, Any] = field(default_factory=dict)
    known_monitors: Dict[str, str] = field(default_factory=dict)
    session_history: List[Dict[str, Any]] = field(default_factory=list)
    last_updated: Optional[str] = None

    def add_session(self, session: Dict[str, Any]) -> None:
        self.session_history.append(session)
        self.last_updated = datetime.now().isoformat()

    def update_preference(self, key: str, value: Any) -> None:
        self.display_preferences[key] = value
        self.last_updated = datetime.now().isoformat()

    def get_preference(self, key: str, default: Any = None) -> Any:
        return self.display_preferences.get(key, default)


@dataclass
class DisplayStateBar:
    server_type: str = "unknown"
    monitor_count: int = 0
    primary_monitor: Optional[str] = None
    active_operations: List[str] = field(default_factory=list)

    def to_prompt_string(self) -> str:
        lines = [
            "=== Display System State ===",
            f"Display Server: {self.server_type}",
            f"Connected Monitors: {self.monitor_count}",
            f"Primary Monitor: {self.primary_monitor or 'None'}",
        ]
        if self.active_operations:
            lines.append(f"Active Operations: {', '.join(self.active_operations)}")
        return "\n".join(lines)


@dataclass
class SystemPrompt:
    identity: str = (
        "You are DisplayAgent, an AI assistant specialized in configuring "
        "Linux display settings. You help users manage their monitors, "
        "resolution, refresh rate, multi-monitor layout, brightness, "
        "color calibration, and other display-related tasks."
    )

    capabilities: List[str] = field(default_factory=lambda: [
        "List all connected monitors and their current configuration",
        "Change monitor resolution and refresh rate",
        "Arrange multi-monitor layout (position monitors relative to each other)",
        "Set primary monitor",
        "Adjust UI scale factor for HiDPI displays",
        "Rotate monitor (normal, left, right, inverted)",
        "Adjust backlight/brightness",
        "Enable or disable monitors",
    ])

    constraints: List[str] = field(default_factory=lambda: [
        "Only modify display configuration, do not execute other system commands",
        "Verify changes were applied successfully before reporting completion",
        "When multiple monitors are involved, confirm which monitor the user means",
        "For resolution changes, only use modes reported as available",
        "If a requested operation is not supported, explain why and suggest alternatives",
    ])

    safety_rules: List[str] = field(default_factory=lambda: [
        "Do not execute commands that could damage hardware (e.g., invalid refresh rates)",
        "When uncertain about a monitor's capabilities, query available modes first",
        "Backlight changes are limited to 0-100 range",
        "Scale factors must be between 0.25 and 4.0",
    ])

    def to_prompt_string(self) -> str:
        lines = [
            self.identity,
            "",
            "## Capabilities",
            *[f"- {cap}" for cap in self.capabilities],
            "",
            "## Operating Constraints",
            *[f"- {c}" for c in self.constraints],
            "",
            "## Safety Rules",
            *[f"- {r}" for r in self.safety_rules],
        ]
        return "\n".join(lines)


class ContextManager:
    def __init__(
        self,
        system_prompt: Optional[SystemPrompt] = None,
        memory: Optional[UserMemory] = None,
    ):
        self.system_prompt = system_prompt or SystemPrompt()
        self.memory = memory or UserMemory()
        self.state_bar = DisplayStateBar()
        self.conversation_history: List[Dict[str, str]] = []

    def update_state_bar(self, **kwargs) -> None:
        for key, value in kwargs.items():
            if hasattr(self.state_bar, key):
                setattr(self.state_bar, key, value)

    def add_user_message(self, message: str) -> None:
        self.conversation_history.append({"role": "user", "content": message})

    def add_assistant_message(self, message: str) -> None:
        self.conversation_history.append({"role": "assistant", "content": message})

    def get_context_for_llm(self) -> Dict[str, Any]:
        return {
            "system_prompt": self.system_prompt.to_prompt_string(),
            "state_bar": self.state_bar.to_prompt_string(),
            "user_memory": self.memory.display_preferences,
            "conversation_history": self.conversation_history,
        }

    def build_static_prefix(self, tool_definitions: List[Dict[str, Any]]) -> str:
        parts = [
            self.system_prompt.to_prompt_string(),
            "",
            "=== Current Display State ===",
            self.state_bar.to_prompt_string(),
            "",
            "=== Available Tools ===",
        ]
        for tool in tool_definitions:
            parts.append(f"**{tool['name']}**: {tool['description']}")

        if self.memory.display_preferences:
            parts.append("")
            parts.append("=== User Preferences (from memory) ===")
            for key, value in self.memory.display_preferences.items():
                parts.append(f"- {key}: {value}")

        return "\n".join(parts)

    def record_action(self, action: str, result: str) -> None:
        self.memory.add_session({
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "result": result,
        })
