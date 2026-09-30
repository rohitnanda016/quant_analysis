# quant_analysis

Research-grade quantitative analysis workspace.

## FLUID-Q V6.2

V6.2 adds a historical security-identity layer before price repair.

Key principles:
- Point-in-time Nifty 500 membership.
- Historical security identity rather than ticker text alone.
- Verified symbol changes are explicit and auditable.
- No interpolation or synthetic prices.
- Remaining price gaps must be resolved from NSE security-wise archives/security-master/corporate-action evidence before backtesting.

### Stage A findings

The initial 2022-01-03 to 2022-07-29 dataset contains 76,227 rows across 534 symbols and exposed 12 coverage flags. One important issue is ADANITRANS -> ADANIENSOL, effective 2023-08-24.

This repository deliberately keeps the repair pipeline conservative: unresolved gaps are reported, not silently filled.

## Scripts

- `scripts/build_v6_2_identity.py`
- `scripts/audit_v6_2_gaps.py`

## Usage

```bash
python scripts/build_v6_2_identity.py \
  --prices data/processed/prices_nifty500_raw.csv \
  --membership data/input/nifty500_membership.csv \
  --symbol-map data/input/verified_symbol_map.csv

python scripts/audit_v6_2_gaps.py \
  --prices data/processed/v6_2/prices_with_canonical_symbol.csv \
  --membership data/processed/v6_2/membership_with_canonical_symbol.csv
```
