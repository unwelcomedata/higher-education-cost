# higher-education-cost — Dataset Codebook
Generated: 2026-10-12

## Columns

### `sector`
- **Type**: `str`
- **Non-null**: 423 / 423 (100.0%)
- **Description**: Human-readable sector name (All items, College tuition & fees, Medical care (all), Medical care services, Prescription drugs, Gasoline, Energy, Shelter, Hospital services).

### `series_id`
- **Type**: `str`
- **Non-null**: 423 / 423 (100.0%)
- **Description**: BLS CPI-U series ID (CUUR0000… = CPI-U, U.S. city average, not seasonally adjusted) this sector comes from — provenance.

### `year`
- **Type**: `int32`
- **Non-null**: 423 / 423 (100.0%)
- **Description**: Calendar year (1979 … latest full year), the annual-average observation.

### `value`
- **Type**: `float64`
- **Non-null**: 423 / 423 (100.0%)
- **Description**: Raw CPI-U annual-average index value for this sector·year, on BLS's published 1982-84 = 100 reference base (irrelevant once re-indexed below).

### `value_1979`
- **Type**: `float64`
- **Non-null**: 423 / 423 (100.0%)
- **Description**: The sector's own CPI-U annual-average index value in the 1979 base year — the divisor used to re-index the sector to 100.

### `index_1979base`
- **Type**: `float64`
- **Non-null**: 423 / 423 (100.0%)
- **Description**: value ÷ value_1979 × 100 — the sector's price level re-indexed so 1979 = 100. The charted line value; its height in a later year is the cumulative price change since 1979 (e.g. 400 = prices quadrupled).

### `in_headline`
- **Type**: `bool`
- **Non-null**: 423 / 423 (100.0%)
- **Description**: TRUE for the 8 sectors covering the full 1979 common window; FALSE for Hospital services (CPI series starts Dec 1996, so it is excluded from the 1979-base headline chart).

## Notes

Source: U.S. Bureau of Labor Statistics — Consumer Price Index for All Urban
Consumers (CPI-U), U.S. city average, NOT seasonally adjusted (CUUR0000… series).
Public domain (U.S. federal government work). Annual averages (M13), 1979–latest.

What this is: the sector subindices behind the project's reframed headline — "has
the cost of higher education outpaced general inflation and the other 'big'
sectors?". Each sector is re-indexed to 100 at the 1979 base year; the line that
climbs highest has risen most. College tuition & fees is reliably the steepest.

Load-bearing caveats:
- Common base is 1979 because the college-tuition subindex (CUUR0000SEEB01)
  begins December 1978; every other sector reaches further back and is truncated
  to the common start. Hospital services (CUUR0000SEMD) begins December 1996 and
  is excluded from the 1979 headline window (in_headline = FALSE).
- NSA only — never mixed with seasonally-adjusted (CUUS/CUSR) series. Gasoline is
  CUUR0000SETB01 (unadjusted), never its CUUS twin.
- CPI subindices embed BLS hedonic quality adjustment and periodic weight updates.
  For these rising cost sectors that effect is minor; disclosed for completeness.
- The college-tuition subindex tracks PUBLISHED (sticker-ish) price movement, not
  net-of-grant-aid price.
Prior art: AEI / Mark J. Perry "Chart of the Century" is the same chart over a
~2000 window; this dataset extends it to 1979 with its own framing (cited, not
copied).
