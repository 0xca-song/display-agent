"""Display control tools following Agent-Computer Interface (ACI) principles."""

import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type
from enum import Enum

from .mock.display_server import MockDisplayServer, DisplayServerType
from .mock.monitor import DisplayMode, ColorProfile


class ToolResult:
    def __init__(self, success: bool, output: Any = None, error: str = None):
        self.success = success
        self.output = output
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
        }

    def __str__(self) -> str:
        if self.success:
            return str(self.output) if self.output is not None else "OK"
        return f"Error: {self.error}"


class BaseTool(ABC):
    name: str = ""
    description: str = ""

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        pass

    def get_definition(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
        }


@dataclass
class BaseToolWithServer(BaseTool):
    mock_server: Optional[MockDisplayServer] = None


@dataclass
class ListMonitorsTool(BaseToolWithServer):
    name: str = "list_monitors"
    description: str = (
        "List all connected monitors and their current configuration. "
        "Use this when you need to understand the current display setup "
        "before making changes. Returns connector names, resolution, position, "
        "scale, rotation, and whether each monitor is primary."
    )

    def execute(self, **kwargs) -> ToolResult:
        if self.mock_server:
            monitors = self.mock_server.get_all_monitors()
            output = []
            for m in monitors:
                output.append({
                    "connector": m.connector,
                    "name": m.name,
                    "connected": m.is_connected,
                    "primary": m.is_primary,
                    "mode": str(m.current_mode) if m.current_mode else None,
                    "position": {"x": m.position_x, "y": m.position_y},
                    "scale": m.scale,
                    "rotation": m.rotation,
                })
            return ToolResult(success=True, output=output)

        server_type = MockDisplayServer.detect_server_type()
        if server_type == DisplayServerType.X11:
            try:
                result = subprocess.run(
                    ["xrandr", "--listmonitors"],
                    capture_output=True, text=True, timeout=5
                )
                return ToolResult(success=True, output=result.stdout)
            except Exception as e:
                return ToolResult(success=False, error=str(e))
        else:
            try:
                result = subprocess.run(
                    ["wlprop", "--list"],
                    capture_output=True, text=True, timeout=5
                )
                return ToolResult(success=True, output=result.stdout)
            except Exception as e:
                return ToolResult(success=False, error=str(e))


