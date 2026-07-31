#!/usr/bin/env python3
"""Evaluation runner for DisplayAgent."""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from display_agent.mock.display_server import MockDisplayServer
from display_agent.tools import ToolRegistry
from display_agent.agent import DisplayAgent
from display_agent.context import ContextManager
from display_agent.harness import Harness
from eval.cases import get_default_test_suite
from eval.judge import LLMasJudge, run_evaluation_suite, print_evaluation_report, JudgeModel


def parse_args():
    parser = argparse.ArgumentParser(description="Run DisplayAgent evaluation suite")
    parser.add_argument(
        "--use-judge",
        action="store_true",
        help="Use LLM-as-Judge for evaluation",
    )
    parser.add_argument(
        "--judge-model",
        choices=["anthropic", "openai", "mock"],
        default="mock",
        help="Judge model provider",
    )
    parser.add_argument(
        "--api-key",
        help="API key for judge model",
    )
    parser.add_argument(
        "--model-name",
        default="claude-sonnet-4-20250514",
        help="Model name for judge",
    )
    parser.add_argument(
        "--output",
        help="Output JSON file for results",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print verbose output",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    mock_server = MockDisplayServer()
    tool_registry = ToolRegistry(mock_server=mock_server)
    harness = Harness()
    context = ContextManager()
    agent = DisplayAgent(
        tool_registry=tool_registry,
        context_manager=context,
        harness=harness,
    )

    suite = get_default_test_suite()

    judge = None
    if args.use_judge:
        judge_model = JudgeModel(args.judge_model)
        judge = LLMasJudge(
            model=judge_model,
            api_key=args.api_key,
            model_name=args.model_name,
        )

    print(f"Running evaluation suite: {suite.name}")
    print(f"Total test cases: {len(suite.cases)}")
    print(f"LLM-as-Judge: {'Enabled' if judge else 'Disabled'}")
    print()

    results = run_evaluation_suite(
        suite=suite,
        agent=agent,
        mock_server=mock_server,
        judge=judge,
        use_judge=args.use_judge,
    )

    print_evaluation_report(results)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to: {args.output}")

    if results["pass_rate"] >= 0.8:
        print("\n[SUCCESS] Pass rate >= 80%")
        sys.exit(0)
    else:
        print(f"\n[FAILED] Pass rate {results['pass_rate']:.1%} < 80%")
        sys.exit(1)


if __name__ == "__main__":
    main()
