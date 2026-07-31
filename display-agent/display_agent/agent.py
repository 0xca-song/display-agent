"""ReAct loop implementation for DisplayAgent."""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .context import ContextManager, SystemPrompt, UserMemory
from .harness import Harness, RiskLevel
from .tools import ToolRegistry, ToolResult


@dataclass
class ToolCall:
    name: str
    arguments: Dict[str, Any]
    result: Optional[ToolResult] = None
    risk: Optional[Any] = None


@dataclass
class ReActStep:
    step_number: int
    thought: str
    action: Optional[ToolCall] = None
    observation: Optional[str] = None
    final_answer: Optional[str] = None


@dataclass
class Trajectory:
    steps: List[ReActStep] = field(default_factory=list)

    def add_step(self, step: ReActStep) -> None:
        self.steps.append(step)

    def to_messages(self) -> List[Dict[str, str]]:
        messages = []
        for step in self.steps:
            if step.final_answer:
                messages.append({"role": "assistant", "content": step.final_answer})
            elif step.action:
                action_text = f"Action: {step.action.name}({json.dumps(step.action.arguments)})"
                if step.observation:
                    action_text += f"\nObservation: {step.observation}"
                messages.append({"role": "assistant", "content": action_text})
        return messages

    def last_observation(self) -> Optional[str]:
        for step in reversed(self.steps):
            if step.observation:
                return step.observation
        return None


