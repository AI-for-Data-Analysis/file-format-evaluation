# %% [markdown]
# # Seattle Public Library physical vs digital checkout totals
#
# Analysis question: How have Seattle Public Library physical vs digital checkout
# totals changed across complete years, and which recent complete year shows the
# largest digital share?
#
# Dataset reference used first: `seattle-public-library/README.md`.
#
# Row meaning from the reference: one row in
# `combined_checkout_totals_by_month_usageclass.csv` represents one usage class
# in one month of one year. This file is already aggregated, not title-level raw
# checkout data.

# %%
from pathlib import Path
import os

import pandas as pd

if "__file__" in globals():
    ANALYSIS_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = ANALYSIS_DIR.parents[1]
else:
    PROJECT_ROOT = Path.cwd()
    ANALYSIS_DIR = PROJECT_ROOT / "agent-format-experiment" / "py-cell-agent"

OUTPUT_DIR = ANALYSIS_DIR / "reports" / "assets"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", "/tmp/py-cell-agent-matplotlib-cache")

import matplotlib.pyplot as plt

try:
    display
except NameError:
    def display(value):
        print(value)

DATA_PATH = PROJECT_ROOT / "seattle-public-library" / "combined_checkout_totals_by_month_usageclass.csv"
SUMMARY_CSV_PATH = OUTPUT_DIR / "annual_physical_digital_summary.csv"
CHART_PATH = OUTPUT_DIR / "annual_physical_digital_totals.svg"

print(f"Reading data from: {DATA_PATH}")
print(f"Saving outputs to: {OUTPUT_DIR}")

# Load the monthly totals and check the expected structure.
monthly_checkouts = pd.read_csv(DATA_PATH)

expected_columns = [
    "checkout_year",
    "checkout_month",
    "usageclass",
    "total_checkouts",
    "month_total_checkouts",
    "usageclass_share",
    "title_month_rows",
    "sample_rows",
]

missing_columns = []
for column_name in expected_columns:
    if column_name not in monthly_checkouts.columns:
        missing_columns.append(column_name)

if missing_columns:
    raise ValueError(f"Missing expected columns: {missing_columns}")

print("Columns match the expected schema.")
print(f"Rows: {len(monthly_checkouts):,}")
print(
    "Year range:",
    int(monthly_checkouts["checkout_year"].min()),
    "to",
    int(monthly_checkouts["checkout_year"].max()),
)
print("Usage classes:", sorted(monthly_checkouts["usageclass"].dropna().unique()))

display(monthly_checkouts.head())

# %% [markdown]
# ## Keep complete physical/digital years only
#
# A complete year must have 12 months for both physical and digital usage
# classes. This avoids interpreting partial-year data as a full-year trend.

# %%
physical_digital_rows = monthly_checkouts[
    monthly_checkouts["usageclass"].isin(["Digital", "Physical"])
].copy()

months_by_year_usage = (
    physical_digital_rows.groupby(["checkout_year", "usageclass"])["checkout_month"]
    .nunique()
    .reset_index(name="month_count")
)

complete_year_flags = months_by_year_usage.pivot(
    index="checkout_year",
    columns="usageclass",
    values="month_count",
).reset_index()

complete_year_flags["has_12_digital_months"] = complete_year_flags["Digital"] == 12
complete_year_flags["has_12_physical_months"] = complete_year_flags["Physical"] == 12
complete_year_flags["is_complete_year"] = (
    complete_year_flags["has_12_digital_months"]
    & complete_year_flags["has_12_physical_months"]
)

complete_years = complete_year_flags.loc[
    complete_year_flags["is_complete_year"], "checkout_year"
].tolist()

incomplete_years = complete_year_flags.loc[
    ~complete_year_flags["is_complete_year"],
    ["checkout_year", "Digital", "Physical"],
]

