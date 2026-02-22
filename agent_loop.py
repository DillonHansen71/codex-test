#!/usr/bin/env python3
"""Run Codex in a lightweight autonomous loop over a task list.

The script repeatedly calls Codex with:
- shared global instructions,
- the next pending task,
- a request to mark completion and state what to do next.

It keeps a local state file so runs are resumable.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List


@dataclass
class TaskState:
    task: str
    status: str = "pending"  # pending|in_progress|done
    last_output: str = ""


@dataclass
class LoopState:
    tasks: List[TaskState]


def load_tasks(path: Path) -> List[str]:
    lines = [line.strip() for line in path.read_text().splitlines()]
    return [line for line in lines if line and not line.startswith("#")]


def load_or_init_state(state_path: Path, tasks_path: Path) -> LoopState:
    if state_path.exists():
        raw = json.loads(state_path.read_text())
        return LoopState(tasks=[TaskState(**item) for item in raw["tasks"]])

    tasks = [TaskState(task=task) for task in load_tasks(tasks_path)]
    state = LoopState(tasks=tasks)
    save_state(state_path, state)
    return state


def save_state(path: Path, state: LoopState) -> None:
    path.write_text(json.dumps(asdict(state), indent=2))


def next_pending_index(state: LoopState) -> int | None:
    for i, task in enumerate(state.tasks):
        if task.status != "done":
            return i
    return None


def build_prompt(global_instructions: str, task: str) -> str:
    return (
        f"{global_instructions}\n\n"
        f"Current task: {task}\n\n"
        "Do the task end-to-end. If complete, explicitly write 'TASK_COMPLETE'. "
        "If blocked, explicitly write 'TASK_BLOCKED' and explain the blocker. "
        "At the end, include a short 'NEXT_ACTION:' line."
    )


def run_codex(prompt: str, codex_cmd: str) -> subprocess.CompletedProcess[str]:
    cmd = [codex_cmd, "exec", prompt]
    return subprocess.run(cmd, text=True, capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Autonomous loop runner for Codex tasks")
    parser.add_argument("--tasks", default="tasks.txt", help="Task list file (one per line)")
    parser.add_argument(
        "--instructions",
        default="instructions.txt",
        help="Shared instructions prepended on every run",
    )
    parser.add_argument(
        "--state",
        default=".agent-loop-state.json",
        help="State JSON path for resumable progress",
    )
    parser.add_argument("--max-steps", type=int, default=20, help="Safety stop to avoid infinite loops")
    parser.add_argument("--codex-cmd", default="codex", help="Codex CLI command name")
    args = parser.parse_args()

    tasks_path = Path(args.tasks)
    instructions_path = Path(args.instructions)
    state_path = Path(args.state)

    if not tasks_path.exists():
        print(f"Missing tasks file: {tasks_path}", file=sys.stderr)
        return 1
    if not instructions_path.exists():
        print(f"Missing instructions file: {instructions_path}", file=sys.stderr)
        return 1

    global_instructions = instructions_path.read_text().strip()
    state = load_or_init_state(state_path, tasks_path)

    for step in range(1, args.max_steps + 1):
        idx = next_pending_index(state)
        if idx is None:
            print("All tasks complete.")
            return 0

        task_state = state.tasks[idx]
        task_state.status = "in_progress"
        save_state(state_path, state)

        prompt = build_prompt(global_instructions, task_state.task)
        print(f"\n=== Step {step}: task {idx + 1}/{len(state.tasks)} ===")
        print(task_state.task)

        result = run_codex(prompt, args.codex_cmd)
        output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
        task_state.last_output = output[-5000:]

        if result.returncode != 0:
            task_state.status = "pending"
            save_state(state_path, state)
            print(output)
            print("\nCodex command failed. Stopping loop.", file=sys.stderr)
            return result.returncode

        print(result.stdout)

        if "TASK_COMPLETE" in result.stdout:
            task_state.status = "done"
            save_state(state_path, state)
            continue

        if "TASK_BLOCKED" in result.stdout:
            task_state.status = "pending"
            save_state(state_path, state)
            print("Task reported blocked. Stopping so you can unblock it.")
            return 2

        task_state.status = "pending"
        save_state(state_path, state)
        print("Task did not signal completion. Stopping to avoid drift.")
        return 3

    print(f"Reached max steps ({args.max_steps}). Stopping for safety.")
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
