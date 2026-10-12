# higher-education-cost — Dataset Codebook
Generated: 2026-10-12

## Columns

### `year`
- **Type**: `int32`
- **Non-null**: 112 / 112 (100.0%)
- **Description**: Academic/fiscal year of the national aggregate.

### `function`
- **Type**: `str`
- **Non-null**: 112 / 112 (100.0%)
- **Description**: Harmonized IPEDS expense function: instruction, institutional_support (= admin), academic_support, or student_services.

### `per_fte`
- **Type**: `float64`
- **Non-null**: 44 / 112 (39.3%)
- **Description**: National spending on this function per 12-month FTE student (summed $ / summed FTE), in that year's nominal dollars.

### `share`
- **Type**: `float64`
- **Non-null**: 112 / 112 (100.0%)
- **Description**: This function's share of core functional spending nationally (summed function $ / summed core-function $). The honest-framing metric.

### `source`
- **Type**: `str`
- **Non-null**: 112 / 112 (100.0%)
- **Description**: Data source for the row: 'delta' (NCES Delta Cost Project, 1987-2012) or 'ipeds_raw' (raw IPEDS finance tail, 2013+). The seam is at 2012.

## Notes

Source: NCES Delta Cost Project Database (1987-2012) + raw IPEDS Finance
(2013+), national, public + private-nonprofit institutions. Public domain.
Spending by harmonized IPEDS function; "admin" = institutional support only.

⭐ Honest finding: NON-INSTRUCTIONAL spending (student services + academic
support + institutional support) grew as a share of core spending while
instruction's share fell. Institutional support (admin) ALONE is roughly flat —
the rise is NOT "administrators alone exploded." Delta is a derived product
(Jaquette & Parra); seam at 2012 between Delta and the raw-IPEDS tail; GASB
isolates O&M-of-plant while FASB distributes it (O&M excluded from the functions).
