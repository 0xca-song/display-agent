"""Evaluation test cases for DisplayAgent."""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from enum import Enum
import json

from display_agent.mock.display_server import MockDisplayServer, DisplayServerType
from display_agent.mock.monitor import MockMonitor, DisplayMode
from display_agent.tools import ToolRegistry
from display_agent.agent import DisplayAgent
from display_agent.context import ContextManager
from display_agent.harness import Harness


class CaseCategory(Enum):
    SINGLE_MONITOR = "single_monitor"
    MULTI_MONITOR = "multi_monitor"
    X11_SPECIFIC = "x11_specific"
    WAYLAND_SPECIFIC = "wayland_specific"
    EDGE_CASE = "edge_case"
    SAFETY = "safety"


@dataclass
class TestCase:
    id: str
    name: str
    category: CaseCategory
    description: str
    user_message: str
    initial_state_fn: Callable[[MockDisplayServer], None]
    expected_checks: List[Callable[[MockDisplayServer], tuple]]
    expected_trajectory_contains: Optional[List[str]] = None
    expected_final_answer_contains: Optional[List[str]] = None
    server_type: DisplayServerType = DisplayServerType.X11
    difficulty: int = 1

    def run(self, agent: DisplayAgent, mock_server: MockDisplayServer) -> Dict[str, Any]:
        self.initial_state_fn(mock_server)

        context = ContextManager()
        context.update_state_bar(
            server_type=self.server_type.value,
            monitor_count=len(mock_server.get_all_monitors()),
        )

        original_execute = agent.tool_registry.mock_server
        agent.tool_registry.mock_server = mock_server

        try:
            result = agent.run(self.user_message)
            trajectory = agent.get_trajectory()

            check_results = []
            all_passed = True
            for check_fn in self.expected_checks:
                try:
                    passed, msg = check_fn(mock_server)
                    check_results.append({"check": check_fn.__name__, "passed": passed, "message": msg})
                    if not passed:
                        all_passed = False
                except Exception as e:
                    check_results.append({"check": check_fn.__name__, "passed": False, "message": str(e)})
                    all_passed = False

            trajectory_info = []
            for step in trajectory.steps:
                step_info = {
                    "step": step.step_number,
                    "thought": step.thought,
                }
                if step.action:
                    step_info["action"] = step.action.name
                    step_info["args"] = step.action.arguments
                if step.observation:
                    step_info["observation"] = step.observation
                if step.final_answer:
                    step_info["final_answer"] = step.final_answer
                trajectory_info.append(step_info)

            return {
                "case_id": self.id,
                "case_name": self.name,
                "passed": all_passed,
                "agent_output": result,
                "checks": check_results,
                "trajectory": trajectory_info,
            }
        finally:
            agent.tool_registry.mock_server = original_execute


@dataclass
class TestSuite:
    name: str
    description: str
    cases: List[TestCase] = field(default_factory=list)

    def add_case(self, case: TestCase) -> None:
        self.cases.append(case)

    def run_all(self, agent: DisplayAgent, mock_server: MockDisplayServer) -> Dict[str, Any]:
        results = []
        for case in self.cases:
            result = case.run(agent, mock_server)
            results.append(result)

        passed = sum(1 for r in results if r["passed"])
        total = len(results)

        return {
            "suite_name": self.name,
            "total_cases": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": passed / total if total > 0 else 0,
            "results": results,
        }


def create_single_monitor_setup(server: MockDisplayServer) -> None:
    server.reset()
    server.server_type = DisplayServerType.X11
    monitor = MockMonitor.create_common(
        name="Dell U2720Q",
        connector="HDMI-1",
        mode=DisplayMode(3840, 2160, 60.0),
    )
    server.add_monitor(monitor)


def create_dual_monitor_setup(server: MockDisplayServer) -> None:
    server.reset()
    server.server_type = DisplayServerType.X11

    monitor1 = MockMonitor.create_common(
        name="Dell U2720Q",
        connector="HDMI-1",
        mode=DisplayMode(1920, 1080, 60.0),
    )
    monitor1.is_primary = True
    monitor1.set_position(0, 0)

    monitor2 = MockMonitor.create_common(
        name="Samsung CFG73",
        connector="DP-1",
        mode=DisplayMode(2560, 1440, 144.0),
    )
    monitor2.set_position(1920, 0)

    server.add_monitor(monitor1)
    server.add_monitor(monitor2)


def create_wayland_setup(server: MockDisplayServer) -> None:
    server.reset()
    server.server_type = DisplayServerType.WAYLAND

    monitor = MockMonitor.create_common(
        name="LG UltraFine",
        connector="HDMI-A-1",
        mode=DisplayMode(2560, 1440, 60.0),
    )
    server.add_monitor(monitor)