@dataclass
class GetMonitorInfoTool(BaseToolWithServer):
    name: str = "get_monitor_info"
    description: str = (
        "Get detailed information about a specific monitor by connector name. "
        "Returns all available modes, current mode, position, scale, rotation, "
        "backlight level, and color profile. "
        "Example connector names: 'HDMI-1', 'DP-1', 'HDMI-A-1', 'DP-2'."
    )

    def execute(self, connector: str, **kwargs) -> ToolResult:
        if not connector:
            return ToolResult(success=False, error="connector is required")

        if self.mock_server:
            monitor = self.mock_server.get_monitor(connector)
            if monitor:
                return ToolResult(success=True, output=monitor.get_status())
            return ToolResult(success=False, error=f"Monitor {connector} not found")

        server_type = MockDisplayServer.detect_server_type()
        if server_type == DisplayServerType.X11:
            try:
                result = subprocess.run(
                    ["xrandr", "--query", "--output", connector],
                    capture_output=True, text=True, timeout=5
                )
                return ToolResult(success=True, output=result.stdout)
            except Exception as e:
                return ToolResult(success=False, error=str(e))
        else:
            try:
                props = ["mode", "position", "scale", "rotation", "primary", "backlight"]
                output = {}
                for prop in props:
                    result = subprocess.run(
                        ["wlprop", connector, prop],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.returncode == 0:
                        output[prop] = result.stdout.strip()
                return ToolResult(success=True, output=output)
            except Exception as e:
                return ToolResult(success=False, error=str(e))


@dataclass
class SetModeTool(BaseToolWithServer):
    name: str = "set_mode"
    description: str = (
        "Set the display mode (resolution and refresh rate) for a monitor. "
        "Format: WIDTHxHEIGHT@REFRESH_RATE (e.g., '1920x1080@60'). "
        "If refresh rate is omitted, uses the default 60Hz. "
        "Available modes can be queried with list_monitors or get_monitor_info."
    )

    def execute(self, connector: str, mode: str, **kwargs) -> ToolResult:
        if not connector or not mode:
            return ToolResult(success=False, error="connector and mode are required")

        if self.mock_server:
            monitor = self.mock_server.get_monitor(connector)
            if not monitor:
                return ToolResult(success=False, error=f"Monitor {connector} not found")

            target_mode = None
            mode_str = mode if "@" in mode else f"{mode}@60"
            for m in monitor.available_modes:
                if str(m) == mode_str:
                    target_mode = m
                    break

            if target_mode is None:
                available = [str(m) for m in monitor.available_modes]
                return ToolResult(
                    success=False,
                    error=f"Mode {mode_str} not available. Available: {available}"
                )

            monitor.set_mode(target_mode)
            return ToolResult(success=True, output=f"Set {connector} to {target_mode}")

        server_type = MockDisplayServer.detect_server_type()
        if server_type == DisplayServerType.X11:
            try:
                result = subprocess.run(
                    ["xrandr", "--output", connector, "--mode", mode],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return ToolResult(success=True, output=f"Set {connector} to {mode}")
                return ToolResult(success=False, error=result.stderr)
            except Exception as e:
                return ToolResult(success=False, error=str(e))
        else:
            try:
                result = subprocess.run(
                    ["wlprop", "set", connector, "mode", mode],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return ToolResult(success=True, output=f"Set {connector} to {mode}")
                return ToolResult(success=False, error=result.stderr)
            except Exception as e:
                return ToolResult(success=False, error=str(e))


@dataclass
class SetPositionTool(BaseToolWithServer):
    name: str = "set_position"
    description: str = (
        "Set the position of a monitor in a multi-monitor setup. "
        "Positions are relative to the virtual framebuffer. "
        "Format: 'WxH' where W is X offset and H is Y offset. "
        "Example: '0x0' places monitor at top-left, '1920x0' places it "
        "to the right of a 1920px wide monitor."
    )

    def execute(self, connector: str, position: str, **kwargs) -> ToolResult:
        if not connector or not position:
            return ToolResult(success=False, error="connector and position are required")

        if self.mock_server:
            monitor = self.mock_server.get_monitor(connector)
            if not monitor:
                return ToolResult(success=False, error=f"Monitor {connector} not found")

            try:
                parts = position.split("x")
                if len(parts) != 2:
                    raise ValueError("Position must be in WxH format")
                x, y = int(parts[0]), int(parts[1])
                monitor.set_position(x, y)
                return ToolResult(
                    success=True,
                    output=f"Set {connector} position to {position}"
                )
            except ValueError as e:
                return ToolResult(success=False, error=f"Invalid position format: {e}")

        server_type = MockDisplayServer.detect_server_type()
        if server_type == DisplayServerType.X11:
            try:
                result = subprocess.run(
                    ["xrandr", "--output", connector, "--pos", position],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return ToolResult(
                        success=True,
                        output=f"Set {connector} position to {position}"
                    )
                return ToolResult(success=False, error=result.stderr)
            except Exception as e:
                return ToolResult(success=False, error=str(e))
        else:
            try:
                result = subprocess.run(
                    ["wlprop", "set", connector, "position", position],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return ToolResult(
                        success=True,
                        output=f"Set {connector} position to {position}"
                    )
                return ToolResult(success=False, error=result.stderr)
            except Exception as e:
                return ToolResult(success=False, error=str(e))


@dataclass
class SetPrimaryTool(BaseToolWithServer):
    name: str = "set_primary"
    description: str = (
        "Set a monitor as the primary monitor. "
        "The primary monitor typically contains the desktop taskbar "
        "and where new windows open by default. "
        "Only one monitor can be primary at a time."
    )

    def execute(self, connector: str, **kwargs) -> ToolResult:
        if not connector:
            return ToolResult(success=False, error="connector is required")

        if self.mock_server:
            if self.mock_server.set_primary(connector):
                return ToolResult(success=True, output=f"Set {connector} as primary")
            return ToolResult(success=False, error=f"Monitor {connector} not found")

        server_type = MockDisplayServer.detect_server_type()
        if server_type == DisplayServerType.X11:
            try:
                result = subprocess.run(
                    ["xrandr", "--output", connector, "--primary"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return ToolResult(success=True, output=f"Set {connector} as primary")
                return ToolResult(success=False, error=result.stderr)
            except Exception as e:
                return ToolResult(success=False, error=str(e))
        else:
            try:
                result = subprocess.run(
                    ["wlprop", "set", connector, "primary", "true"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return ToolResult(success=True, output=f"Set {connector} as primary")
                return ToolResult(success=False, error=result.stderr)
            except Exception as e:
                return ToolResult(success=False, error=str(e))


@dataclass
class SetScaleTool(BaseToolWithServer):
    name: str = "set_scale"
    description: str = (
        "Set the UI scale factor for a monitor. "
        "Values between 0.25 and 4.0 are supported. "
        "Examples: '1.0' is normal scale, '2.0' is 200% scale ( Retina displays), "
        "'0.5' is 50% scale."
    )

    def execute(self, connector: str, scale: float, **kwargs) -> ToolResult:
        if not connector or scale is None:
            return ToolResult(success=False, error="connector and scale are required")

        if not 0.25 <= scale <= 4.0:
            return ToolResult(
                success=False,
                error="Scale must be between 0.25 and 4.0"
            )

        if self.mock_server:
            monitor = self.mock_server.get_monitor(connector)
            if not monitor:
                return ToolResult(success=False, error=f"Monitor {connector} not found")

            if monitor.set_scale(scale):
                return ToolResult(
                    success=True,
                    output=f"Set {connector} scale to {scale}"
                )
            return ToolResult(success=False, error="Failed to set scale")

        server_type = MockDisplayServer.detect_server_type()
        if server_type == DisplayServerType.X11:
            try:
                result = subprocess.run(
                    ["xrandr", "--output", connector, "--scale", f"{scale}x{scale}"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return ToolResult(
                        success=True,
                        output=f"Set {connector} scale to {scale}"
                    )
                return ToolResult(success=False, error=result.stderr)
            except Exception as e:
                return ToolResult(success=False, error=str(e))
        else:
            try:
                result = subprocess.run(
                    ["wlprop", "set", connector, "scale", str(scale)],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return ToolResult(
                        success=True,
                        output=f"Set {connector} scale to {scale}"
                    )
                return ToolResult(success=False, error=result.stderr)
            except Exception as e:
                return ToolResult(success=False, error=str(e))


@dataclass
class SetRotationTool(BaseToolWithServer):
    name: str = "set_rotation"
    description: str = (
        "Set the rotation of a monitor. "
        "Options: 'normal', 'left', 'right', 'inverted'. "
        "'left' rotates 90 degrees counter-clockwise, "
        "'right' rotates 90 degrees clockwise, "
        "'inverted' rotates 180 degrees."
    )

    def execute(self, connector: str, rotation: str, **kwargs) -> ToolResult:
        if not connector or not rotation:
            return ToolResult(success=False, error="connector and rotation are required")

        valid_rotations = ["normal", "left", "right", "inverted"]
        if rotation not in valid_rotations:
            return ToolResult(
                success=False,
                error=f"Invalid rotation. Must be one of: {valid_rotations}"
            )

        if self.mock_server:
            monitor = self.mock_server.get_monitor(connector)
            if not monitor:
                return ToolResult(success=False, error=f"Monitor {connector} not found")

            if monitor.set_rotation(rotation):
                return ToolResult(
                    success=True,
                    output=f"Set {connector} rotation to {rotation}"
                )
            return ToolResult(success=False, error="Failed to set rotation")

        server_type = MockDisplayServer.detect_server_type()
        if server_type == DisplayServerType.X11:
            try:
                result = subprocess.run(
                    ["xrandr", "--output", connector, "--rotate", rotation],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return ToolResult(
                        success=True,
                        output=f"Set {connector} rotation to {rotation}"
                    )
                return ToolResult(success=False, error=result.stderr)
            except Exception as e:
                return ToolResult(success=False, error=str(e))
        else:
            try:
                result = subprocess.run(
                    ["wlprop", "set", connector, "rotation", rotation],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return ToolResult(
                        success=True,
                        output=f"Set {connector} rotation to {rotation}"
                    )
                return ToolResult(success=False, error=result.stderr)
            except Exception as e:
                return ToolResult(success=False, error=str(e))


@dataclass
class SetBacklightTool(BaseToolWithServer):
    name: str = "set_backlight"
    description: str = (
        "Set the backlight/brightness of a monitor. "
        "Value range is typically 0-100 (percent). "
        "Some monitors may not support this feature."
    )

    def execute(self, connector: str, value: int, **kwargs) -> ToolResult:
        if not connector or value is None:
            return ToolResult(success=False, error="connector and value are required")

        if not 0 <= value <= 100:
            return ToolResult(
                success=False,
                error="Backlight value must be between 0 and 100"
            )

        if self.mock_server:
            monitor = self.mock_server.get_monitor(connector)
            if not monitor:
                return ToolResult(success=False, error=f"Monitor {connector} not found")

            if monitor.set_backlight(value):
                return ToolResult(
                    success=True,
                    output=f"Set {connector} backlight to {value}"
                )
            return ToolResult(
                success=False,
                error="Monitor does not support backlight control"
            )

        server_type = MockDisplayServer.detect_server_type()
        if server_type == DisplayServerType.X11:
            try:
                result = subprocess.run(
                    ["xrandr", "--output", connector, "--brightness", str(value / 100)],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return ToolResult(
                        success=True,
                        output=f"Set {connector} backlight to {value}"
                    )
                return ToolResult(success=False, error=result.stderr)
            except Exception as e:
                return ToolResult(success=False, error=str(e))
        else:
            try:
                result = subprocess.run(
                    ["wlprop", "set", connector, "backlight", str(value)],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return ToolResult(
                        success=True,
                        output=f"Set {connector} backlight to {value}"
                    )
                return ToolResult(success=False, error=result.stderr)
            except Exception as e:
                return ToolResult(success=False, error=str(e))


@dataclass
class DisableMonitorTool(BaseToolWithServer):
    name: str = "disable_monitor"
    description: str = (
        "Disable a monitor (turn it off). "
        "Use this when a monitor is temporarily not needed "
        "or to disconnect a monitor without physically unplugging it."
    )

    def execute(self, connector: str, **kwargs) -> ToolResult:
        if not connector:
            return ToolResult(success=False, error="connector is required")

        if self.mock_server:
            monitor = self.mock_server.get_monitor(connector)
            if not monitor:
                return ToolResult(success=False, error=f"Monitor {connector} not found")

            monitor.is_connected = False
            return ToolResult(success=True, output=f"Disabled {connector}")

        server_type = MockDisplayServer.detect_server_type()
        if server_type == DisplayServerType.X11:
            try:
                result = subprocess.run(
                    ["xrandr", "--output", connector, "--off"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return ToolResult(success=True, output=f"Disabled {connector}")
                return ToolResult(success=False, error=result.stderr)
            except Exception as e:
                return ToolResult(success=False, error=str(e))
        else:
            try:
                result = subprocess.run(
                    ["wlprop", "set", connector, "enabled", "false"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return ToolResult(success=True, output=f"Disabled {connector}")
                return ToolResult(success=False, error=result.stderr)
            except Exception as e:
                return ToolResult(success=False, error=str(e))


@dataclass
class EnableMonitorTool(BaseToolWithServer):
    name: str = "enable_monitor"
    description: str = (
        "Enable a previously disabled monitor. "
        "This turns the monitor back on at its previous settings."
    )

    def execute(self, connector: str, **kwargs) -> ToolResult:
        if not connector:
            return ToolResult(success=False, error="connector is required")

        if self.mock_server:
            monitor = self.mock_server.get_monitor(connector)
            if not monitor:
                return ToolResult(success=False, error=f"Monitor {connector} not found")

            monitor.is_connected = True
            return ToolResult(success=True, output=f"Enabled {connector}")

        server_type = MockDisplayServer.detect_server_type()
        if server_type == DisplayServerType.X11:
            try:
                result = subprocess.run(
                    ["xrandr", "--output", connector, "--auto"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return ToolResult(success=True, output=f"Enabled {connector}")
                return ToolResult(success=False, error=result.stderr)
            except Exception as e:
                return ToolResult(success=False, error=str(e))
        else:
            try:
                result = subprocess.run(
                    ["wlprop", "set", connector, "enabled", "true"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return ToolResult(success=True, output=f"Enabled {connector}")
                return ToolResult(success=False, error=result.stderr)
            except Exception as e:
                return ToolResult(success=False, error=str(e))


class ToolRegistry:
    def __init__(self, mock_server: Optional[MockDisplayServer] = None):
        self.mock_server = mock_server
        self._tools: Dict[str, BaseTool] = {}
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        tools = [
            ListMonitorsTool(self.mock_server),
            GetMonitorInfoTool(self.mock_server),
            SetModeTool(self.mock_server),
            SetPositionTool(self.mock_server),
            SetPrimaryTool(self.mock_server),
            SetScaleTool(self.mock_server),
            SetRotationTool(self.mock_server),
            SetBacklightTool(self.mock_server),
            DisableMonitorTool(self.mock_server),
            EnableMonitorTool(self.mock_server),
        ]
        for tool in tools:
            self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def get_all_tools(self) -> List[Dict[str, Any]]:
        return [tool.get_definition() for tool in self._tools.values()]

    def execute(self, tool_name: str, **kwargs) -> ToolResult:
        tool = self.get_tool(tool_name)
        if not tool:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")
        return tool.execute(**kwargs)
