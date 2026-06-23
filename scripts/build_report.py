from __future__ import annotations

import csv
import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SANITIZED_LOG_DIR = ROOT / "sanitized-logs"
OUTPUT = ROOT / "index.html"
PRINT_OUTPUT = ROOT / "report-print.html"

RATES = {
    "fresh_input": 5.00 / 1_000_000,
    "cached_input": 0.50 / 1_000_000,
    "output": 30.00 / 1_000_000,
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def fmt_int(value: str | int | float) -> str:
    return f"{int(float(value)):,}"


def fmt_usd(value: str | float) -> str:
    return f"${float(value):.2f}"


def parse_log(path: Path) -> dict[str, object]:
    events = []
    tool_counts: dict[str, int] = {}
    tool_records = []
    first_worker_prompt = ""
    duration_ms = None
    for line in path.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        payload = item.get("payload", {})
        if item.get("type") == "event_msg" and payload.get("type") == "token_count":
            events.append(payload["info"]["last_token_usage"])
        if item.get("type") == "event_msg" and payload.get("type") == "task_complete":
            duration_ms = payload.get("duration_ms")
        if item.get("type") == "response_item":
            if payload.get("type") in {"function_call", "custom_tool_call"}:
                name = payload.get("name", "unknown")
                tool_counts[name] = tool_counts.get(name, 0) + 1
                arguments = payload.get("arguments") or payload.get("input") or ""
                command = ""
                if payload.get("arguments"):
                    try:
                        command = json.loads(payload["arguments"]).get("cmd", "")
                    except json.JSONDecodeError:
                        command = payload.get("arguments", "")
                tool_records.append(
                    {
                        "name": name,
                        "command": command,
                        "text": arguments,
                    }
                )
            if payload.get("type") == "message" and payload.get("role") == "user":
                for part in payload.get("content") or []:
                    text = part.get("text", "")
                    if text.startswith("You are Worker"):
                        first_worker_prompt = text
    return {
        "events": events,
        "tool_counts": tool_counts,
        "tool_records": tool_records,
        "duration_ms": duration_ms,
        "first_worker_prompt": first_worker_prompt,
    }


def token_usage_from_events(events: list[dict[str, int]]) -> dict[str, int]:
    input_tokens = sum(event["input_tokens"] for event in events)
    cached_input_tokens = sum(event["cached_input_tokens"] for event in events)
    output_tokens = sum(event["output_tokens"] for event in events)
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "non_cached_input_tokens": input_tokens - cached_input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


def assert_usage_matches_csv(agent: str, csv_row: dict[str, str], events: list[dict[str, int]]) -> None:
    usage = token_usage_from_events(events)
    fields = [
        "input_tokens",
        "cached_input_tokens",
        "non_cached_input_tokens",
        "output_tokens",
        "total_tokens",
    ]
    mismatches = [
        f"{field}: csv={csv_row[field]} log={usage[field]}"
        for field in fields
        if int(csv_row[field]) != usage[field]
    ]
    if mismatches:
        joined = "; ".join(mismatches)
        raise ValueError(f"Token usage mismatch for {agent}: {joined}")


def cost_from_usage(usage: dict[str, int | str]) -> float:
    return (
        int(usage["non_cached_input_tokens"]) * RATES["fresh_input"]
        + int(usage["cached_input_tokens"]) * RATES["cached_input"]
        + int(usage["output_tokens"]) * RATES["output"]
    )


def ratio_summary(
    notebook: dict[str, int | float | str],
    py: dict[str, int | float | str],
    normalized_cost_ratio: float | None = None,
) -> list[dict[str, float | str]]:
    rows = [
        ("Total tokens", "total_tokens"),
        ("Fresh input", "non_cached_input_tokens"),
        ("Output tokens", "output_tokens"),
        ("Model calls", "model_calls"),
        ("Runtime", "duration_ms"),
        ("Observed cost", "observed_cost"),
    ]
    summary = [
        {
            "metric": label,
            "ratio": float(notebook[field]) / float(py[field]),
        }
        for label, field in rows
    ]
    if normalized_cost_ratio is not None:
        summary.append({"metric": "Normalized cost", "ratio": normalized_cost_ratio})
    return summary


def normalize_first_call_cache(events: list[dict[str, int]], cached_tokens: int = 41_344) -> dict[str, int]:
    adjusted = [dict(event) for event in events]
    adjusted[0]["cached_input_tokens"] = cached_tokens
    return token_usage_from_events(adjusted)


def broad_controlled_category(category: str) -> str:
    if "edit" in category:
        return "Source edit"
    if "source inspection" in category:
        return "Source inspection"
    if "execution" in category:
        return "Execution"
    if "output" in category:
        return "Output inspection"
    if "structure validation" in category:
        return "Notebook structure validation"
    if "report/log write" in category:
        return "Report/log writing"
    if category in {"environment check", "filesystem/navigation", "final status check", "schema reference"}:
        return "Setup, schema, or status"
    return "Other"


def native_tool_category(record: dict[str, str], workflow: str) -> str:
    name = record["name"]
    command = record["command"].lower()
    text = record["text"].lower()
    combined = f"{command}\n{text}"
    if name == "apply_patch":
        if "run-log" in combined or "analysis-report" in combined or "report.md" in combined:
            return "Report/log writing"
        return "Source edit"
    if "nbconvert" in command or "build_notebook.py" in command or "analysis-cells.py" in command:
        return "Execution"
    if "readme.md" in command and "seattle-public-library" in command:
        return "Setup, schema, or status"
    if any(term in command for term in ["pwd", "rg --files", "ls ", "find ", "git status", "mkdir", "pip list"]):
        return "Setup, schema, or status"
    if any(term in command for term in ["reports/assets", ".csv", ".png", ".svg"]):
        return "Output inspection"
    if "ipynb" in command or "nbformat" in command:
        return "Notebook structure validation" if "notebook" in workflow.lower() else "Source inspection"
    if any(term in command for term in ["sed ", "head ", "tail ", "cat ", "nl "]):
        return "Source inspection"
    if name == "write_stdin":
        return "Execution"
    return "Other"


def count_categories(rows: list[tuple[str, str]]) -> list[dict[str, object]]:
    counts: dict[tuple[str, str], int] = {}
    for workflow, category in rows:
        key = (workflow, category)
        counts[key] = counts.get(key, 0) + 1
    return [
        {"workflow": workflow, "category": category, "count": count}
        for (workflow, category), count in sorted(counts.items())
    ]


def duration_label(ms: int | str) -> str:
    seconds = int(ms) // 1000
    return f"{seconds // 60}m {seconds % 60}s"


def extract_prompt(prompt_markdown: str, heading: str) -> str:
    marker = f"## {heading}"
    start = prompt_markdown.index(marker)
    fence_start = prompt_markdown.index("```text", start) + len("```text")
    fence_end = prompt_markdown.index("```", fence_start)
    return prompt_markdown[fence_start:fence_end].strip()


def build_controlled_turn_specs(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    sessions = [("Carson", "Direct .ipynb"), ("Confucius", "Percent-cell .py")]
    specs = []
    for rank, (agent, workflow) in enumerate(sessions, start=1):
        session_rows = [row for row in rows if row["session_title"].startswith(agent)]
        session_rows.sort(key=lambda row: int(row["turn_index"]))
        specs.append(
            {
                "rank": rank,
                "agent": agent,
                "workflow": workflow,
                "turns": [
                    {
                        "turn": int(row["turn_index"]),
                        "delta": int(row["token_delta"]),
                        "input": int(row["turn_input_tokens"]),
                        "cached_input": int(row["turn_cached_input_tokens"]),
                        "fresh_input": int(row["turn_uncached_input_tokens"]),
                        "output": int(row["turn_output_tokens"]),
                    }
                    for row in session_rows
                ],
            }
        )
    return specs


def html_rows(rows: list[list[str | int | float]]) -> str:
    return "\n".join(
        "<tr>" + "".join(f"<td>{html.escape(str(cell))}</td>" for cell in row) + "</tr>"
        for row in rows
    )


def nice_number(value: float) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.0f}K"
    if value >= 10:
        return f"{value:.0f}"
    return f"{value:.1f}"


def static_grouped_bar_svg(
    labels: list[str],
    series: list[tuple[str, list[float], str]],
    y_title: str,
    width: int = 900,
    height: int = 430,
) -> str:
    left = 90
    right = 30
    top = 35
    bottom = 95
    plot_width = width - left - right
    plot_height = height - top - bottom
    max_value = max(max(values) for _, values, _ in series) * 1.12
    group_width = plot_width / len(labels)
    bar_width = min(44, group_width / (len(series) + 1.2))
    parts = [
        f'<svg class="static-chart" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(y_title)} chart">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<line x1="{left}" y1="{top + plot_height}" x2="{width - right}" y2="{top + plot_height}" stroke="#333"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#333"/>',
        f'<text x="18" y="{top + plot_height / 2}" transform="rotate(-90 18 {top + plot_height / 2})" font-size="14" fill="#262626">{html.escape(y_title)}</text>',
    ]
    for tick in range(5):
        value = max_value * tick / 4
        y = top + plot_height - (value / max_value * plot_height)
        parts.append(f'<line x1="{left - 5}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="#e2e6ed"/>')
        parts.append(f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" font-size="12" fill="#444">{nice_number(value)}</text>')
    for label_index, label in enumerate(labels):
        group_center = left + group_width * (label_index + 0.5)
        parts.append(f'<text x="{group_center:.1f}" y="{height - 45}" text-anchor="middle" font-size="13" fill="#262626">{html.escape(label)}</text>')
        start_x = group_center - (bar_width * len(series)) / 2
        for series_index, (_, values, color) in enumerate(series):
            value = values[label_index]
            bar_height = value / max_value * plot_height
            x = start_x + series_index * bar_width
            y = top + plot_height - bar_height
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width * 0.82:.1f}" height="{bar_height:.1f}" fill="{color}" opacity="0.85"/>')
            parts.append(f'<text x="{x + bar_width * 0.41:.1f}" y="{y - 5:.1f}" text-anchor="middle" font-size="11" fill="#262626">{nice_number(value)}</text>')
    legend_x = left
    for name, _, color in series:
        parts.append(f'<rect x="{legend_x}" y="12" width="14" height="14" fill="{color}" opacity="0.85"/>')
        parts.append(f'<text x="{legend_x + 20}" y="24" font-size="13" fill="#262626">{html.escape(name)}</text>')
        legend_x += 190
    parts.append("</svg>")
    return "\n".join(parts)


def static_single_bar_svg(labels: list[str], values: list[float], y_title: str, color: str = "#012169") -> str:
    return static_grouped_bar_svg(labels, [("Notebook / percent-cell", values, color)], y_title)


def static_stacked_bar_svg(
    labels: list[str],
    cached: list[float],
    fresh: list[float],
    y_title: str = "Input tokens",
    width: int = 900,
    height: int = 430,
) -> str:
    left = 90
    right = 25
    top = 35
    bottom = 75
    plot_width = width - left - right
    plot_height = height - top - bottom
    totals = [a + b for a, b in zip(cached, fresh)]
    max_value = max(totals) * 1.12
    bar_width = max(10, min(28, plot_width / len(labels) * 0.68))
    step = plot_width / len(labels)
    parts = [
        f'<svg class="static-chart" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(y_title)} chart">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<line x1="{left}" y1="{top + plot_height}" x2="{width - right}" y2="{top + plot_height}" stroke="#333"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#333"/>',
        f'<text x="18" y="{top + plot_height / 2}" transform="rotate(-90 18 {top + plot_height / 2})" font-size="14" fill="#262626">{html.escape(y_title)}</text>',
    ]
    for tick in range(5):
        value = max_value * tick / 4
        y = top + plot_height - (value / max_value * plot_height)
        parts.append(f'<line x1="{left - 5}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="#e2e6ed"/>')
        parts.append(f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" font-size="12" fill="#444">{nice_number(value)}</text>')
    for idx, label in enumerate(labels):
        x = left + step * idx + (step - bar_width) / 2
        fresh_height = fresh[idx] / max_value * plot_height
        cached_height = cached[idx] / max_value * plot_height
        y_fresh = top + plot_height - fresh_height
        y_cached = y_fresh - cached_height
        parts.append(f'<rect x="{x:.1f}" y="{y_cached:.1f}" width="{bar_width:.1f}" height="{cached_height:.1f}" fill="#012169" opacity="0.85"/>')
        parts.append(f'<rect x="{x:.1f}" y="{y_fresh:.1f}" width="{bar_width:.1f}" height="{fresh_height:.1f}" fill="#339898" opacity="0.85"/>')
        if idx % max(1, len(labels) // 12) == 0:
            parts.append(f'<text x="{x + bar_width / 2:.1f}" y="{height - 42}" text-anchor="middle" font-size="11" fill="#262626">{html.escape(label)}</text>')
    parts.append('<rect x="90" y="12" width="14" height="14" fill="#012169" opacity="0.85"/><text x="110" y="24" font-size="13" fill="#262626">Cached input</text>')
    parts.append('<rect x="225" y="12" width="14" height="14" fill="#339898" opacity="0.85"/><text x="245" y="24" font-size="13" fill="#262626">Fresh input</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def static_horizontal_grouped_bar_svg(
    rows: list[dict[str, object]],
    x_title: str = "Tool calls",
    width: int = 900,
    height: int = 440,
) -> str:
    categories = sorted({str(row["category"]) for row in rows})
    workflows = list(dict.fromkeys(str(row["workflow"]) for row in rows))
    colors = ["#012169", "#c84e00", "#339898"]
    left = 220
    right = 35
    top = 40
    bottom = 55
    plot_width = width - left - right
    plot_height = height - top - bottom
    max_value = max(int(row["count"]) for row in rows) * 1.2
    group_height = plot_height / len(categories)
    bar_height = min(20, group_height / (len(workflows) + 1.1))
    parts = [
        f'<svg class="static-chart" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(x_title)} chart">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#333"/>',
        f'<line x1="{left}" y1="{top + plot_height}" x2="{width - right}" y2="{top + plot_height}" stroke="#333"/>',
        f'<text x="{left + plot_width / 2}" y="{height - 14}" text-anchor="middle" font-size="14" fill="#262626">{html.escape(x_title)}</text>',
    ]
    for tick in range(5):
        value = max_value * tick / 4
        x = left + value / max_value * plot_width
        parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_height}" stroke="#e2e6ed"/>')
        parts.append(f'<text x="{x:.1f}" y="{top + plot_height + 18}" text-anchor="middle" font-size="12" fill="#444">{nice_number(value)}</text>')
    for category_index, category in enumerate(categories):
        y_center = top + group_height * (category_index + 0.5)
        parts.append(f'<text x="{left - 10}" y="{y_center + 4:.1f}" text-anchor="end" font-size="12" fill="#262626">{html.escape(category)}</text>')
        start_y = y_center - (bar_height * len(workflows)) / 2
        for workflow_index, workflow in enumerate(workflows):
            match = next((row for row in rows if row["workflow"] == workflow and row["category"] == category), None)
            value = int(match["count"]) if match else 0
            bar_width = value / max_value * plot_width
            y = start_y + workflow_index * bar_height
            parts.append(f'<rect x="{left}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_height * 0.82:.1f}" fill="{colors[workflow_index % len(colors)]}" opacity="0.85"/>')
            if value:
                parts.append(f'<text x="{left + bar_width + 4:.1f}" y="{y + bar_height * 0.65:.1f}" font-size="11" fill="#262626">{value}</text>')
    legend_x = left
    for workflow_index, workflow in enumerate(workflows):
        parts.append(f'<rect x="{legend_x}" y="12" width="14" height="14" fill="{colors[workflow_index % len(colors)]}" opacity="0.85"/>')
        parts.append(f'<text x="{legend_x + 20}" y="24" font-size="13" fill="#262626">{html.escape(workflow)}</text>')
        legend_x += 275
    parts.append("</svg>")
    return "\n".join(parts)


def build_html(print_mode: bool = False) -> str:
    controlled_usage_rows = read_csv(DATA_DIR / "direct-comparison-token-usage.csv")
    controlled_cost_rows = read_csv(DATA_DIR / "direct-comparison-api-costs.csv")
    controlled_turn_rows = read_csv(DATA_DIR / "model-call-token-events.csv")
    controlled_tool_rows = read_csv(DATA_DIR / "direct-comparison-tool-call-summary.csv")
    native_usage_rows = read_csv(DATA_DIR / "agent-native-token-usage.csv")

    raw_logs = {
        "Boyle": SANITIZED_LOG_DIR / "agent-native" / "boyle-notebook.jsonl",
        "Laplace": SANITIZED_LOG_DIR / "agent-native" / "laplace-percent-cell.jsonl",
        "Carson": SANITIZED_LOG_DIR / "notebook-carson.jsonl",
        "Confucius": SANITIZED_LOG_DIR / "percent-cell-confucius.jsonl",
    }
    logs = {agent: parse_log(path) for agent, path in raw_logs.items()}

    prompt_markdown = (DATA_DIR / "direct-comparison-agent-prompts.md").read_text(encoding="utf-8")
    prompts = {
        "Boyle": logs["Boyle"]["first_worker_prompt"],
        "Laplace": logs["Laplace"]["first_worker_prompt"],
        "Carson": extract_prompt(prompt_markdown, "Carson Task Prompt"),
        "Confucius": extract_prompt(prompt_markdown, "Confucius Task Prompt"),
    }

    controlled_cost_by_agent = {row["agent"]: row for row in controlled_cost_rows}
    for row in controlled_usage_rows:
        assert_usage_matches_csv(row["agent"], row, logs[row["agent"]]["events"])
    for row in native_usage_rows:
        assert_usage_matches_csv(row["agent"], row, logs[row["agent"]]["events"])

    controlled_usage = {}
    for row in controlled_usage_rows:
        controlled_usage[row["agent"]] = {
            "agent": row["agent"],
            "workflow": "Direct .ipynb" if row["agent"] == "Carson" else "Percent-cell .py",
            "total_tokens": int(row["total_tokens"]),
            "input_tokens": int(row["input_tokens"]),
            "cached_input_tokens": int(row["cached_input_tokens"]),
            "non_cached_input_tokens": int(row["non_cached_input_tokens"]),
            "output_tokens": int(row["output_tokens"]),
            "duration_ms": int(row["duration_ms"]),
            "duration": row["duration"],
            "model_calls": int(row["token_count_events"]),
            "observed_cost": float(controlled_cost_by_agent[row["agent"]]["total_cost_usd"]),
            "artifact_tokens": int(row["source_artifact_tokens"]),
        }

    native_usage = {}
    native_workflow = {"Boyle": "Agent-native executed .ipynb", "Laplace": "Agent-native percent-cell .py"}
    for row in native_usage_rows:
        agent = row["agent"]
        native_usage[agent] = {
            "agent": agent,
            "workflow": native_workflow[agent],
            "total_tokens": int(row["total_tokens"]),
            "input_tokens": int(row["input_tokens"]),
            "cached_input_tokens": int(row["cached_input_tokens"]),
            "non_cached_input_tokens": int(row["non_cached_input_tokens"]),
            "output_tokens": int(row["output_tokens"]),
            "duration_ms": int(row["duration_ms"]),
            "duration": duration_label(row["duration_ms"]),
            "model_calls": len(logs[agent]["events"]),
            "observed_cost": cost_from_usage(row),
            "artifact_tokens": int(row["source_artifact_tokens"]),
        }

    all_usage = {
        "Boyle": native_usage["Boyle"],
        "Laplace": native_usage["Laplace"],
        "Carson": controlled_usage["Carson"],
        "Confucius": controlled_usage["Confucius"],
    }
    pairs = [
        ("Agent-native", "Boyle", "Laplace"),
        ("Controlled direct-edit", "Carson", "Confucius"),
    ]

    overview_ratios = []
    cache_rows = []
    pair_ratio_summaries = {}
    for label, notebook_agent, py_agent in pairs:
        notebook = all_usage[notebook_agent]
        py = all_usage[py_agent]
        notebook_norm = normalize_first_call_cache(logs[notebook_agent]["events"])
        py_norm = token_usage_from_events(logs[py_agent]["events"])
        notebook_norm_cost = cost_from_usage(notebook_norm)
        py_norm_cost = cost_from_usage(py_norm)
        overview_ratios.append(
            {
                "comparison": label,
                "total_tokens": notebook["total_tokens"] / py["total_tokens"],
                "model_calls": notebook["model_calls"] / py["model_calls"],
                "runtime": notebook["duration_ms"] / py["duration_ms"],
                "observed_cost": notebook["observed_cost"] / py["observed_cost"],
                "normalized_cost": notebook_norm_cost / py_norm_cost,
            }
        )
        pair_ratio_summaries[label] = ratio_summary(
            notebook,
            py,
            normalized_cost_ratio=notebook_norm_cost / py_norm_cost,
        )
        cache_rows.append(
            [
                label,
                f"{notebook['workflow']} / {py['workflow']}",
                f"{notebook['observed_cost'] / py['observed_cost']:.2f}x",
                f"{notebook_norm['non_cached_input_tokens'] / py_norm['non_cached_input_tokens']:.2f}x",
                f"{notebook_norm_cost / py_norm_cost:.2f}x",
            ]
        )

    controlled_table_rows = [
        [
            row["workflow"],
            row["agent"],
            fmt_int(row["total_tokens"]),
            fmt_int(row["non_cached_input_tokens"]),
            fmt_int(row["model_calls"]),
            row["duration"],
            fmt_usd(row["observed_cost"]),
            fmt_int(row["artifact_tokens"]),
        ]
        for row in [controlled_usage["Carson"], controlled_usage["Confucius"]]
    ]
    native_table_rows = [
        [
            row["workflow"],
            row["agent"],
            fmt_int(row["total_tokens"]),
            fmt_int(row["non_cached_input_tokens"]),
            fmt_int(row["model_calls"]),
            row["duration"],
            fmt_usd(row["observed_cost"]),
            fmt_int(row["artifact_tokens"]),
        ]
        for row in [native_usage["Boyle"], native_usage["Laplace"]]
    ]
    controlled_tool_table_rows = [
        [row["workflow"], row["category"], fmt_int(row["tool_call_count"])]
        for row in controlled_tool_rows
    ]
    controlled_tool_categories = []
    for row in controlled_tool_rows:
        controlled_tool_categories.append(
            {
                "workflow": "Direct .ipynb" if row["agent"] == "Carson" else "Percent-cell .py",
                "category": broad_controlled_category(row["category"]),
                "count": int(row["tool_call_count"]),
            }
        )
    controlled_category_totals: dict[tuple[str, str], int] = {}
    for row in controlled_tool_categories:
        key = (str(row["workflow"]), str(row["category"]))
        controlled_category_totals[key] = controlled_category_totals.get(key, 0) + int(row["count"])
    controlled_tool_categories = [
        {"workflow": workflow, "category": category, "count": count}
        for (workflow, category), count in sorted(controlled_category_totals.items())
    ]

    native_tool_table_rows = [
        [native_usage[agent]["workflow"], agent, name, fmt_int(count)]
        for agent in ["Boyle", "Laplace"]
        for name, count in sorted(logs[agent]["tool_counts"].items())
    ]
    native_tool_categories = []
    for agent in ["Boyle", "Laplace"]:
        workflow = str(native_usage[agent]["workflow"])
        for record in logs[agent]["tool_records"]:
            native_tool_categories.append(
                {
                    "workflow": workflow,
                    "category": native_tool_category(record, workflow),
                    "count": 1,
                }
            )
    native_category_totals: dict[tuple[str, str], int] = {}
    for row in native_tool_categories:
        key = (str(row["workflow"]), str(row["category"]))
        native_category_totals[key] = native_category_totals.get(key, 0) + int(row["count"])
    native_tool_categories = [
        {"workflow": workflow, "category": category, "count": count}
        for (workflow, category), count in sorted(native_category_totals.items())
    ]

    js_data = {
        "allUsage": all_usage,
        "overviewRatios": overview_ratios,
        "controlledTurnSpecs": build_controlled_turn_specs(controlled_turn_rows),
        "controlledToolCategories": controlled_tool_categories,
        "nativeToolCategories": native_tool_categories,
        "pairRatioSummaries": pair_ratio_summaries,
        "pairs": [
            {"label": label, "notebook": notebook, "py": py}
            for label, notebook, py in pairs
        ],
    }
    controlled_specs = js_data["controlledTurnSpecs"]
    overview_labels = [row["label"] for row in js_data["pairs"]]
    overview_notebook_values = [
        all_usage[row["notebook"]]["total_tokens"]
        for row in js_data["pairs"]
    ]
    overview_py_values = [
        all_usage[row["py"]]["total_tokens"]
        for row in js_data["pairs"]
    ]
    chart_svgs = {
        "overview-ratio-chart": static_grouped_bar_svg(
            overview_labels,
            [
                ("Notebook workflow", overview_notebook_values, "#012169"),
                ("Percent-cell workflow", overview_py_values, "#c84e00"),
            ],
            "Total task tokens",
        ),
        "overview-total-chart": static_grouped_bar_svg(
            ["Total tokens", "Model calls", "Runtime", "Observed cost", "Normalized cost"],
            [
                (
                    row["comparison"],
                    [
                        row["total_tokens"],
                        row["model_calls"],
                        row["runtime"],
                        row["observed_cost"],
                        row["normalized_cost"],
                    ],
                    "#012169" if row["comparison"] == "Controlled direct-edit" else "#339898",
                )
                for row in overview_ratios
            ],
            "Notebook / percent-cell ratio",
        ),
        "controlled-ratio-chart": static_single_bar_svg(
            [row["metric"] for row in pair_ratio_summaries["Controlled direct-edit"]],
            [row["ratio"] for row in pair_ratio_summaries["Controlled direct-edit"]],
            "Notebook / percent-cell ratio",
        ),
        "native-ratio-chart": static_single_bar_svg(
            [row["metric"] for row in pair_ratio_summaries["Agent-native"]],
            [row["ratio"] for row in pair_ratio_summaries["Agent-native"]],
            "Notebook / percent-cell ratio",
        ),
        "controlled-tool-category-chart": static_horizontal_grouped_bar_svg(controlled_tool_categories),
        "native-tool-category-chart": static_horizontal_grouped_bar_svg(native_tool_categories),
        "cache-ratio-chart": static_grouped_bar_svg(
            [row["comparison"] for row in overview_ratios],
            [
                ("Observed cost ratio", [row["observed_cost"] for row in overview_ratios], "#012169"),
                ("Normalized cost ratio", [row["normalized_cost"] for row in overview_ratios], "#339898"),
            ],
            "Notebook / percent-cell cost ratio",
        ),
    }
    for spec in controlled_specs:
        turns = spec["turns"]
        chart_svgs[f"controlled-delta-{spec['rank']}"] = static_single_bar_svg(
            [str(row["turn"]) for row in turns],
            [row["delta"] for row in turns],
            "Token delta",
            color=("#012169" if "ipynb" in spec["workflow"] else "#c84e00"),
        )
        chart_svgs[f"controlled-input-{spec['rank']}"] = static_stacked_bar_svg(
            [str(row["turn"]) for row in turns],
            [row["cached_input"] for row in turns],
            [row["fresh_input"] for row in turns],
        )

    body_class = ' class="print-report"' if print_mode else ""
    tabs_html = "" if print_mode else """
  <div class="tabs" role="tablist">
    <button class="tab-button active" data-tab="overview" type="button">Overview</button>
    <button class="tab-button" data-tab="controlled" type="button">Controlled Comparison</button>
    <button class="tab-button" data-tab="native" type="button">Agent-Native Comparison</button>
    <button class="tab-button" data-tab="cache" type="button">Cache And Cost Notes</button>
    <button class="tab-button" data-tab="appendix" type="button">Appendix</button>
  </div>
"""
    panel_class = "tab-panel active" if print_mode else "tab-panel"
    overview_class = "tab-panel active"
    if print_mode:
        overview_class = panel_class
    script_startup = """
setupTabs();
ratioChart();
overviewRatioChart();
pairRatioChart("controlled-ratio-chart", "Controlled direct-edit");
pairRatioChart("native-ratio-chart", "Agent-native");
toolCategoryChart("controlled-tool-category-chart", reportData.controlledToolCategories);
toolCategoryChart("native-tool-category-chart", reportData.nativeToolCategories);
controlledDeltaCharts();
controlledInputCharts();
cacheRatioChart();
"""
    if print_mode:
        script_startup += """
window.addEventListener("load", () => {
  setTimeout(() => {
    document.querySelectorAll(".js-plotly-plot").forEach(plot => Plotly.Plots.resize(plot));
  }, 500);
});
"""
    def figure_div(chart_id: str) -> str:
        if print_mode:
            return chart_svgs[chart_id]
        return f'<div id="{chart_id}" class="chart"></div>'
    def prompt_block(label: str, prompt: str) -> str:
        escaped_label = html.escape(label)
        escaped_prompt = html.escape(prompt)
        if print_mode:
            return f'<section class="prompt-block"><h4>{escaped_label}</h4><pre>{escaped_prompt}</pre></section>'
        return f'<details><summary>{escaped_label}</summary><pre>{escaped_prompt}</pre></details>'

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Notebook vs. Percent-Cell Python for Coding Agents</title>
  <script src="assets/plotly-2.35.2.min.js"></script>
  <style>
    :root {{
      --duke-navy: #012169;
      --duke-copper: #c84e00;
      --duke-teal: #339898;
      --cast-iron: #262626;
      --hatteras: #e2e6ed;
    }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--cast-iron);
      background: #ffffff;
      line-height: 1.55;
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 2rem 1.25rem 4rem;
    }}
    h1, h2, h3 {{
      color: var(--duke-navy);
      line-height: 1.15;
    }}
    h1 {{
      font-size: 2.4rem;
      margin-bottom: 0.6rem;
    }}
    h2 {{
      border-top: 1px solid var(--hatteras);
      padding-top: 1.6rem;
      margin-top: 2.4rem;
    }}
    .lead {{
      font-size: 1.15rem;
      max-width: 850px;
    }}
    .abstract {{
      margin: 1.2rem 0 1.6rem;
      font-size: 1.04rem;
    }}
    .callout {{
      border-left: 5px solid var(--duke-navy);
      background: #f7f8fa;
      padding: 1rem 1.2rem;
      margin: 1.4rem 0;
    }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 0.9rem;
      margin: 1.4rem 0;
    }}
    .metric {{
      border: 1px solid var(--hatteras);
      padding: 0.9rem;
      background: #fff;
    }}
    .metric strong {{
      display: block;
      font-size: 1.6rem;
      color: var(--duke-navy);
    }}
    .tabs {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.55rem;
      border-bottom: 2px solid var(--duke-navy);
      margin: 1.8rem 0 1.4rem;
      padding-bottom: 0;
    }}
    .tab-button {{
      border: 2px solid var(--duke-navy);
      border-bottom: none;
      background: #eef3f8;
      color: var(--duke-navy);
      padding: 0.8rem 1rem;
      cursor: pointer;
      font: inherit;
      font-weight: 750;
      border-radius: 6px 6px 0 0;
    }}
    .tab-button.active {{
      background: var(--duke-navy);
      color: #ffffff;
      border-color: var(--duke-navy);
      box-shadow: 0 -2px 0 var(--duke-copper) inset;
    }}
    .tab-button:focus-visible {{
      outline: 3px solid var(--duke-copper);
      outline-offset: 2px;
    }}
    .tab-panel {{
      display: none;
    }}
    .tab-panel.active {{
      display: block;
    }}
    .print-report .tab-panel {{
      display: block;
      page-break-before: always;
      break-before: page;
    }}
    .print-report .tab-panel:first-of-type {{
      page-break-before: auto;
      break-before: auto;
    }}
    .print-report h2 {{
      border-top: none;
      padding-top: 0;
    }}
    @media print {{
      @page {{
        margin: 0.85in 0.55in 0.6in;
      }}
      body {{
        margin: 0;
      }}
      main {{
        max-width: none;
        padding: 0;
      }}
      .chart {{
        min-height: 410px;
      }}
      h1, h2, h3, .chart-label {{
        break-after: avoid;
        page-break-after: avoid;
      }}
      .abstract, .callout, .metric-grid, table, details, .static-chart, .keep-block {{
        break-inside: avoid;
        page-break-inside: avoid;
      }}
      .figure-caption {{
        break-before: avoid;
        page-break-before: avoid;
      }}
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 1rem 0 1.5rem;
      font-size: 0.95rem;
    }}
    th, td {{
      border: 1px solid var(--hatteras);
      padding: 0.5rem 0.6rem;
      vertical-align: top;
    }}
    th {{
      background: #f0f4f8;
      text-align: left;
    }}
    code {{
      background: #f0f4f8;
      padding: 0.08rem 0.25rem;
    }}
    pre {{
      background: #f8fafc;
      border: 1px solid var(--hatteras);
      padding: 1rem;
      overflow-x: auto;
    }}
    .chart {{
      width: 100%;
      min-height: 460px;
      margin: 0.3rem 0 2rem;
    }}
    .chart-label {{
      margin: 1.2rem 0 0;
      color: var(--duke-navy);
      font-weight: 650;
      font-size: 1rem;
    }}
    .figure-caption {{
      margin: -1.35rem 0 2rem;
      color: #444;
      font-size: 0.95rem;
      line-height: 1.45;
    }}
    .keep-block {{
      break-inside: avoid;
      page-break-inside: avoid;
    }}
    .prompt-block {{
      margin: 1rem 0 1.5rem;
    }}
    .prompt-block h4 {{
      color: var(--duke-navy);
      margin: 0 0 0.4rem;
    }}
    .small {{
      color: #555;
      font-size: 0.95rem;
    }}
    details {{
      border: 1px solid var(--hatteras);
      margin: 1rem 0;
      padding: 0.9rem 1rem;
      background: #fff;
    }}
    summary {{
      cursor: pointer;
      color: var(--duke-navy);
      font-weight: 650;
    }}
  </style>