def check_primary_is_hdmi1(server: MockDisplayServer) -> tuple:
    hdmi1 = server.get_monitor("HDMI-1")
    if hdmi1 and hdmi1.is_primary:
        return True, "HDMI-1 is primary"
    return False, "HDMI-1 is not primary"


def check_primary_is_dp1(server: MockDisplayServer) -> tuple:
    dp1 = server.get_monitor("DP-1")
    if dp1 and dp1.is_primary:
        return True, "DP-1 is primary"
    return False, "DP-1 is not primary"


def check_mode_is_1920x1080(connector: str) -> Callable:
    def checker(server: MockDisplayServer) -> tuple:
        monitor = server.get_monitor(connector)
        if monitor and monitor.current_mode:
            if monitor.current_mode.width == 1920 and monitor.current_mode.height == 1080:
                return True, f"{connector} is 1920x1080"
        return False, f"{connector} mode check failed"
    return checker


def check_monitor_disabled(connector: str) -> Callable:
    def checker(server: MockDisplayServer) -> tuple:
        monitor = server.get_monitor(connector)
        if monitor and not monitor.is_connected:
            return True, f"{connector} is disabled"
        return False, f"{connector} is not disabled"
    return checker


def check_monitor_enabled(connector: str) -> Callable:
    def checker(server: MockDisplayServer) -> tuple:
        monitor = server.get_monitor(connector)
        if monitor and monitor.is_connected:
            return True, f"{connector} is enabled"
        return False, f"{connector} is not enabled"
    return checker


def check_scale(server: MockDisplayServer, connector: str, expected: float) -> tuple:
    monitor = server.get_monitor(connector)
    if monitor and abs(monitor.scale - expected) < 0.01:
        return True, f"{connector} scale is {expected}"
    return False, f"{connector} scale is not {expected}"


def check_position(server: MockDisplayServer, connector: str, expected_x: int, expected_y: int) -> tuple:
    monitor = server.get_monitor(connector)
    if monitor and monitor.position_x == expected_x and monitor.position_y == expected_y:
        return True, f"{connector} is at ({expected_x}, {expected_y})"
    return False, f"{connector} position is not ({expected_x}, {expected_y})"


def check_backlight(server: MockDisplayServer, connector: str, expected: int) -> tuple:
    monitor = server.get_monitor(connector)
    if monitor and monitor.backlight == expected:
        return True, f"{connector} backlight is {expected}"
    return False, f"{connector} backlight is not {expected}"


def check_rotation(server: MockDisplayServer, connector: str, expected: str) -> tuple:
    monitor = server.get_monitor(connector)
    if monitor and monitor.rotation == expected:
        return True, f"{connector} rotation is {expected}"
    return False, f"{connector} rotation is not {expected}"


