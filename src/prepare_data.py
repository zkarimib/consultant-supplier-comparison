"""
Data preparation for the consulting supplier talent analysis.

The raw input is one LinkedIn Talent Insights (LTI) company report per consulting
supplier (Excel, 12 sheets each). This module:

1. merges subsidiary reports into one parent-company report (merge_subsidiaries)
2. combines all supplier reports into one workbook, tags each counterparty in
   'Company Movements' as a consulting and/or automotive company, and cleans
   location columns (combine_reports)

Usage:
    python src/prepare_data.py merge   --input data/raw/to_merge/<group> --output data/raw/in/<Group>.xlsx
    python src/prepare_data.py combine --input data/raw/in --filters data/raw/filter --output data/processed/combined.xlsx
"""
import argparse
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

LOCATION_SHEETS = ["Locations", "Location Movements", "Attrition by Locations"]
GROWTH_SHEETS = ["Locations", "Titles", "Skills", "Schools", "Fields of Study"]
ATTRITION_SHEETS = {"Attrition by Functions": "Attrition by Function",
                    "Attrition by Locations": "Attrition by Locations"}
MOVEMENT_SHEETS = {"Company Movements": "Company",
                   "Location Movements": "Location",
                   "Industry Movements": "Industry"}
DIMENSION_SHEETS = {"Locations": "Location", "Titles": "Titles", "Skills": "Skills",
                    "Schools": "Schools", "Fields of Study": "Fields of study"}


# ---------------------------------------------------------------- helpers
def signed_ratio(departures, hires):
    """Hires/departures ratio, negative when a company loses more people than it gains.

    0 departures -> +hires, 0 hires -> -departures,
    departures > hires -> -(departures / hires), otherwise hires / departures
    (same definition as in the LTI export).
    """
    if pd.isnull(departures) or pd.isnull(hires):
        return np.nan
    if departures == 0:
        return hires
    if hires == 0:
        return -departures
    if departures > hires:
        return -departures / hires
    return hires / departures


def read_sheet(path, sheet):
    df = pd.read_excel(path, sheet_name=sheet, index_col=False)
    if sheet == "Degrees":
        df = df.rename(columns={df.columns[0]: "Degree", df.columns[1]: "Company"})
    return df


def excel_files(folder):
    return sorted(p for p in Path(folder).glob("*.xlsx") if not p.name.startswith("~$"))


def growth_from_last_year(df):
    df["1 Year Growth"] = np.where(df["N Last Year Employee"] != 0,
                                   (df["Employees"] - df["N Last Year Employee"]) / df["N Last Year Employee"],
                                   np.nan)
    df["% of employees"] = df["Employees"] / df["Employees"].sum()
    return df


# ------------------------------------------------- step 1: merge subsidiaries
def merge_subsidiaries(input_dir):
    """Merge the LTI reports of a parent company's subsidiaries into one report."""
    files = excel_files(input_dir)
    sheets = pd.ExcelFile(files[0]).sheet_names
    result = {}
    for sheet in sheets:
        parts = []
        for f in files:
            df = read_sheet(f, sheet)
            if "Employees" in df.columns:
                df["N Last Year Employee"] = df["Employees"] / (df["1y growth"] + 1)
                df.loc[df["1y growth"].isnull() | df["Employees"].isnull(), "N Last Year Employee"] = np.nan
            if sheet in ATTRITION_SHEETS:
                df["Average Employee"] = df["% of employees"] * 100
                df["Departures"] = df["Average Employee"] * df["Attrition"]
            parts.append(df)
        df = pd.concat(parts, ignore_index=True)

        if sheet == "Degrees":
            df = df.groupby("Degree").agg({"Company": "mean", "Industry": "first",
                                           "Your company": "first"}).reset_index()
        elif sheet in DIMENSION_SHEETS:
            key = DIMENSION_SHEETS[sheet]
            agg = {"Employees": "sum", "1y hires": "sum", "N Last Year Employee": "sum", "Your %": "first"}
            if "Job posts" in df.columns:
                agg["Job posts"] = "sum"
            df = growth_from_last_year(df.groupby(key).agg(agg).reset_index())
        elif sheet in ATTRITION_SHEETS:
            key = "Function" if sheet == "Attrition by Functions" else "Location"
            df = df.groupby(key).agg({"Attrition": "sum", "Your attrition": "first", "% of employees": "sum",
                                      "Departures": "sum", "Average Employee": "sum"}).reset_index()
            df[ATTRITION_SHEETS[sheet]] = df["Departures"] / df["Average Employee"]
        elif sheet in MOVEMENT_SHEETS:
            df = df.groupby(MOVEMENT_SHEETS[sheet]).agg({"Departures": "sum", "Hires": "sum"}).reset_index()
            df["Net change"] = df["Hires"] - df["Departures"]
            df["Ratio"] = [signed_ratio(d, h) for d, h in zip(df["Departures"], df["Hires"])]
        result[sheet] = df
    return result