</head>
<body{body_class}>
<main>
  <h1>Notebook vs. Percent-Cell Python for Coding Agents</h1>

{tabs_html}

  <section id="overview" class="{overview_class}">
    <h2>Overview</h2>
    <div class="abstract">
      <p>Interactive data analysis is often taught and reviewed in notebooks, but coding agents have to read, edit, validate, and re-send the working artifact as context during a task. This report tests whether an <code>.ipynb</code> notebook is more token-expensive for agents than an equivalent VS Code/Jupyter percent-cell <code>.py</code> file, which preserves cell-based interaction while storing the analysis as plain Python text.</p>
      <p>We ran two paired agent experiments in which agents analyzed Seattle Public Library checkout data to compare physical and digital borrowing trends over time and produce a short reproducible analysis report. In the controlled direct-edit comparison, one subagent edited and executed an existing notebook while a second subagent edited and executed an equivalent percent-cell Python file. In the agent-native comparison, one subagent used a less constrained notebook workflow that included generating, executing, inspecting, patching, and rerunning notebook artifacts, while the paired subagent used a percent-cell Python workflow. Across both comparisons, the notebook workflow accumulated more total tokens, required more model calls, and took longer. Internal worker names are retained as log labels for auditability, but the report treats workflow as the main unit of comparison.</p>
    </div>
    <div class="callout">
      <strong>Main takeaway:</strong> both comparisons point in the same direction. Notebook workflows required more model calls, took longer, and accumulated more total task tokens. The exact cost multiplier is a best estimate because prompt caching changes the fresh/cached input split.
    </div>
    <div class="metric-grid">
      <div class="metric"><strong>1.59x</strong>Agent-native total-token ratio</div>
      <div class="metric"><strong>1.94x</strong>Controlled total-token ratio</div>
      <div class="metric"><strong>1.25x</strong>Agent-native model-call ratio</div>
      <div class="metric"><strong>1.71x</strong>Controlled model-call ratio</div>
    </div>
    <p>In both the looser agent-native workflow and the stricter direct-edit workflow, the notebook path required more model turns and accumulated more total session context. This workflow-friction result is stronger than any precise universal cost multiplier.</p>
    <p>Total tokens are still useful because they measure cumulative context traffic. Fresh input and observed cost are useful too, but they are cache-sensitive and should be presented as estimates.</p>
    {figure_div("overview-ratio-chart")}
    <p class="figure-caption"><strong>Figure:</strong> Total task tokens for notebook and percent-cell workflows within each experiment. <strong>Takeaway:</strong> the notebook workflow used more total tokens in both the agent-native and controlled comparisons.</p>
    {figure_div("overview-total-chart")}
    <p class="figure-caption"><strong>Figure:</strong> Notebook-to-percent-cell ratios for total tokens, model calls, runtime, and cost estimates. <strong>Takeaway:</strong> the notebook workflow is consistently above parity, while the exact cost ratio is more cache-sensitive than the workflow and token-count ratios.</p>
  </section>

  <section id="controlled" class="{panel_class}">
    <h2>Controlled Direct-Edit Comparison</h2>
    <div class="abstract">
      <p>This section isolates the file-format question as closely as this experiment allowed. Two subagents were given the same data, the same analysis question, and similar deliverable requirements; the main intended difference was whether the durable working source was an <code>.ipynb</code> notebook or a percent-cell <code>.py</code> file.</p>
      <p>The notebook worker edited an existing notebook, executed it, and inspected saved notebook outputs. The percent-cell worker edited an equivalent Python file and inspected terminal or saved outputs. This comparison is the strongest evidence in the report because it controls the task framing more tightly than the agent-native run.</p>
    </div>
    <table>
      <thead><tr><th>Workflow</th><th>Log label</th><th>Total tokens</th><th>Fresh input</th><th>Model calls</th><th>Runtime</th><th>Observed cost</th><th>Source artifact tokens</th></tr></thead>
      <tbody>{html_rows(controlled_table_rows)}</tbody>
    </table>
    {figure_div("controlled-ratio-chart")}
    <p class="figure-caption"><strong>Figure:</strong> Controlled direct-edit notebook-to-percent-cell ratios across task metrics. <strong>Takeaway:</strong> the notebook worker required more calls, more elapsed time, more total tokens, and more fresh input than the percent-cell worker.</p>
    <div class="keep-block">
      <h3>Tool-Call Categories</h3>
      <p class="small">Categories group similar work, so source edits or output inspections do not need to use identical commands to be compared.</p>
      {figure_div("controlled-tool-category-chart")}
      <p class="figure-caption"><strong>Figure:</strong> Broad tool-call categories for the controlled comparison. <strong>Takeaway:</strong> the notebook workflow added notebook-specific structure validation and more output-inspection work, which helps explain the higher call count.</p>
    </div>
    <h3>Per-Call Token Delta</h3>
    <div class="keep-block">
      <p class="chart-label">Direct .ipynb workflow</p>
      {figure_div("controlled-delta-1")}
      <p class="figure-caption"><strong>Figure:</strong> Per-call token delta for the controlled notebook worker. <strong>Takeaway:</strong> the notebook run kept accumulating large per-call context as the task progressed.</p>
    </div>
    <div class="keep-block">
      <p class="chart-label">Percent-cell .py workflow</p>
      {figure_div("controlled-delta-2")}
      <p class="figure-caption"><strong>Figure:</strong> Per-call token delta for the controlled percent-cell worker. <strong>Takeaway:</strong> the percent-cell run had fewer calls overall, shortening the cumulative token path through the task.</p>
    </div>
    <h3>Input Composition</h3>
    <div class="keep-block">
      <p class="chart-label">Direct .ipynb workflow</p>
      {figure_div("controlled-input-1")}
      <p class="figure-caption"><strong>Figure:</strong> Cached and fresh input tokens by model call for the controlled notebook worker. <strong>Takeaway:</strong> most later input was cached, but the notebook run still paid for repeated long context and several fresh-input spikes.</p>
    </div>
    <div class="keep-block">
      <p class="chart-label">Percent-cell .py workflow</p>
      {figure_div("controlled-input-2")}
      <p class="figure-caption"><strong>Figure:</strong> Cached and fresh input tokens by model call for the controlled percent-cell worker. <strong>Takeaway:</strong> the percent-cell workflow had fewer model calls and less cumulative fresh input.</p>
    </div>
    <h3>Tool-Call Category Table</h3>
    <table>
      <thead><tr><th>Workflow</th><th>Category</th><th>Tool calls</th></tr></thead>
      <tbody>{html_rows(controlled_tool_table_rows)}</tbody>
    </table>
  </section>

  <section id="native" class="{panel_class}">
    <h2>Agent-Native Comparison</h2>
    <div class="abstract">
      <p>This section uses the earlier, less constrained paired run to ask what happens when the notebook worker is allowed to follow a more natural agent workflow. That notebook workflow included generating notebook structure, executing with notebook tooling, inspecting saved outputs, patching, and rerunning notebook artifacts.</p>
      <p>Because the workers had more freedom, this run is less controlled than the direct-edit comparison. Its value is corroboration: it tests whether the same direction appears when the notebook worker behaves more like an unconstrained coding agent might behave in practice.</p>
    </div>
    <table>
      <thead><tr><th>Workflow</th><th>Log label</th><th>Total tokens</th><th>Fresh input</th><th>Model calls</th><th>Runtime</th><th>Observed cost</th><th>Source artifact tokens</th></tr></thead>
      <tbody>{html_rows(native_table_rows)}</tbody>
    </table>
    {figure_div("native-ratio-chart")}
    <p class="figure-caption"><strong>Figure:</strong> Agent-native notebook-to-percent-cell ratios across task metrics. <strong>Takeaway:</strong> even in the less constrained run, the notebook workflow used more total tokens, more model calls, more time, and higher estimated cost.</p>
    <div class="keep-block">
      <h3>Tool-Call Categories</h3>
      <p class="small">The agent-native logs mostly expose shell and patch tools, so this chart uses broad command-intent categories.</p>
      {figure_div("native-tool-category-chart")}
      <p class="figure-caption"><strong>Figure:</strong> Broad command-intent categories for the agent-native comparison. <strong>Takeaway:</strong> the agent-native notebook run spent more calls on setup/status and output or execution handling, while broad edit and report-writing work was similar in scale.</p>
    </div>
    <h3>Raw Tool Calls</h3>
    <table>
      <thead><tr><th>Workflow</th><th>Log label</th><th>Tool</th><th>Calls</th></tr></thead>
      <tbody>{html_rows(native_tool_table_rows)}</tbody>
    </table>
  </section>

  <section id="cache" class="{panel_class}">
    <h2>Cache And Cost Notes</h2>
    <div class="abstract">
      <p>This section separates total session traffic from cache-sensitive cost estimates. The raw token totals show how much input and output accumulated across model calls. API-equivalent cost depends on how much input was classified as fresh versus cached, which varied across first calls in a way that should not be over-interpreted as a file-format effect.</p>
      <p>The normalization table treats the notebook first calls as if they had the same common first-call cache pattern seen in the percent-cell runs. This sensitivity check helps show whether the conclusion depends entirely on the first-call cache difference.</p>
    </div>
    <p>Prompt caching changes the split between fresh and cached input. It does not change total input tokens, but it does affect estimated API cost. In these runs, the percent-cell first calls commonly had about 43K input tokens with about 41K cached, while the notebook first calls had similar input length but only about 5K cached.</p>
    <p>The table below normalizes each notebook first call to the common 41,344 cached-token first-call pattern as a sensitivity check rather than a claim about what billing should have been.</p>
    <table>
      <thead><tr><th>Comparison</th><th>Pair</th><th>Observed cost ratio</th><th>Normalized fresh-input ratio</th><th>Normalized cost ratio</th></tr></thead>
      <tbody>{html_rows(cache_rows)}</tbody>
    </table>
    {figure_div("cache-ratio-chart")}
    <p class="figure-caption"><strong>Figure:</strong> Observed cost ratios compared with ratios after normalizing notebook first-call cache behavior. <strong>Takeaway:</strong> notebook workflows remain more expensive under this sensitivity check, but the multiplier shrinks when the first-call cache imbalance is reduced.</p>
    <p class="small">Interpretation: cost likely moves in the same direction as total tokens and model calls, but the exact cost ratio is less stable than the workflow-turn evidence.</p>
  </section>

  <section id="appendix" class="{panel_class}">
    <h2>Appendix</h2>
    <div class="abstract">
      <p>This section documents how the report can be audited and rebuilt. The HTML is generated from package-local CSV files and raw Codex JSONL logs; the exact worker prompts are included so readers can inspect the starting conditions for each subagent.</p>
    </div>
    <h3>Reproducibility</h3>
    <p>The page is generated by <code>scripts/build_report.py</code> from CSV files and sanitized JSONL logs included in this package. Plotly is vendored at <code>assets/plotly-2.35.2.min.js</code>.</p>
    <h3>Token Interpretation</h3>
    <p><code>total_tokens</code> is cumulative accounting across model calls, not unique text. For each call, <code>input_tokens = cached_input_tokens + non_cached_input_tokens</code>, and <code>total_tokens = input_tokens + output_tokens</code>.</p>
    <h3>Exact Starting Prompts</h3>
    <p>The names below are internal worker/log labels preserved so the sanitized JSONL logs, CSV rows, and prompts can be cross-checked.</p>
    {prompt_block("Boyle: agent-native notebook prompt", str(prompts["Boyle"]))}
    {prompt_block("Laplace: agent-native percent-cell prompt", str(prompts["Laplace"]))}
    {prompt_block("Carson: direct notebook prompt", str(prompts["Carson"]))}
    {prompt_block("Confucius: direct percent-cell prompt", str(prompts["Confucius"]))}
  </section>
