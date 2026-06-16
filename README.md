# Notebook vs. Percent-Cell Python for Coding Agents

This folder is a standalone report package for a controlled coding-agent workflow comparison.

It compares:

- direct editing/execution of an `.ipynb` notebook
- direct editing/execution of a VS Code/Jupyter percent-cell `.py` file

The report is self-contained and includes:

- `index.html`: interactive Plotly report
- `report.md`: Markdown narrative report
- `data/`: CSV evidence used by the report
- `raw-logs/`: raw Codex JSONL session logs for both workers
- `source-artifacts/`: final `.ipynb` and percent-cell `.py` artifacts produced by the workers
- `scripts/build_report.py`: standard-library Python script that regenerates `index.html`
- `assets/plotly-2.35.2.min.js`: vendored Plotly bundle used by `index.html`
- `assets/report-*.png`: static Matplotlib figures used by `report.md`

## Rebuild

From this folder:

```bash
python scripts/build_report.py
```

No Python packages are required to rebuild the HTML report.

## Notes

The generated CSV files are included so the report can be rebuilt without the original working repository. The raw logs are included for auditability and for anyone who wants to re-run or extend the extraction logic.

The cost estimates use GPT-5.5 API rates:

- fresh input: $5.00 per 1M tokens
- cached input: $0.50 per 1M tokens
- output: $30.00 per 1M tokens