# ----------------------------------------------------- step 2: combine reports
def load_filter_list(path, column):
    names = pd.read_excel(path)[column].dropna().astype(str).unique().tolist()
    return sorted(re.escape(n.lower()) for n in names)


def clean_locations(df):
    for word in ["Area", "Greater", "Metropolitan", "City", "County"]:
        df["Location"] = df["Location"].str.replace(word, "", regex=False)
    parts = df["Location"].str.split(",", n=2, expand=True).reindex(columns=range(3))
    df[["City", "County", "Country"]] = parts
    df["Country"] = "Sweden"
    return df


def combine_reports(input_dir, filter_dir):
    """Combine one LTI report per supplier into one table per sheet."""
    consulting = "|".join(load_filter_list(Path(filter_dir) / "Consulting Firms.xlsx", "Consulting Company"))
    automotive = "|".join(load_filter_list(Path(filter_dir) / "Automotive Companies.xlsx", "Company"))

    files = excel_files(input_dir)
    sheets = pd.ExcelFile(files[0]).sheet_names
    for f in files[1:]:
        if set(pd.ExcelFile(f).sheet_names) != set(sheets):
            raise ValueError(f"{f.name} does not have the same sheets as {files[0].name}")

    result = {}
    for sheet in sheets:
        parts = []
        for f in files:
            df = read_sheet(f, sheet)
            if sheet == "Company Movements":
                name = df["Company"].astype(str).str.lower()
                df["Consultant Company"] = name.str.contains(consulting).astype(int)
                df["Automotive Company"] = name.str.contains(automotive).astype(int)
                df["Company"] = name
            df["Company_Name"] = f.stem
            parts.append(df)
        result[sheet] = pd.concat(parts, ignore_index=True)

    for sheet in LOCATION_SHEETS:
        result[sheet] = clean_locations(result[sheet])

    # suppliers without subsidiaries do not have the derived columns yet -> fill them
    for sheet, col in ATTRITION_SHEETS.items():
        df = result[sheet]
        for c in [col, "Average Employee", "Departures"]:
            if c not in df.columns:
                df[c] = np.nan
        df[col] = df[col].fillna(df["Attrition"])
        df["Average Employee"] = df["Average Employee"].fillna(df["% of employees"] * 100)
        df["Departures"] = df["Departures"].fillna(df["Attrition"] * df["Average Employee"])
    for sheet in GROWTH_SHEETS:
        df = result[sheet]
        if "1 Year Growth" not in df.columns:
            df["1 Year Growth"] = np.nan
        df["1 Year Growth"] = df["1 Year Growth"].fillna(df["1y growth"])
    return result


def write_workbook(result, output):
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output) as writer:
        for sheet, df in result.items():
            df.to_excel(writer, sheet_name=sheet, index=False)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["merge", "combine"])
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--filters", help="folder with 'Consulting Firms.xlsx' and 'Automotive Companies.xlsx'")
    a = ap.parse_args()
    if a.step == "merge":
        write_workbook(merge_subsidiaries(a.input), a.output)
    else:
        if not a.filters:
            ap.error("combine needs --filters")
        write_workbook(combine_reports(a.input, a.filters), a.output)
    print(f"Wrote {a.output}")
