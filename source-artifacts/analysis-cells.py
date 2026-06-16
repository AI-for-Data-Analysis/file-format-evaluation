# %% [markdown]
# # Seattle Public Library Checkout Format Experiment
#
# Analysis question: How have Seattle Public Library physical vs. digital checkout
# totals changed across complete years, and which recent complete year shows the
# largest digital share?
#
# This file starts intentionally minimal. The agent should edit it directly,
# execute it, inspect targeted outputs, and add interpretation based on those
# outputs.

# %%
import os
from pathlib import Path

matplotlib_config_dir = Path(__file__).resolve().parent / ".matplotlib-cache"
matplotlib_config_dir.mkdir(exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(matplotlib_config_dir))

import matplotlib.pyplot as plt
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 120)

project_root = Path(__file__).resolve().parents[2]
data_path = project_root / "seattle-public-library" / "combined_checkout_totals_by_month_usageclass.csv"
assets_dir = Path(__file__).resolve().parent / "reports" / "assets"
assets_dir.mkdir(parents=True, exist_ok=True)

monthly_checkouts = pd.read_csv(data_path)

print("Row meaning: one row is one usageclass in one month of one checkout year.")
print("Input file:", data_path)
print("Shape:", monthly_checkouts.shape)
print("Columns:", list(monthly_checkouts.columns))
print()
print("First five rows:")
print(monthly_checkouts.head())

# %%
print("Usage classes and row counts:")
print(monthly_checkouts["usageclass"].value_counts(dropna=False))
print()
print("Year range:")
print(monthly_checkouts["checkout_year"].min(), "to", monthly_checkouts["checkout_year"].max())

# %%
usage_classes_to_compare = ["Digital", "Physical"]
comparison_rows = monthly_checkouts[monthly_checkouts["usageclass"].isin(usage_classes_to_compare)].copy()

months_per_year_usageclass = (
    comparison_rows.groupby(["checkout_year", "usageclass"])["checkout_month"]
    .nunique()
    .reset_index(name="month_count")
)

months_wide = months_per_year_usageclass.pivot(
    index="checkout_year",
    columns="usageclass",
    values="month_count",
).reset_index()

months_wide = months_wide.fillna(0)
complete_year_flags = (
    (months_wide["Digital"] == 12)
    & (months_wide["Physical"] == 12)
)
complete_years = months_wide.loc[complete_year_flags, "checkout_year"].tolist()

print("Month counts by usage class near dataset edges:")
print(pd.concat([months_wide.head(5), months_wide.tail(5)]))
print()
print("Complete years with 12 digital months and 12 physical months:")
print(complete_years)

# %%
complete_year_rows = comparison_rows[comparison_rows["checkout_year"].isin(complete_years)].copy()

annual_by_usageclass = (
    complete_year_rows.groupby(["checkout_year", "usageclass"])["total_checkouts"]
    .sum()
    .reset_index(name="annual_checkouts")
)

annual_totals = (
    annual_by_usageclass.groupby("checkout_year")["annual_checkouts"]
    .sum()
    .reset_index(name="all_usageclass_checkouts")
)

annual_summary = annual_by_usageclass.pivot(
    index="checkout_year",
    columns="usageclass",
    values="annual_checkouts",
).reset_index()

annual_summary = annual_summary.merge(annual_totals, on="checkout_year", how="left")
annual_summary["digital_share"] = annual_summary["Digital"] / annual_summary["all_usageclass_checkouts"]
annual_summary["physical_share"] = annual_summary["Physical"] / annual_summary["all_usageclass_checkouts"]
annual_summary["digital_minus_physical"] = annual_summary["Digital"] - annual_summary["Physical"]

annual_summary = annual_summary.sort_values("checkout_year").reset_index(drop=True)

summary_csv_path = assets_dir / "annual_physical_digital_checkout_summary.csv"
annual_summary.to_csv(summary_csv_path, index=False)

print("Annual complete-year summary:")
print(annual_summary)
print()
print("Saved CSV:", summary_csv_path)

# %%
recent_complete_years = annual_summary.tail(5).copy()
largest_recent_digital_share = recent_complete_years.sort_values(
    "digital_share",
    ascending=False,
).iloc[0]

largest_overall_digital_share = annual_summary.sort_values(
    "digital_share",
    ascending=False,
).iloc[0]

chart_path = assets_dir / "annual_physical_digital_checkout_trends.png"

fig, first_axis = plt.subplots(figsize=(10, 6))

first_axis.plot(
    annual_summary["checkout_year"],
    annual_summary["Physical"],
    marker="o",
    label="Physical checkouts",
)
first_axis.plot(
    annual_summary["checkout_year"],
    annual_summary["Digital"],
    marker="o",
    label="Digital checkouts",
)
first_axis.set_title("Seattle Public Library Annual Checkouts by Usage Class")
first_axis.set_xlabel("Complete checkout year")
first_axis.set_ylabel("Annual checkouts")
first_axis.legend(loc="upper left")
first_axis.grid(True, axis="y", alpha=0.3)

second_axis = first_axis.twinx()
second_axis.plot(
    annual_summary["checkout_year"],
    annual_summary["digital_share"],
    color="black",
    linestyle="--",
    marker="s",
    label="Digital share",
)
second_axis.set_ylabel("Digital share of annual checkouts")
second_axis.set_ylim(0, 0.8)
second_axis.legend(loc="upper right")

fig.tight_layout()
fig.savefig(chart_path, dpi=150)
plt.close(fig)

print("Recent complete years checked for largest digital share:")
print(recent_complete_years[["checkout_year", "Digital", "Physical", "digital_share"]])
print()
print("Largest digital share among recent complete years:")
print(
    f"{int(largest_recent_digital_share['checkout_year'])}: "
    f"{largest_recent_digital_share['digital_share']:.1%} digital share "
    f"({int(largest_recent_digital_share['Digital']):,} digital; "
    f"{int(largest_recent_digital_share['Physical']):,} physical)"
)
print()
print("Largest digital share among all complete years:")
print(
    f"{int(largest_overall_digital_share['checkout_year'])}: "
    f"{largest_overall_digital_share['digital_share']:.1%} digital share "
    f"({int(largest_overall_digital_share['Digital']):,} digital; "
    f"{int(largest_overall_digital_share['Physical']):,} physical)"
)
print()
print("Saved chart:", chart_path)

# %% [markdown]
# ## Interpretation
#
# This analysis uses `combined_checkout_totals_by_month_usageclass.csv`, where one
# row is one usage class in one month of one checkout year. To avoid partial-year
# comparisons, it keeps only years with 12 digital months and 12 physical months:
# 2006 through 2025.
#
# Physical checkouts were much larger than digital checkouts from 2006 through
# 2019, but physical totals generally declined after their late-2000s peak while
# digital totals rose steadily. Digital checkouts first exceeded physical
# checkouts in 2020, when physical circulation dropped sharply and digital
# circulation continued growing. From 2021 through 2025, digital remained larger
# than physical, although the digital share moved up and down rather than rising
# every year.
#
# Defining "recent complete years" as the latest five complete years in the file
# (2021-2025), 2024 has the largest recent digital share at about 64.5% of annual
# checkouts. Across all complete years, 2020 has the largest digital share at
# about 71.2%.
