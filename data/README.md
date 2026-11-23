# Data

The data comes from **LinkedIn Talent Insights** company reports and is licensed, so it is **not included** in this repository. The `.gitignore` keeps every data file out of git.

## Expected layout

```
data/
├── raw/
│   ├── to_merge/<parent>/   one LTI report (.xlsx) per subsidiary of a parent company
│   ├── in/                  one LTI report (.xlsx) per consulting supplier
│   └── filter/
│       ├── Consulting Firms.xlsx      column "Consulting Company"
│       └── Automotive Companies.xlsx  column "Company"
└── processed/
    ├── combined.xlsx                  output of src/prepare_data.py combine
    └── company_movements.csv          output of src/anonymize.py, used by the notebooks
```

Each LTI report has 12 sheets: Overview, Locations, Company Movements, Location Movements, Industry Movements, Titles, Skills, Attrition by Functions, Attrition by Locations, Schools, Degrees, Fields of Study. The notebooks only use **Company Movements**.

## `company_movements.csv`

| Column | Type | Meaning |
|---|---|---|
| `supplier` | text | Anonymized consulting supplier (S01–S41) |
| `counterparty` | text | Anonymized company people moved to/from (C0001…) |
| `is_consulting` | 0/1 | Counterparty is a consulting company |
| `is_automotive` | 0/1 | Counterparty is an automotive company |
| `departures` | int | People who left the supplier for the counterparty |
| `hires` | int | People who joined the supplier from the counterparty |
| `net_change` | int | `hires − departures` |
| `ratio` | float | Signed ratio: `hires / departures`, negative (`−departures / hires`) when departures are higher |
