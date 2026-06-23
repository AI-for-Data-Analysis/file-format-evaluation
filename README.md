# Notebook vs. Percent-Cell Python for Coding Agents

This folder is a standalone, GitHub Pages-ready report package comparing
notebook and percent-cell Python workflows for coding agents.

It includes two comparisons:

- **Controlled direct-edit comparison:** Carson edited and executed an existing
  `.ipynb`; Confucius edited and executed an equivalent VS Code/Jupyter
  percent-cell `.py` file.
- **Agent-native comparison:** Boyle used a notebook workflow an agent might
  naturally choose; Laplace used a percent-cell `.py` workflow. This run is less
  controlled, but it provides corroborating evidence.

The package includes:

- `index.html`: tabbed interactive Plotly report
- `report-print.html`: print/PDF HTML version with every tab expanded as a report section
- `report.pdf`: PDF version of the report, generated from `report-print.html`
- `report.md`: Markdown narrative report
- `data/`: CSV evidence used by the report
- `sanitized-logs/`: sanitized Codex JSONL session logs for all four workers
- `source-artifacts/`: final `.ipynb` and percent-cell `.py` artifacts produced by the workers
- `scripts/build_report.py`: standard-library Python script that regenerates `index.html`
- `assets/plotly-2.35.2.min.js`: vendored Plotly bundle used by `index.html`
- `assets/report-*.png`: static Matplotlib figures used by `report.md`

## Rebuild

From this folder:

```bash
python scripts/sanitize_logs.py
python scripts/sanitize_logs.py --check
python scripts/build_report.py
wkhtmltopdf --enable-local-file-access --margin-top 22mm --margin-bottom 16mm --margin-left 14mm --margin-right 14mm report-print.html report.pdf
```

No Python packages are required to rebuild the HTML report. The PDF build uses
`wkhtmltopdf` when available.

The generated HTML reads only files included in this package. It does not need
access to `~/.codex` or the original working directory.

During rebuild, `scripts/build_report.py` validates the included token-usage CSV
rows against the included sanitized JSONL logs. If the cumulative CSV totals no longer
match the summed `last_token_usage` events in the logs, the build fails.

## Notes

The generated CSV files are included so the report can be rebuilt without the
original working repository. The sanitized logs are included for auditability and
for anyone who wants to re-run or extend the extraction logic without publishing
the full raw Codex transcripts.

The cost estimates use GPT-5.5 API rates:

- fresh input: $5.00 per 1M tokens
- cached input: $0.50 per 1M tokens
- output: $30.00 per 1M tokens

Cost comparisons are best read as observed estimates. Prompt caching affects
the split between fresh and cached input, especially on the first model call of
these sessions. Total tokens, model calls, runtime, and final artifact size are
less sensitive to that cache split.