def get_default_test_suite() -> TestSuite:
    suite = TestSuite(
        name="DisplayAgent Test Suite",
        description="Comprehensive test suite for DisplayAgent covering single/multi-monitor, X11/Wayland, and edge cases",
    )

    suite.add_case(TestCase(
        id="single_001",
        name="Set primary monitor",
        category=CaseCategory.SINGLE_MONITOR,
        description="Set HDMI-1 as the primary monitor",
        user_message="Set HDMI-1 as my primary monitor",
        initial_state_fn=create_single_monitor_setup,
        expected_checks=[check_primary_is_hdmi1],
        difficulty=1,
    ))

    suite.add_case(TestCase(
        id="single_002",
        name="Change resolution",
        category=CaseCategory.SINGLE_MONITOR,
        description="Change HDMI-1 resolution to 1920x1080",
        user_message="Change my display resolution to 1920x1080",
        initial_state_fn=create_single_monitor_setup,
        expected_checks=[check_mode_is_1920x1080("HDMI-1")],
        difficulty=1,
    ))

    suite.add_case(TestCase(
        id="single_003",
        name="Adjust backlight",
        category=CaseCategory.SINGLE_MONITOR,
        description="Set HDMI-1 backlight to 75",
        user_message="Dim my display to 75% brightness",
        initial_state_fn=create_single_monitor_setup,
        expected_checks=[lambda s: check_backlight(s, "HDMI-1", 75)],
        difficulty=1,
    ))

    suite.add_case(TestCase(
        id="single_004",
        name="Set scale factor",
        category=CaseCategory.SINGLE_MONITOR,
        description="Set HDMI-1 scale to 1.5 for HiDPI",
        user_message="Set scale to 1.5 for my HiDPI display",
        initial_state_fn=create_single_monitor_setup,
        expected_checks=[lambda s: check_scale(s, "HDMI-1", 1.5)],
        difficulty=1,
    ))

    suite.add_case(TestCase(
        id="single_005",
        name="Rotate monitor",
        category=CaseCategory.SINGLE_MONITOR,
        description="Rotate HDMI-1 to portrait mode",
        user_message="Rotate my display to portrait mode (left)",
        initial_state_fn=create_single_monitor_setup,
        expected_checks=[lambda s: check_rotation(s, "HDMI-1", "left")],
        difficulty=1,
    ))

    suite.add_case(TestCase(
        id="multi_001",
        name="Set different monitor as primary",
        category=CaseCategory.MULTI_MONITOR,
        description="Change primary from HDMI-1 to DP-1",
        user_message="Make DP-1 my primary monitor",
        initial_state_fn=create_dual_monitor_setup,
        expected_checks=[check_primary_is_dp1],
        difficulty=1,
    ))

    suite.add_case(TestCase(
        id="multi_002",
        name="Arrange monitors side by side",
        category=CaseCategory.MULTI_MONITOR,
        description="Position DP-1 to the right of HDMI-1",
        user_message="Put DP-1 to the right of my main monitor",
        initial_state_fn=create_dual_monitor_setup,
        expected_checks=[lambda s: check_position(s, "DP-1", 1920, 0)],
        difficulty=2,
    ))

    suite.add_case(TestCase(
        id="multi_003",
        name="Disable secondary monitor",
        category=CaseCategory.MULTI_MONITOR,
        description="Disable DP-1 monitor",
        user_message="Turn off my second monitor",
        initial_state_fn=create_dual_monitor_setup,
        expected_checks=[check_monitor_disabled("DP-1")],
        difficulty=1,
    ))

    suite.add_case(TestCase(
        id="multi_004",
        name="Enable disabled monitor",
        category=CaseCategory.MULTI_MONITOR,
        description="Re-enable DP-1 monitor",
        user_message="Turn my second monitor back on",
        initial_state_fn=lambda s: (create_dual_monitor_setup(s), s.get_monitor("DP-1").__setattr__("is_connected", False)),
        expected_checks=[check_monitor_enabled("DP-1")],
        difficulty=1,
    ))

    suite.add_case(TestCase(
        id="wayland_001",
        name="Wayland primary monitor",
        category=CaseCategory.WAYLAND_SPECIFIC,
        description="Set primary on Wayland",
        user_message="Set HDMI-A-1 as primary",
        initial_state_fn=create_wayland_setup,
        expected_checks=[lambda s: (s.get_monitor("HDMI-A-1").is_primary if s.get_monitor("HDMI-A-1") else False, "HDMI-A-1 primary check")],
        server_type=DisplayServerType.WAYLAND,
        difficulty=1,
    ))

    suite.add_case(TestCase(
        id="safety_001",
        name="Reject out-of-range backlight",
        category=CaseCategory.SAFETY,
        description="Reject backlight value > 100",
        user_message="Set my brightness to 150",
        initial_state_fn=create_single_monitor_setup,
        expected_checks=[lambda s: check_backlight(s, "HDMI-1", 100)],
        difficulty=2,
    ))

    suite.add_case(TestCase(
        id="safety_002",
        name="Reject invalid scale",
        category=CaseCategory.SAFETY,
        description="Reject scale value > 4.0",
        user_message="Set my display scale to 5.0",
        initial_state_fn=create_single_monitor_setup,
        expected_checks=[lambda s: check_scale(s, "HDMI-1", 1.0)],
        difficulty=2,
    ))

    suite.add_case(TestCase(
        id="edge_001",
        name="List all monitors",
        category=CaseCategory.EDGE_CASE,
        description="Query current monitor configuration",
        user_message="Show me my current monitor setup",
        initial_state_fn=create_dual_monitor_setup,
        expected_checks=[],
        difficulty=1,
    ))

    suite.add_case(TestCase(
        id="edge_002",
        name="Complex multi-step task",
        category=CaseCategory.EDGE_CASE,
        description="Set primary, resolution, and scale in one go",
        user_message="Make HDMI-1 primary, set it to 1080p, and use 1.25x scale",
        initial_state_fn=create_dual_monitor_setup,
        expected_checks=[
            check_primary_is_hdmi1,
            check_mode_is_1920x1080("HDMI-1"),
            lambda s: check_scale(s, "HDMI-1", 1.25),
        ],
        difficulty=3,
    ))

    return suite