</main>

<script>
const reportData = {json.dumps(js_data)};

function workflowColor(name) {{
  return name.includes("ipynb") || name.includes("notebook") || name === "Boyle" || name === "Carson" ? "#012169" : "#c84e00";
}}

function ratioChart() {{
  const labels = reportData.pairs.map(row => row.label);
  const notebookAgents = reportData.pairs.map(row => row.notebook);
  const pyAgents = reportData.pairs.map(row => row.py);
  const notebookWorkflows = notebookAgents.map(agent => reportData.allUsage[agent].workflow);
  const pyWorkflows = pyAgents.map(agent => reportData.allUsage[agent].workflow);
  const traces = [
    {{
      type: "bar",
      name: "Notebook workflow",
      x: labels,
      y: notebookAgents.map(agent => reportData.allUsage[agent].total_tokens),
      marker: {{ color: "#012169", opacity: 0.82 }},
      customdata: notebookWorkflows,
      hovertemplate: "%{{customdata}}<br>%{{x}}<br>Total tokens: %{{y:,}}<extra></extra>"
    }},
    {{
      type: "bar",
      name: "Percent-cell workflow",
      x: labels,
      y: pyAgents.map(agent => reportData.allUsage[agent].total_tokens),
      marker: {{ color: "#c84e00", opacity: 0.82 }},
      customdata: pyWorkflows,
      hovertemplate: "%{{customdata}}<br>%{{x}}<br>Total tokens: %{{y:,}}<extra></extra>"
    }}
  ];
  Plotly.newPlot("overview-ratio-chart", traces, {{
    barmode: "group",
    yaxis: {{ title: "Total task tokens" }},
    xaxis: {{ title: "Experiment" }},
    legend: {{ orientation: "h", y: 1.12 }},
    margin: {{ l: 80, r: 30, t: 35, b: 70 }}
  }}, {{ responsive: true }});
}}

