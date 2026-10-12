# higher-education-cost — Dataset Codebook
Generated: 2026-10-12

## Columns

### `year_start`
- **Type**: `int32`
- **Non-null**: 442 / 442 (100.0%)
- **Description**: Starting calendar year of the academic year (e.g. 1963 for 1963-64).

### `control`
- **Type**: `str`
- **Non-null**: 442 / 442 (100.0%)
- **Description**: Institution control: all / public / private.

### `level`
- **Type**: `str`
- **Non-null**: 442 / 442 (100.0%)
- **Description**: Institution level: all (all levels) or 4-year.

### `value_constant`
- **Type**: `float64`
- **Non-null**: 442 / 442 (100.0%)
- **Description**: Average published undergraduate tuition & fees in CONSTANT dollars (NCES's own CPI-U All-Items adjustment; base = base_year).

### `base_year`
- **Type**: `int32`
- **Non-null**: 442 / 442 (100.0%)
- **Description**: Starting year of the constant-dollar base academic year (e.g. 2023 for constant 2023-24 dollars).

## Notes

Source: NCES Digest of Education Statistics Table 330.10 — average undergraduate
tuition and fees for full-time students at degree-granting institutions, by level
and control, selected academic years 1963-64 -> latest. Public domain. Constant
dollars are NCES's own CPI-U All-Items adjustment.

Caveats: NATIONAL AVERAGES, not per-institution; the institution universe and
room/board basis shifted across Digest editions; published (sticker) price, not
net-of-grant-aid; constant dollars use CPI-U All-Items (a general deflator).
