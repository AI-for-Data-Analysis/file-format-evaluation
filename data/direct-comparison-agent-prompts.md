# Direct Comparison Agent Prompts

This file is generated from local Codex JSONL session logs by
`extract_agent_prompts.py`.

## Shared Injected Context

The first user-role context message was **identical** across the two worker sessions.

It contained the project AGENTS.md instructions and environment context. The task-specific worker prompts below were the differing experimental prompts.

## Carson Task Prompt

Session: `019ec69e-fa32-7283-b6c6-fc26f2e1d8d8`

```text
You are Worker C in a controlled apples-to-apples format experiment. You are not alone in the codebase; do not revert or modify files outside your assigned write scope.

Workspace: /home/jessica-nash/analytics-accelerator/week-2-preparation
Assigned write scope only: agent-format-experiment/direct-notebook-agent/
Starter artifact: agent-format-experiment/direct-notebook-agent/analysis-notebook.ipynb

Task: Simulate a human-in-the-loop notebook analysis session using direct notebook editing. You must work directly on the existing .ipynb file. Do not create a notebook builder script. Do not wholesale regenerate the notebook from a separate script.

Use this dataset reference first: seattle-public-library/README.md. For analysis, use only seattle-public-library/combined_checkout_totals_by_month_usageclass.csv. Do not modify raw data.

Analysis question: How have Seattle Public Library physical vs digital checkout totals changed across complete years, and which recent complete year shows the largest digital share?

Required workflow:
1. Inspect the starter notebook structure directly with jq, nbformat, or equivalent targeted commands.
2. Edit the .ipynb directly with nbformat or structured JSON operations. Make incremental notebook edits: add or modify a few cells at a time.
3. Execute the notebook with the project environment after meaningful edits, using .venv/bin/jupyter or .venv/bin/python -m nbconvert. If sandbox blocks Jupyter kernel sockets, request escalation for the same execution command.
4. After execution, inspect targeted cell outputs from the .ipynb JSON, not full notebook dumps. Use the outputs to decide the interpretation.
5. Add or update a final markdown interpretation cell in the notebook based on those inspected outputs.
6. Save at least one chart and one CSV table under agent-format-experiment/direct-notebook-agent/reports/assets/ from notebook code.
7. Create agent-format-experiment/direct-notebook-agent/run-log.md with commands run, output cells inspected, and brief issues.

Constraints:
- No builder script for creating the notebook.
- Do not use terminal Python to compute analysis results outside the accepted notebook. Terminal Python may edit/validate the notebook structure only.
- Code should be explicit, readable pandas for a student with one semester of Python.
- Identify row meaning before plotting/interpreting.
- Use complete years only, requiring 12 months for both physical and digital.
- Keep the notebook concise: 5-9 cells.

Final response: list changed files, execution commands, output cells inspected, and a short summary of findings.
```

## Confucius Task Prompt

Session: `019ec69f-3714-7170-8901-7d4a0f4d47bb`

```text
You are Worker D in a controlled apples-to-apples format experiment. You are not alone in the codebase; do not revert or modify files outside your assigned write scope.

Workspace: /home/jessica-nash/analytics-accelerator/week-2-preparation
Assigned write scope only: agent-format-experiment/direct-py-cell-agent/
Starter artifact: agent-format-experiment/direct-py-cell-agent/analysis-cells.py

Task: Simulate the same human-in-the-loop analysis session using a VS Code/Jupyter percent-cell Python file. You must work directly on the existing .py file. Make incremental source edits and execute the script/cells to inspect outputs.

Use this dataset reference first: seattle-public-library/README.md. For analysis, use only seattle-public-library/combined_checkout_totals_by_month_usageclass.csv. Do not modify raw data.

Analysis question: How have Seattle Public Library physical vs digital checkout totals changed across complete years, and which recent complete year shows the largest digital share?

Required workflow:
1. Inspect the starter percent-cell file structure directly.
2. Edit analysis-cells.py directly. Make incremental edits: add or modify a few cells at a time.
3. Execute the file with .venv/bin/python after meaningful edits.
4. Inspect targeted terminal output and generated CSV/chart outputs. Use those outputs to decide the interpretation.
5. Add or update a final markdown/comment interpretation cell in analysis-cells.py based on inspected outputs.
6. Save at least one chart and one CSV table under agent-format-experiment/direct-py-cell-agent/reports/assets/ from the script code.
7. Create agent-format-experiment/direct-py-cell-agent/run-log.md with commands run, outputs inspected, and brief issues.

Constraints:
- Do not create a separate generator/builder script.
- Do not use terminal Python to compute analysis results outside the accepted .py analysis file. Terminal commands may inspect files and execute the .py file only.
- Code should be explicit, readable pandas for a student with one semester of Python.
- Identify row meaning before plotting/interpreting.
- Use complete years only, requiring 12 months for both physical and digital.
- Keep the percent-cell file concise: 5-9 cells.

Final response: list changed files, execution commands, outputs inspected, and a short summary of findings.
```
