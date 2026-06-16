from __future__ import annotations

import csv
import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT = ROOT / "index.html"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def fmt_int(value: str | int | float) -> str:
    return f"{int(float(value)):,}"


def fmt_usd(value: str | float) -> str:
    return f"${float(value):.2f}"


def workflow_label(agent: str) -> str:
    return "Direct .ipynb" if agent == "Carson" else "Percent-cell .py"


def build_chart_specs(turn_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    session_order = [
        ("Carson", "Direct .ipynb"),
        ("Confucius", "Percent-cell .py"),
    ]
    specs = []
    for rank, (agent, workflow) in enumerate(session_order, start=1):
        rows = [
            row
            for row in turn_rows
            if row["session_title"].startswith(agent)
        ]
        rows.sort(key=lambda row: int(row["turn_index"]))
        specs.append(
            {
                "rank": rank,
                "agent": agent,
                "workflow": workflow,
                "turns": [
                    {
                        "turn": int(row["turn_index"]),
                        "delta": int(row["token_delta"]),
                        "cumulative": int(row["end_total_tokens"]),
                        "input": int(row["turn_input_tokens"]),
                        "cached_input": int(row["turn_cached_input_tokens"]),
                        "fresh_input": int(row["turn_uncached_input_tokens"]),
                        "output": int(row["turn_output_tokens"]),
                        "tool_calls": int(row["tool_call_count"] or 0),
                        "tools": row["tool_call_summary"],
                    }
                    for row in rows
                ],
            }
        )
    return specs


def build_summary_rows(usage_rows: list[dict[str, str]], cost_rows: list[dict[str, str]]) -> str:
    cost_by_agent = {row["agent"]: row for row in cost_rows}
    rows = []
    for row in usage_rows:
        agent = row["agent"]
        cost = cost_by_agent[agent]
        rows.append(
            "<tr>"
            f"<td>{html.escape(agent)}</td>"
            f"<td>{workflow_label(agent)}</td>"
            f"<td>{fmt_int(row['total_tokens'])}</td>"
            f"<td>{fmt_int(row['non_cached_input_tokens'])}</td>"
            f"<td>{fmt_int(row['token_count_events'])}</td>"
            f"<td>{html.escape(row['duration'])}</td>"
            f"<td>{fmt_usd(cost['total_cost_usd'])}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def build_tool_rows(tool_rows: list[dict[str, str]]) -> str:
    rows = []
    for row in tool_rows:
        rows.append(
            "<tr>"
            f"<td>{html.escape(row['workflow'])}</td>"
            f"<td>{html.escape(row['category'])}</td>"
            f"<td>{fmt_int(row['tool_call_count'])}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def extract_prompt(prompt_markdown: str, heading: str) -> str:
    marker = f"## {heading}"
    start = prompt_markdown.index(marker)
    fence_start = prompt_markdown.index("```text", start) + len("```text")
    fence_end = prompt_markdown.index("```", fence_start)
    return prompt_markdown[fence_start:fence_end].strip()


def build_html() -> str:
    usage_rows = read_csv(DATA_DIR / "direct-comparison-token-usage.csv")
    cost_rows = read_csv(DATA_DIR / "direct-comparison-api-costs.csv")
    turn_rows = read_csv(DATA_DIR / "model-call-token-events.csv")
    tool_rows = read_csv(DATA_DIR / "direct-comparison-tool-call-summary.csv")
    prompt_markdown = (DATA_DIR / "direct-comparison-agent-prompts.md").read_text(encoding="utf-8")
    carson_prompt = extract_prompt(prompt_markdown, "Carson Task Prompt")
    confucius_prompt = extract_prompt(prompt_markdown, "Confucius Task Prompt")
    chart_specs = build_chart_specs(turn_rows)
    chart_json = json.dumps(chart_specs)

    ratios = {
        "total_tokens": int(usage_rows[0]["total_tokens"]) / int(usage_rows[1]["total_tokens"]),
        "fresh_input": int(usage_rows[0]["non_cached_input_tokens"]) / int(usage_rows[1]["non_cached_input_tokens"]),
        "cost": float(cost_rows[0]["total_cost_usd"]) / float(cost_rows[1]["total_cost_usd"]),
        "model_calls": int(usage_rows[0]["token_count_events"]) / int(usage_rows[1]["token_count_events"]),
        "runtime": int(usage_rows[0]["duration_ms"]) / int(usage_rows[1]["duration_ms"]),
    }

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
    .two-col {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 1rem;
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
<body>
<main>
  <h1>Notebook vs. Percent-Cell Python for Coding Agents</h1>
  <p class="lead">A controlled comparison of two coding-agent workflows for the same analysis task: direct `.ipynb` editing versus VS Code/Jupyter percent-cell `.py` editing.</p>

  <div class="callout">
    <strong>Main takeaway:</strong> for this task, the direct notebook workflow used 1.94x as many total tokens, 2.53x as many fresh input tokens, and about 2.03x the GPT-5.5 API-equivalent cost. The percent-cell `.py` workflow reached the same analytical conclusion with fewer model calls and a much smaller source artifact.
  </div>

  <div class="metric-grid">
    <div class="metric"><strong>{ratios['total_tokens']:.2f}x</strong>Total token ratio</div>
    <div class="metric"><strong>{ratios['fresh_input']:.2f}x</strong>Fresh input ratio</div>
    <div class="metric"><strong>{ratios['cost']:.2f}x</strong>API cost ratio</div>
    <div class="metric"><strong>{ratios['model_calls']:.2f}x</strong>Model call ratio</div>
    <div class="metric"><strong>{ratios['runtime']:.2f}x</strong>Runtime ratio</div>
  </div>

  <h2>Executive Summary</h2>
  <p>This experiment compared two agents doing the same Seattle Public Library checkout analysis with parallel instructions. Carson edited and executed a notebook. Confucius edited and executed a percent-cell Python file. Both agents had to inspect outputs before writing final interpretation.</p>
  <p>The result was not just that the `.ipynb` file was larger at the end, although it was much larger. The notebook workflow also required more model calls and more fresh context during the task. The trace suggests the overhead came from the notebook acting as both source file and execution record: the agent had to edit JSON notebook structure, execute through notebook tooling, and inspect saved cell outputs.</p>

  <table>
    <thead>
      <tr><th>Agent</th><th>Workflow</th><th>Total tokens</th><th>Fresh input</th><th>Model calls</th><th>Runtime</th><th>GPT-5.5 cost</th></tr>
    </thead>
    <tbody>
      {build_summary_rows(usage_rows, cost_rows)}
    </tbody>
  </table>

  <h2>Procedure</h2>
  <p>The two workers received the same dataset, schema instructions, analysis question, and output requirements. The only intended difference was the durable analysis format.</p>
  <ul>
    <li>Notebook worker: direct edits to <code>analysis-notebook.ipynb</code>, execution with notebook tooling, targeted inspection of notebook cell outputs.</li>
    <li>Percent-cell worker: direct edits to <code>analysis-cells.py</code>, execution with <code>.venv/bin/python</code>, targeted inspection of terminal output and saved CSV/PNG artifacts.</li>
  </ul>
  <p>The report is built from archived Codex JSONL session logs and cleaned CSV extracts generated from those logs. The raw logs, cleaned data, final worker artifacts, and report-generation script are included with the published repository so the analysis can be audited or rebuilt.</p>

  <h2>Finding 1: Session Footprint</h2>
  <p>Total token delta shows how much the session token counter grew at each model call. The notebook worker accumulated more calls and a larger final session footprint.</p>
  <p class="chart-label">Direct .ipynb</p>
  <div id="footprint-chart-1" class="chart"></div>
  <p class="chart-label">Percent-cell .py</p>
  <div id="footprint-chart-2" class="chart"></div>

  <h2>Finding 2: Input Composition</h2>
  <p>Cached input is still part of input and still counted in total tokens, but it is classified as reusable prefix context. Fresh input is the non-cached portion of the prompt for that call.</p>
  <p class="chart-label">Direct .ipynb</p>
  <div id="composition-chart-1" class="chart"></div>
  <p class="chart-label">Percent-cell .py</p>
  <div id="composition-chart-2" class="chart"></div>

  <h2>Finding 3: Fresh Context</h2>
  <p>Fresh/non-cached input is the closest logged proxy for newly processed input context. On this measure, the notebook workflow used 129,036 fresh input tokens versus 51,000 for the percent-cell workflow.</p>
  <div id="fresh-chart" class="chart"></div>

  <h2>Finding 4: API-Equivalent Cost</h2>
  <p>Using GPT-5.5 rates, the notebook workflow cost about $1.61 and the percent-cell workflow cost about $0.79. Cost is computed from fresh input, cached input, and output separately.</p>
  <div id="cost-chart" class="chart"></div>
  <pre>cost =
  fresh_input * 5.00 / 1,000,000
  + cached_input * 0.50 / 1,000,000
  + output * 30.00 / 1,000,000</pre>

  <h2>Finding 5: Workflow Burden</h2>
  <p>The notebook worker made 36 classified tool calls; the percent-cell worker made 22. Notebook-specific overhead included structure validation, notebook execution, and extraction of saved cell outputs.</p>
  <table>
    <thead><tr><th>Workflow</th><th>Tool-call category</th><th>Count</th></tr></thead>
    <tbody>{build_tool_rows(tool_rows)}</tbody>
  </table>

  <h2>Conclusion</h2>
  <p>The evidence supports percent-cell Python as the better default durable format for agent-assisted analysis when a notebook is not itself the required deliverable. Percent-cell Python preserves cell-based execution and readable analysis structure while keeping the agent's working source smaller and separating code from generated output artifacts.</p>
  <p>The stronger claim is not "never use notebooks." It is that direct notebook editing can impose substantial overhead on coding agents because the agent must manage both source code and execution state.</p>

  <h2>Appendix</h2>
  <h3>Token interpretation</h3>
  <p><code>total_tokens</code> is cumulative accounting across model calls, not unique text. For each call, <code>input_tokens = cached_input_tokens + non_cached_input_tokens</code>, and <code>total_tokens = input_tokens + output_tokens</code>. Cached input is not free and is still included in total tokens, but it is priced lower and likely reflects reused prompt-prefix work.</p>
  <p class="small">For energy or compute interpretation, neither raw total tokens nor fresh input alone is perfect. Total tokens can overstate new work because cached input is included; fresh input can understate total work because cached input and output are not zero-cost. API-equivalent cost is a practical weighted proxy, not a direct energy measurement.</p>

  <h3>Exact Starting Prompts</h3>
  <p>The shared injected project context was identical across both worker sessions. The task-specific prompts below are the experimental prompts that differed by assigned file format and workflow.</p>

  <details>
    <summary>Carson: direct notebook workflow prompt</summary>
    <pre>{html.escape(carson_prompt)}</pre>
  </details>

  <details>
    <summary>Confucius: percent-cell Python workflow prompt</summary>
    <pre>{html.escape(confucius_prompt)}</pre>
  </details>

  <h3>Reproducibility</h3>
  <p>The HTML report can be regenerated from the repository package with <code>python scripts/build_report.py</code>. Plotly is vendored with the site, so the page does not depend on a CDN for the interactive figures.</p>
</main>

<script>
const chartSpecs = {chart_json};
const costRows = {json.dumps(cost_rows)};

function workflowColor(workflow) {{
  return workflow === "Direct .ipynb" ? "#012169" : "#c84e00";
}}

function makeFootprintChart() {{
  for (const spec of chartSpecs) {{
    const callLabels = spec.turns.map(row => String(row.turn));
    const traces = [
      {{
        type: "bar",
        name: "Token delta",
        x: callLabels,
        y: spec.turns.map(row => row.delta),
        marker: {{ color: workflowColor(spec.workflow), opacity: 0.7 }},
        hovertemplate: spec.workflow + "<br>Call %{{x}}<br>Token delta: %{{y:,}}<extra></extra>"
      }},
      {{
        type: "scatter",
        mode: "lines+markers",
        name: "Cumulative total",
        x: callLabels,
        y: spec.turns.map(row => row.cumulative),
        yaxis: "y2",
        line: {{ color: "#262626", width: 3 }},
        marker: {{ size: 7 }},
        hovertemplate: spec.workflow + "<br>Call %{{x}}<br>Cumulative: %{{y:,}}<extra></extra>"
      }}
    ];
    Plotly.newPlot("footprint-chart-" + spec.rank, traces, {{
      hovermode: "closest",
      xaxis: {{ title: "Model call / token_count event" }},
      yaxis: {{ title: "Token delta" }},
      yaxis2: {{ title: "Cumulative total tokens", overlaying: "y", side: "right", showgrid: false }},
      legend: {{ orientation: "h", y: 1.08 }},
      margin: {{ l: 70, r: 80, t: 25, b: 55 }}
    }}, {{ responsive: true }});
  }}
}}

function makeCompositionChart() {{
  for (const spec of chartSpecs) {{
    const callLabels = spec.turns.map(row => String(row.turn));
    const traces = [
      {{
        type: "bar",
        name: "Cached input",
        x: callLabels,
        y: spec.turns.map(row => row.cached_input),
        marker: {{ color: "#012169", opacity: 0.85 }},
        hovertemplate: spec.workflow + "<br>Call %{{x}}<br>Cached input: %{{y:,}}<extra></extra>"
      }},
      {{
        type: "bar",
        name: "Fresh input",
        x: callLabels,
        y: spec.turns.map(row => row.fresh_input),
        marker: {{ color: "#339898", opacity: 0.85 }},
        hovertemplate: spec.workflow + "<br>Call %{{x}}<br>Fresh input: %{{y:,}}<extra></extra>"
      }}
    ];
    Plotly.newPlot("composition-chart-" + spec.rank, traces, {{
      barmode: "stack",
      xaxis: {{ title: "Model call / token_count event" }},
      yaxis: {{ title: "Input tokens" }},
      legend: {{ orientation: "h", y: 1.08 }},
      margin: {{ l: 70, r: 30, t: 25, b: 55 }}
    }}, {{ responsive: true }});
  }}
}}

function makeFreshChart() {{
  const traces = chartSpecs.map(spec => ({{
    type: "scatter",
    mode: "lines+markers",
    name: spec.workflow,
    x: spec.turns.map(row => row.turn),
    y: spec.turns.map(row => row.fresh_input),
    line: {{ width: 3, color: workflowColor(spec.workflow) }},
    marker: {{ size: 7 }},
    hovertemplate: spec.workflow + "<br>Call %{{x}}<br>Fresh input: %{{y:,}}<extra></extra>"
  }}));
  Plotly.newPlot("fresh-chart", traces, {{
    xaxis: {{ title: "Model call / token_count event" }},
    yaxis: {{ title: "Fresh/non-cached input tokens" }},
    legend: {{ orientation: "h", y: 1.15 }},
    margin: {{ l: 70, r: 30, t: 35, b: 55 }}
  }}, {{ responsive: true }});
}}

function makeCostChart() {{
  const labels = costRows.map(row => row.agent === "Carson" ? "Direct .ipynb" : "Percent-cell .py");
  const traces = [
    {{
      type: "bar",
      name: "Fresh input cost",
      x: labels,
      y: costRows.map(row => Number(row.non_cached_input_cost_usd)),
      marker: {{ color: "#339898" }}
    }},
    {{
      type: "bar",
      name: "Cached input cost",
      x: labels,
      y: costRows.map(row => Number(row.cached_input_cost_usd)),
      marker: {{ color: "#012169" }}
    }},
    {{
      type: "bar",
      name: "Output cost",
      x: labels,
      y: costRows.map(row => Number(row.output_cost_usd)),
      marker: {{ color: "#c84e00" }}
    }}
  ];
  Plotly.newPlot("cost-chart", traces, {{
    barmode: "stack",
    yaxis: {{ title: "Estimated GPT-5.5 API cost (USD)" }},
    legend: {{ orientation: "h", y: 1.15 }},
    margin: {{ l: 70, r: 30, t: 35, b: 60 }}
  }}, {{ responsive: true }});
}}

makeFootprintChart();
makeCompositionChart();
makeFreshChart();
makeCostChart();
</script>
</body>
</html>
"""


def main() -> None:
    OUTPUT.write_text(build_html(), encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