function overviewRatioChart() {{
  const metrics = ["total_tokens", "model_calls", "runtime", "observed_cost", "normalized_cost"];
  const labels = ["Total tokens", "Model calls", "Runtime", "Observed cost", "Normalized cost"];
  const traces = reportData.overviewRatios.map(row => ({{
    type: "bar",
    name: row.comparison,
    x: labels,
    y: metrics.map(metric => row[metric]),
    marker: {{ color: row.comparison === "Controlled direct-edit" ? "#012169" : "#339898" }},
    hovertemplate: row.comparison + "<br>%{{x}}: %{{y:.2f}}x<extra></extra>"
  }}));
  Plotly.newPlot("overview-total-chart", traces, {{
    barmode: "group",
    yaxis: {{ title: "Notebook / percent-cell ratio" }},
    xaxis: {{ title: "Metric" }},
    legend: {{ orientation: "h", y: 1.12 }},
    margin: {{ l: 70, r: 30, t: 35, b: 70 }}
  }}, {{ responsive: true }});
}}

function pairRatioChart(divId, comparisonLabel) {{
  const rows = reportData.pairRatioSummaries[comparisonLabel];
  const traces = [{{
    type: "bar",
    name: "Notebook / percent-cell",
    x: rows.map(row => row.metric),
    y: rows.map(row => row.ratio),
    marker: {{ color: rows.map(row => row.metric === "Normalized cost" ? "#339898" : "#012169"), opacity: 0.82 }},
    hovertemplate: "%{{x}}<br>Ratio: %{{y:.2f}}x<extra></extra>"
  }}];
  Plotly.newPlot(divId, traces, {{
    yaxis: {{ title: "Notebook / percent-cell ratio" }},
    xaxis: {{ title: "Metric" }},
    shapes: [{{
      type: "line",
      xref: "paper",
      x0: 0,
      x1: 1,
      y0: 1,
      y1: 1,
      line: {{ color: "#666", width: 1, dash: "dot" }}
    }}],
    annotations: [{{
      xref: "paper",
      yref: "y",
      x: 1,
      y: 1,
      text: "parity",
      showarrow: false,
      xanchor: "right",
      yanchor: "bottom",
      font: {{ size: 12, color: "#555" }}
    }}],
    showlegend: false,
    margin: {{ l: 80, r: 30, t: 35, b: 75 }}
  }}, {{ responsive: true }});
}}

