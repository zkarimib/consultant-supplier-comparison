"""
Create the anonymized analysis table from the combined workbook.

Only the 'Company Movements' sheet is used in the analysis. Supplier names are
replaced with neutral IDs (S01, S02, ...) and counterparty companies with
C0001, C0002, ... in random order, so the published notebooks show no company
names from the licensed LinkedIn Talent Insights data.

Usage:
    python src/anonymize.py --input data/processed/combined.xlsx --output data/processed/company_movements.csv
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from prepare_data import signed_ratio

COLUMNS = {"Company_Name": "supplier", "Company": "counterparty", "Consultant Company": "is_consulting",
           "Automotive Company": "is_automotive", "Departures": "departures",
           "Hires": "hires", "Net change": "net_change", "Ratio": "ratio"}


def anonymize(df, seed):
    rng = np.random.default_rng(seed)
    suppliers = df["Company_Name"].unique()
    supplier_ids = {name: f"S{i + 1:02d}" for name, i in zip(suppliers, rng.permutation(len(suppliers)))}
    companies = df["Company"].astype(str).str.lower().unique()
    company_ids = {name: f"C{i + 1:04d}" for name, i in zip(companies, rng.permutation(len(companies)))}
    out = df[list(COLUMNS)].rename(columns=COLUMNS)
    out["supplier"] = out["supplier"].map(supplier_ids)
    out["counterparty"] = out["counterparty"].astype(str).str.lower().map(company_ids)
    # recompute the ratio from the counts so every supplier uses the same definition
    out["ratio"] = [signed_ratio(d, h) for d, h in zip(out["departures"], out["hires"])]
    return out.sort_values(["supplier", "departures", "hires"], ascending=[True, False, False])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--seed", type=int, required=True, help="keep this private")
    a = ap.parse_args()
    df = pd.read_excel(a.input, sheet_name="Company Movements")
    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    anonymize(df, a.seed).to_csv(a.output, index=False)
    print(f"Wrote {a.output}")