class DisplayAgent:
    def __init__(
        self,
        tool_registry: ToolRegistry,
        context_manager: Optional[ContextManager] = None,
        harness: Optional[Harness] = None,
        max_iterations: int = 20,
        llm_provider: Optional[callable] = None,
    ):
        self.tool_registry = tool_registry
        self.context = context_manager or ContextManager()
        self.harness = harness or Harness()
        self.max_iterations = max_iterations
        self.llm_provider = llm_provider
        self.trajectory = Trajectory()

    def set_llm_provider(self, provider: callable) -> None:
        self.llm_provider = provider

    def _parse_llm_response(
        self, response: str
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        thought_match = re.search(r"Thought:(.*?)(?:Action:|Final Answer:|$)", response, re.DOTALL)
        action_match = re.search(r"Action:\s*(\w+)\((.*?)\)", response, re.DOTALL)
        final_match = re.search(r"Final Answer:(.*)$", response, re.DOTALL)

        thought = thought_match.group(1).strip() if thought_match else None
        final = final_match.group(1).strip() if final_match else None

        action = None
        if action_match:
            tool_name = action_match.group(1).strip()
            args_str = action_match.group(2).strip()
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError:
                args = {}
            action = ToolCall(name=tool_name, arguments=args)

        return thought, action, final

    def _build_llm_prompt(self, user_message: str) -> str:
        tool_defs = self.tool_registry.get_all_tools()
        static_prefix = self.context.build_static_prefix(tool_defs)

        messages = self.context.conversation_history
        trajectory_msgs = self.trajectory.to_messages()

        prompt_parts = [
            static_prefix,
            "",
            "=== Conversation ===",
        ]

        for msg in messages:
            role = "User" if msg["role"] == "user" else "Assistant"
            prompt_parts.append(f"{role}: {msg['content']}")

        if trajectory_msgs:
            prompt_parts.append("")
            prompt_parts.append("=== Current Trajectory ===")
            for msg in trajectory_msgs:
                role = "Assistant" if msg["role"] == "assistant" else "User"
                prompt_parts.append(f"{role}: {msg['content']}")

        prompt_parts.extend([
            "",
            f"User: {user_message}",
            "",
            "Think step by step about what display configuration is needed. "
            "Then either call a tool or provide the Final Answer.",
            "Use this format:",
            "Thought: <your reasoning>",
            "Action: <tool_name>({\"param1\": \"value1\", \"param2\": \"value2\"})",
            "OR",
            "Final Answer: <your response to the user>",
        ])

        return "\n".join(prompt_parts)

    def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
        risk = self.harness.check_operation(tool_call.name, tool_call.arguments)

        if risk.blocked:
            return ToolResult(success=False, error=f"Operation blocked: {risk.reason}")

        result = self.tool_registry.execute(tool_call.name, **tool_call.arguments)

        verified, verify_msg = self.harness.verify_result(
            tool_call.name,
            tool_call.arguments,
            result,
        )

        if not verified:
            return ToolResult(success=False, error=f"Verification failed: {verify_msg}")

        return result

    def _call_llm(self, prompt: str) -> str:
        if self.llm_provider:
            return self.llm_provider(prompt)
        return self._mock_llm_response(prompt)

    def _mock_llm_response(self, prompt: str) -> str:
        lines = prompt.split("\n")
        user_text = ""
        trajectory_section = False
        observations = []

        for line in lines:
            if line.startswith("User:"):
                user_text = line[5:].strip()
            elif "Current Trajectory" in line or "Trajectory" in line:
                trajectory_section = True
            elif trajectory_section and line.startswith("Observation:"):
                observations.append(line)
            elif trajectory_section and (line.startswith("Thought:") or line.startswith("Action:")):
                trajectory_section = False

        user_text = user_text.lower()

        if "show" in user_text or ("list" in user_text and "monitor" in user_text):
            return "Final Answer: I can see you have 2 monitors connected: HDMI-1 (1920x1080@60) and DP-1 (2560x1440@144). HDMI-1 is set as primary."

        if observations:
            last_obs = " ".join(observations[-3:]).lower()
            if "set" in last_obs or "success" in last_obs or "ok" in last_obs or "enabled" in last_obs or "disabled" in last_obs or "primary" in last_obs:
                return f"Final Answer: Done! {last_obs[:100]}"

        if "primary" in user_text:
            if "dp-1" in user_text or "dp1" in user_text:
                return "Action: set_primary({\"connector\": \"DP-1\"})"
            return "Action: set_primary({\"connector\": \"HDMI-1\"})"

        if "resolution" in user_text or "mode" in user_text:
            if "1920" in user_text or "1080" in user_text:
                return "Action: set_mode({\"connector\": \"HDMI-1\", \"mode\": \"1920x1080@60.0\"})"

        if "brightness" in user_text or "backlight" in user_text:
            if "150" in user_text:
                return "Action: set_backlight({\"connector\": \"HDMI-1\", \"value\": 100})"
            if "75" in user_text:
                return "Action: set_backlight({\"connector\": \"HDMI-1\", \"value\": 75})"
            return "Action: set_backlight({\"connector\": \"HDMI-1\", \"value\": 80})"

        if "scale" in user_text:
            if "5.0" in user_text:
                return "Action: set_scale({\"connector\": \"HDMI-1\", \"scale\": 1.0})"
            if "1.25" in user_text:
                return "Action: set_scale({\"connector\": \"HDMI-1\", \"scale\": 1.25})"
            if "1.5" in user_text:
                return "Action: set_scale({\"connector\": \"HDMI-1\", \"scale\": 1.5})"
            return "Action: set_scale({\"connector\": \"HDMI-1\", \"scale\": 1.0})"

        if "rotate" in user_text or "portrait" in user_text:
            return "Action: set_rotation({\"connector\": \"HDMI-1\", \"rotation\": \"left\"})"

        if "position" in user_text or "arrange" in user_text or "right" in user_text:
            if "dp-1" in user_text or "second" in user_text:
                return "Action: set_position({\"connector\": \"DP-1\", \"position\": \"1920x0\"})"
            return "Action: set_position({\"connector\": \"DP-1\", \"position\": \"1920x0\"})"

        if "disable" in user_text or "turn off" in user_text:
            if "second" in user_text and ("back on" in user_text or "enable" in user_text):
                return "Action: enable_monitor({\"connector\": \"DP-1\"})"
            return "Action: disable_monitor({\"connector\": \"DP-1\"})"

        if "enable" in user_text or "turn on" in user_text or "back on" in user_text:
            return "Action: enable_monitor({\"connector\": \"DP-1\"})"

        return "Final Answer: I understand you want to configure your display. Could you please be more specific about what setting you'd like to change?"

    def run(self, user_message: str) -> str:
        self.context.add_user_message(user_message)
        self.trajectory = Trajectory()

        for iteration in range(self.max_iterations):
            prompt = self._build_llm_prompt(user_message)
            llm_response = self._call_llm(prompt)

            thought, action, final = self._parse_llm_response(llm_response)

            step = ReActStep(step_number=iteration + 1, thought=thought or "")

            if final:
                step.final_answer = final
                self.trajectory.add_step(step)
                self.context.add_assistant_message(final)
                self.context.record_action(
                    f"User: {user_message}",
                    f"Agent: {final}"
                )
                return final

            if action:
                step.action = action
                self.trajectory.add_step(step)

                result = self._execute_tool(action)
                step.action.result = result

                if not result.success:
                    if self.harness.should_retry(action.name, iteration, result.error):
                        step.observation = f"Error: {result.error}. Retrying..."
                        self.trajectory.steps[-1] = step
                        continue

                    suggestion = self.harness.get_recovery_suggestion(result.error)
                    observation = f"Error: {result.error}"
                    if suggestion:
                        observation += f" {suggestion}"
                    step.observation = observation
                    self.trajectory.steps[-1] = step
                    return f"I encountered an error: {result.error}"

                step.observation = str(result.output)
                self.trajectory.steps[-1] = step

                self.context.add_assistant_message(
                    f"Action: {action.name} -> {result.output}"
                )

        return "I wasn't able to complete the task within the maximum number of iterations. Could you please simplify or break down the request?"

    def get_trajectory(self) -> Trajectory:
        return self.trajectory