function toolCategoryChart(divId, rows) {{
  const categories = Array.from(new Set(rows.map(row => row.category))).sort();
  const workflows = Array.from(new Set(rows.map(row => row.workflow)));
  const traces = workflows.map(workflow => ({{
    type: "bar",
    orientation: "h",
    name: workflow,
    y: categories,
    x: categories.map(category => {{
      const match = rows.find(row => row.workflow === workflow && row.category === category);
      return match ? match.count : 0;
    }}),
    marker: {{ color: workflowColor(workflow), opacity: 0.82 }},
    hovertemplate: workflow + "<br>%{{y}}: %{{x}} calls<extra></extra>"
  }}));
  Plotly.newPlot(divId, traces, {{
    barmode: "group",
    xaxis: {{ title: "Tool calls" }},
    yaxis: {{ title: "Category", automargin: true }},
    legend: {{ orientation: "h", y: 1.12 }},
    margin: {{ l: 185, r: 30, t: 35, b: 60 }}
  }}, {{ responsive: true }});
}}

function controlledDeltaCharts() {{
  for (const spec of reportData.controlledTurnSpecs) {{
    const labels = spec.turns.map(row => String(row.turn));
    const traces = [{{
      type: "bar",
      name: "Token delta",
      x: labels,
      y: spec.turns.map(row => row.delta),
      marker: {{ color: workflowColor(spec.workflow), opacity: 0.75 }},
      hovertemplate: spec.workflow + "<br>Call %{{x}}<br>Token delta: %{{y:,}}<extra></extra>"
    }}];
    Plotly.newPlot("controlled-delta-" + spec.rank, traces, {{
      xaxis: {{ title: "Model call / token_count event" }},
      yaxis: {{ title: "Token delta" }},
      margin: {{ l: 70, r: 30, t: 25, b: 55 }}
    }}, {{ responsive: true }});
  }}
}}