print(f"Complete years retained: {min(complete_years)} to {max(complete_years)}")
print(f"Number of complete years retained: {len(complete_years)}")
print("Incomplete years excluded:")
display(incomplete_years)

complete_monthly_checkouts = physical_digital_rows[
    physical_digital_rows["checkout_year"].isin(complete_years)
].copy()

# %% [markdown]
# ## Build annual physical/digital summary
#
# Annual totals are sums of monthly `total_checkouts`. Digital share is computed
# from annual digital checkouts divided by annual physical plus digital
# checkouts.

# %%
annual_usage_totals = (
    complete_monthly_checkouts.groupby(["checkout_year", "usageclass"])["total_checkouts"]
    .sum()
    .reset_index()
)

annual_wide = annual_usage_totals.pivot(
    index="checkout_year",
    columns="usageclass",
    values="total_checkouts",
).reset_index()

annual_wide = annual_wide.rename(
    columns={
        "checkout_year": "year",
        "Digital": "digital_checkouts",
        "Physical": "physical_checkouts",
    }
)

annual_wide["combined_checkouts"] = (
    annual_wide["digital_checkouts"] + annual_wide["physical_checkouts"]
)
annual_wide["digital_share"] = (
    annual_wide["digital_checkouts"] / annual_wide["combined_checkouts"]
)
annual_wide["physical_share"] = (
    annual_wide["physical_checkouts"] / annual_wide["combined_checkouts"]
)

annual_summary = annual_wide[
    [
        "year",
        "physical_checkouts",
        "digital_checkouts",
        "combined_checkouts",
        "physical_share",
        "digital_share",
    ]
].copy()

annual_summary = annual_summary.sort_values("year").reset_index(drop=True)

print("Annual summary preview:")
display(annual_summary.head())

print("Most recent complete years:")
display(annual_summary.tail())

# Here, "recent complete year" means one of the five most recent complete years.
recent_complete_years = annual_summary.tail(5).copy()
largest_recent_digital_share = recent_complete_years.sort_values(
    "digital_share",
    ascending=False,
).iloc[0]

first_year = annual_summary.iloc[0]
last_year = annual_summary.iloc[-1]

physical_change = (
    last_year["physical_checkouts"] - first_year["physical_checkouts"]
) / first_year["physical_checkouts"]
digital_change = (
    last_year["digital_checkouts"] - first_year["digital_checkouts"]
) / first_year["digital_checkouts"]

print("Five most recent complete years:")
display(
    recent_complete_years[
        ["year", "physical_checkouts", "digital_checkouts", "digital_share"]
    ]
)

print(
    "Largest recent digital share:",
    int(largest_recent_digital_share["year"]),
    f"({largest_recent_digital_share['digital_share']:.1%})",
)
print(
    f"From {int(first_year['year'])} to {int(last_year['year'])}, "
    f"physical checkouts changed by {physical_change:.1%} and "
    f"digital checkouts changed by {digital_change:.1%}."
)

# %%
# Save the annual summary used for the report.
annual_summary.to_csv(SUMMARY_CSV_PATH, index=False)

plt.style.use("seaborn-v0_8-whitegrid")
fig, ax = plt.subplots(figsize=(10, 5.5))

ax.plot(
    annual_summary["year"],
    annual_summary["physical_checkouts"] / 1_000_000,
    marker="o",
    linewidth=2,
    label="Physical",
)
ax.plot(
    annual_summary["year"],
    annual_summary["digital_checkouts"] / 1_000_000,
    marker="o",
    linewidth=2,
    label="Digital",
)

ax.set_title("Seattle Public Library Annual Checkouts by Usage Class")
ax.set_xlabel("Complete year")
ax.set_ylabel("Checkouts, millions")
ax.legend()
ax.margins(x=0.02)
fig.tight_layout()
fig.savefig(CHART_PATH)
plt.show()

print(f"Saved summary table: {SUMMARY_CSV_PATH}")
print(f"Saved chart: {CHART_PATH}")
