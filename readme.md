# Codex test repo

## Autonomous Codex agent loop

You can run Codex over a task list without manually prompting "continue" each time.
This repo now includes `agent_loop.py`, a resumable loop runner.

### 1) Create your two input files

`instructions.txt` (global guidance, reused each step):

```txt
Work in this repository.
Follow AGENTS.md instructions.
Run checks before finishing each task.
Commit changes only when a task is complete.
```

`tasks.txt` (one task per line):

```txt
Refactor the navbar HTML for accessibility labels.
Add tests for newsletter form validation.
Update documentation for local setup.
```

### 2) Run the loop

```bash
python agent_loop.py --tasks tasks.txt --instructions instructions.txt --max-steps 30
```

### 3) Resume anytime

The script writes `.agent-loop-state.json` so you can stop/restart without losing progress.

### Behavior

For each task, the loop asks Codex to:
- execute the task end-to-end,
- print `TASK_COMPLETE` when done,
- print `TASK_BLOCKED` if it cannot proceed,
- include a `NEXT_ACTION:` hint.

If Codex does not emit a completion/block marker, the loop stops to prevent drift.

### Notes

- You can customize the CLI command with `--codex-cmd`.
- This design keeps a human checkpoint for blockers while automating normal task progression.
