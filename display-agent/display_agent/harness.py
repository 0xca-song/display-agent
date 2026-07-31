"""Harness layer: Constraint, Verify, Correct."""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
from enum import Enum
from datetime import datetime


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class OperationRisk:
    level: RiskLevel
    reason: str
    blocked: bool = False


class ConstraintEngine:
    def __init__(self):
        self._rules: List[Callable[[str, Dict[str, Any]], OperationRisk]] = []
        self._register_default_rules()

    def _register_default_rules(self) -> None:
        self._rules.append(self._backlight_range_check)
        self._rules.append(self._scale_range_check)
        self._rules.append(self._rotation_check)
        self._rules.append(self._mode_validity_check)

    @staticmethod
    def _backlight_range_check(
        tool_name: str, params: Dict[str, Any]
    ) -> OperationRisk:
        if tool_name == "set_backlight":
            value = params.get("value")
            if value is not None:
                if not 0 <= value <= 100:
                    return OperationRisk(
                        level=RiskLevel.HIGH,
                        reason=f"Backlight value {value} out of safe range (0-100)",
                        blocked=True,
                    )
        return OperationRisk(level=RiskLevel.LOW, reason="OK")

    @staticmethod
    def _scale_range_check(
        tool_name: str, params: Dict[str, Any]
    ) -> OperationRisk:
        if tool_name == "set_scale":
            scale = params.get("scale")
            if scale is not None:
                if not 0.25 <= scale <= 4.0:
                    return OperationRisk(
                        level=RiskLevel.HIGH,
                        reason=f"Scale {scale} out of safe range (0.25-4.0)",
                        blocked=True,
                    )
        return OperationRisk(level=RiskLevel.LOW, reason="OK")

    @staticmethod
    def _rotation_check(
        tool_name: str, params: Dict[str, Any]
    ) -> OperationRisk:
        if tool_name == "set_rotation":
            rotation = params.get("rotation")
            valid_rotations = ["normal", "left", "right", "inverted"]
            if rotation and rotation not in valid_rotations:
                return OperationRisk(
                    level=RiskLevel.MEDIUM,
                    reason=f"Invalid rotation '{rotation}'. Must be one of: {valid_rotations}",
                    blocked=True,
                )
        return OperationRisk(level=RiskLevel.LOW, reason="OK")

    @staticmethod
    def _mode_validity_check(
        tool_name: str, params: Dict[str, Any]
    ) -> OperationRisk:
        if tool_name == "set_mode":
            mode = params.get("mode")
            if mode:
                if "@" in mode:
                    try:
                        parts = mode.split("@")
                        width, height = int(parts[0].split("x")[0]), int(parts[0].split("x")[1])
                        rate = float(parts[1])
                        if width <= 0 or height <= 0:
                            return OperationRisk(
                                level=RiskLevel.HIGH,
                                reason=f"Invalid resolution {width}x{height}",
                                blocked=True,
                            )
                        if rate <= 0 or rate > 500:
                            return OperationRisk(
                                level=RiskLevel.HIGH,
                                reason=f"Invalid refresh rate {rate}Hz",
                                blocked=True,
                            )
                    except (ValueError, IndexError):
                        return OperationRisk(
                            level=RiskLevel.MEDIUM,
                            reason=f"Malformed mode string: {mode}. Expected format: WIDTHxHEIGHT@RATE",
                            blocked=True,
                        )
        return OperationRisk(level=RiskLevel.LOW, reason="OK")

    def check(self, tool_name: str, params: Dict[str, Any]) -> OperationRisk:
        for rule in self._rules:
            risk = rule(tool_name, params)
            if risk.level != RiskLevel.LOW:
                return risk
        return OperationRisk(level=RiskLevel.LOW, reason="All checks passed")


class VerifyEngine:
    def __init__(self):
        self.verification_history: List[Dict[str, Any]] = []

    def verify_tool_result(
        self,
        tool_name: str,
        params: Dict[str, Any],
        result: Any,
        expected_state: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        if result is None:
            return False, "Tool returned no result"

        if hasattr(result, "success"):
            if not result.success:
                return False, f"Tool failed: {getattr(result, 'error', 'Unknown error')}"

        if expected_state:
            for key, expected in expected_state.items():
                actual = result.get(key) if isinstance(result, dict) else getattr(result, key, None)
                if actual != expected:
                    return False, f"State mismatch for '{key}': expected {expected}, got {actual}"

        self.verification_history.append({
            "timestamp": datetime.now().isoformat(),
            "tool_name": tool_name,
            "params": params,
            "verified": True,
        })

        return True, "Verification passed"

    def add_verification_log(self, entry: Dict[str, Any]) -> None:
        self.verification_history.append(entry)


class CorrectEngine:
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self.retry_history: List[Dict[str, Any]] = []
        self._recovery_strategies: Dict[str, Callable] = {}

    def register_recovery(self, failure_pattern: str, recovery_fn: Callable) -> None:
        self._recovery_strategies[failure_pattern] = recovery_fn

    def should_retry(
        self,
        tool_name: str,
        attempt: int,
        error: str,
    ) -> bool:
        if attempt >= self.max_retries:
            self.retry_history.append({
                "timestamp": datetime.now().isoformat(),
                "tool_name": tool_name,
                "attempt": attempt,
                "error": error,
                "action": "max_retries_exceeded",
            })
            return False

        retryable_patterns = [
            "connection timeout",
            "resource busy",
            "temporarily unavailable",
        ]
        for pattern in retryable_patterns:
            if pattern.lower() in error.lower():
                self.retry_history.append({
                    "timestamp": datetime.now().isoformat(),
                    "tool_name": tool_name,
                    "attempt": attempt,
                    "error": error,
                    "action": "retry",
                })
                return True

        self.retry_history.append({
            "timestamp": datetime.now().isoformat(),
            "tool_name": tool_name,
            "attempt": attempt,
            "error": error,
            "action": "no_retry",
        })
        return False

    def get_recovery_suggestion(self, error: str) -> Optional[str]:
        error_lower = error.lower()
        if "not found" in error_lower or "does not exist" in error_lower:
            return "Check if the monitor connector name is correct. Use list_monitors to see available monitors."
        if "not supported" in error_lower or "invalid" in error_lower:
            return "Check the parameter value is within supported range. Use get_monitor_info to see valid options."
        if "permission denied" in error_lower:
            return "This operation may require elevated privileges. Try running with appropriate permissions."
        return None


@dataclass
class Harness:
    constraint: ConstraintEngine = field(default_factory=ConstraintEngine)
    verify: VerifyEngine = field(default_factory=VerifyEngine)
    correct: CorrectEngine = field(default_factory=CorrectEngine)

    def check_operation(self, tool_name: str, params: Dict[str, Any]) -> OperationRisk:
        return self.constraint.check(tool_name, params)

    def verify_result(
        self,
        tool_name: str,
        params: Dict[str, Any],
        result: Any,
        expected_state: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        return self.verify.verify_tool_result(tool_name, params, result, expected_state)

    def should_retry(self, tool_name: str, attempt: int, error: str) -> bool:
        return self.correct.should_retry(tool_name, attempt, error)

    def get_recovery_suggestion(self, error: str) -> Optional[str]:
        return self.correct.get_recovery_suggestion(error)
