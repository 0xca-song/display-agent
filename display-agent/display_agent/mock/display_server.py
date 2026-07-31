"""Mock Display Server supporting X11 and Wayland modes."""

import subprocess
from typing import Dict, List, Optional, Any
from enum import Enum

from .monitor import MockMonitor, DisplayMode, ColorProfile


class DisplayServerType(Enum):
    X11 = "x11"
    WAYLAND = "wayland"
    UNKNOWN = "unknown"


class MockDisplayServer:
    def __init__(self, server_type: DisplayServerType = DisplayServerType.X11):
        self.server_type = server_type
        self.monitors: Dict[str, MockMonitor] = {}
        self.command_history: List[Dict[str, Any]] = []

    def add_monitor(self, monitor: MockMonitor) -> None:
        self.monitors[monitor.connector] = monitor

    def remove_monitor(self, connector: str) -> bool:
        if connector in self.monitors:
            del self.monitors[connector]
            return True
        return False

    def get_monitor(self, connector: str) -> Optional[MockMonitor]:
        return self.monitors.get(connector)

    def get_all_monitors(self) -> List[MockMonitor]:
        return list(self.monitors.values())

    def get_primary_monitor(self) -> Optional[MockMonitor]:
        for m in self.monitors.values():
            if m.is_primary:
                return m
        return None

    def set_primary(self, connector: str) -> bool:
        for m in self.monitors.values():
            m.set_primary(m.connector == connector)
        return connector in self.monitors

    def execute_xrandr(self, args: List[str]) -> Dict[str, Any]:
        self.command_history.append({"type": "xrandr", "args": args})

        if not args:
            return self._xrandr_list()

        cmd = args[0] if args else None
        if cmd == "--output":
            return self._xrandr_output(args[1:])
        elif cmd == "--auto":
            return self._xrandr_auto()
        elif cmd == "--off":
            return self._xrandr_off(args[1:] if len(args) > 1 else [])
        elif cmd == "--primary":
            return self._xrandr_primary()
        else:
            return {"success": False, "error": f"Unknown xrandr command: {cmd}"}

    def execute_wlprop(self, args: List[str]) -> Dict[str, Any]:
        self.command_history.append({"type": "wlprop", "args": args})

        if not args:
            return self._wlprop_list()

        subcmd = args[0] if args else None
        if subcmd == "set":
            return self._wlprop_set(args[1:])
        elif subcmd == "get":
            return self._wlprop_get(args[1:] if len(args) > 1 else [])
        else:
            return {"success": False, "error": f"Unknown wlprop command: {subcmd}"}

    def _xrandr_list(self) -> Dict[str, Any]:
        output_lines = []
        for m in self.monitors.values():
            status = "connected" if m.is_connected else "disconnected"
            primary_mark = " primary" if m.is_primary else ""
            output_lines.append(f"{m.connector} {status}{primary_mark}")
            if m.is_connected:
                output_lines.append(f"   {m.current_mode}")
                for mode in m.available_modes:
                    if mode != m.current_mode:
                        output_lines.append(f"   {mode}")
        return {"success": True, "output": "\n".join(output_lines)}

    def _xrandr_output(self, args: List[str]) -> Dict[str, Any]:
        if not args:
            return {"success": False, "error": "xrandr --output requires connector argument"}

        connector = args[0]
        monitor = self.get_monitor(connector)

        i = 1
        while i < len(args):
            arg = args[i]
            if arg == "--mode":
                if i + 1 >= len(args):
                    return {"success": False, "error": "--mode requires resolution argument"}
                mode_str = args[i + 1]
                i += 2
                if monitor:
                    for mode in monitor.available_modes:
                        if str(mode) == mode_str:
                            monitor.set_mode(mode)
                            break
                continue
            elif arg == "--pos":
                if i + 1 >= len(args):
                    return {"success": False, "error": "--pos requires position argument"}
                pos = args[i + 1]
                i += 2
                if monitor and ":" in pos:
                    x, y = pos.split(":")
                    monitor.set_position(int(x), int(y))
                continue
            elif arg == "--primary":
                if monitor:
                    self.set_primary(connector)
                i += 1
                continue
            elif arg == "--scale":
                if i + 1 >= len(args):
                    return {"success": False, "error": "--scale requires scale argument"}
                scale = args[i + 1]
                i += 2
                if monitor:
                    try:
                        monitor.set_scale(float(scale))
                    except ValueError:
                        return {"success": False, "error": f"Invalid scale: {scale}"}
                continue
            elif arg == "--rotate":
                if i + 1 >= len(args):
                    return {"success": False, "error": "--rotate requires rotation argument"}
                rotation = args[i + 1]
                i += 2
                if monitor:
                    monitor.set_rotation(rotation)
                continue
            elif arg == "--off":
                if monitor:
                    monitor.is_connected = False
                i += 1
                continue
            elif arg == "--auto":
                if monitor:
                    monitor.is_connected = True
                i += 1
                continue
            else:
                i += 1

        return {"success": True}

    def _xrandr_auto(self) -> Dict[str, Any]:
        for m in self.monitors.values():
            if not m.is_connected:
                m.is_connected = True
        return {"success": True}

    def _xrandr_off(self, args: List[str]) -> Dict[str, Any]:
        if not args:
            return {"success": False, "error": "--off requires connector argument"}
        connector = args[0]
        monitor = self.get_monitor(connector)
        if monitor:
            monitor.is_connected = False
        return {"success": True}

    def _xrandr_primary(self) -> Dict[str, Any]:
        for m in self.monitors.values():
            if m.is_connected and not m.is_primary:
                m.set_primary(True)
                break
        return {"success": True}

    def _wlprop_list(self) -> Dict[str, Any]:
        output_lines = []
        for m in self.monitors.values():
            status = "connected" if m.is_connected else "disconnected"
            output_lines.append(f"{m.connector}: {status}")
            if m.is_connected:
                output_lines.append(f"  mode: {m.current_mode}")
                output_lines.append(f"  position: {m.position_x},{m.position_y}")
                output_lines.append(f"  scale: {m.scale}")
                output_lines.append(f"  rotation: {m.rotation}")
                output_lines.append(f"  primary: {m.is_primary}")
                output_lines.append(f"  backlight: {m.backlight}")
        return {"success": True, "output": "\n".join(output_lines)}

    def _wlprop_set(self, args: List[str]) -> Dict[str, Any]:
        if len(args) < 3:
            return {"success": False, "error": "wlprop set requires connector property value"}

        connector, prop, value = args[0], args[1], args[2]
        monitor = self.get_monitor(connector)

        if not monitor:
            return {"success": False, "error": f"Unknown connector: {connector}"}

        if prop == "mode":
            for mode in monitor.available_modes:
                if str(mode) == value:
                    monitor.set_mode(mode)
                    return {"success": True}
            return {"success": False, "error": f"Mode {value} not available"}
        elif prop == "position":
            if "," in value:
                x, y = value.split(",")
                monitor.set_position(int(x), int(y))
                return {"success": True}
            return {"success": False, "error": f"Invalid position format: {value}"}
        elif prop == "scale":
            try:
                monitor.set_scale(float(value))
                return {"success": True}
            except ValueError:
                return {"success": False, "error": f"Invalid scale: {value}"}
        elif prop == "rotation":
            if monitor.set_rotation(value):
                return {"success": True}
            return {"success": False, "error": f"Invalid rotation: {value}"}
        elif prop == "primary":
            monitor.set_primary(value == "true")
            return {"success": True}
        elif prop == "backlight":
            try:
                if monitor.set_backlight(int(value)):
                    return {"success": True}
                return {"success": False, "error": f"Backlight {value} out of range"}
            except ValueError:
                return {"success": False, "error": f"Invalid backlight value: {value}"}
        else:
            return {"success": False, "error": f"Unknown property: {prop}"}

    def _wlprop_get(self, args: List[str]) -> Dict[str, Any]:
        if len(args) < 2:
            return {"success": False, "error": "wlprop get requires connector property"}

        connector, prop = args[0], args[1]
        monitor = self.get_monitor(connector)

        if not monitor:
            return {"success": False, "error": f"Unknown connector: {connector}"}

        if prop == "mode":
            return {"success": True, "value": str(monitor.current_mode)}
        elif prop == "position":
            return {"success": True, "value": f"{monitor.position_x},{monitor.position_y}"}
        elif prop == "scale":
            return {"success": True, "value": str(monitor.scale)}
        elif prop == "rotation":
            return {"success": True, "value": monitor.rotation}
        elif prop == "primary":
            return {"success": True, "value": str(monitor.is_primary).lower()}
        elif prop == "backlight":
            return {"success": True, "value": str(monitor.backlight)}
        else:
            return {"success": False, "error": f"Unknown property: {prop}"}

    def get_state(self) -> Dict[str, Any]:
        return {
            "server_type": self.server_type.value,
            "monitors": {k: v.get_status() for k, v in self.monitors.items()},
            "command_history": self.command_history,
        }

    def reset(self) -> None:
        self.monitors.clear()
        self.command_history.clear()

    @classmethod
    def detect_server_type(cls) -> DisplayServerType:
        try:
            result = subprocess.run(
                ["ps", "-p", str(subprocess.getpid())],
                capture_output=True,
                text=True,
            )
            if "wayland" in result.stdout.lower():
                return DisplayServerType.WAYLAND
        except Exception:
            pass

        if "WAYLAND_DISPLAY" in __import__("os").environ:
            return DisplayServerType.WAYLAND
        if "DISPLAY" in __import__("os").environ:
            return DisplayServerType.X11

        return DisplayServerType.UNKNOWN