function controlledInputCharts() {{
  for (const spec of reportData.controlledTurnSpecs) {{
    const labels = spec.turns.map(row => String(row.turn));
    const traces = [
      {{
        type: "bar",
        name: "Cached input",
        x: labels,
        y: spec.turns.map(row => row.cached_input),
        marker: {{ color: "#012169", opacity: 0.85 }}
      }},
      {{
        type: "bar",
        name: "Fresh input",
        x: labels,
        y: spec.turns.map(row => row.fresh_input),
        marker: {{ color: "#339898", opacity: 0.85 }}
      }}
    ];
    Plotly.newPlot("controlled-input-" + spec.rank, traces, {{
      barmode: "stack",
      xaxis: {{ title: "Model call / token_count event" }},
      yaxis: {{ title: "Input tokens" }},
      legend: {{ orientation: "h", y: 1.08 }},
      margin: {{ l: 70, r: 30, t: 25, b: 55 }}
    }}, {{ responsive: true }});
  }}
}}

function cacheRatioChart() {{
  const traces = [
    {{
      type: "bar",
      name: "Observed cost ratio",
      x: reportData.overviewRatios.map(row => row.comparison),
      y: reportData.overviewRatios.map(row => row.observed_cost),
      marker: {{ color: "#012169", opacity: 0.8 }}
    }},
    {{
      type: "bar",
      name: "Normalized cost ratio",
      x: reportData.overviewRatios.map(row => row.comparison),
      y: reportData.overviewRatios.map(row => row.normalized_cost),
      marker: {{ color: "#339898", opacity: 0.8 }}
    }}
  ];
  Plotly.newPlot("cache-ratio-chart", traces, {{
    barmode: "group",
    yaxis: {{ title: "Notebook / percent-cell cost ratio" }},
    xaxis: {{ title: "Comparison" }},
    legend: {{ orientation: "h", y: 1.12 }},
    margin: {{ l: 80, r: 30, t: 35, b: 70 }}
  }}, {{ responsive: true }});
}}

function setupTabs() {{
  const buttons = document.querySelectorAll(".tab-button");
  const panels = document.querySelectorAll(".tab-panel");
  buttons.forEach(button => {{
    button.addEventListener("click", () => {{
      buttons.forEach(item => item.classList.remove("active"));
      panels.forEach(item => item.classList.remove("active"));
      button.classList.add("active");
      document.getElementById(button.dataset.tab).classList.add("active");
      setTimeout(() => {{
        document.querySelectorAll(".js-plotly-plot").forEach(plot => Plotly.Plots.resize(plot));
      }}, 0);
    }});
  }});
}}

{script_startup}
</script>
</body>
</html>
"""


def main() -> None:
    OUTPUT.write_text(build_html(), encoding="utf-8")
    PRINT_OUTPUT.write_text(build_html(print_mode=True), encoding="utf-8")
    print(f"Wrote {OUTPUT}")
    print(f"Wrote {PRINT_OUTPUT}")


if __name__ == "__main__":
    main()
