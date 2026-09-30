"""Web ingestion utilities.

Handles three source types:
  - html_table  : pandas read_html on a static page
  - html_scrape : BeautifulSoup for custom element extraction
  - csv / json  : direct download and save to data/raw

All raw files land in data/raw unchanged. Call load_config() once per notebook
to get paths and source definitions from config.yaml.
"""

from __future__ import annotations

import io
import json
import time
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import yaml
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config(config_path: str | Path = "config.yaml") -> dict[str, Any]:
    """Load project config.yaml and return it as a dict."""
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def raw_path(cfg: dict, filename: str) -> Path:
    """Return a Path inside data/raw, creating the directory if needed."""
    p = Path(cfg["paths"]["data_raw"]) / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_CACHE_DIR: Path | None = None


def _get_cache_dir(cfg: dict) -> Path:
    """Return the cache directory (data/raw by default)."""
    global _CACHE_DIR
    if _CACHE_DIR is None:
        _CACHE_DIR = Path(cfg["paths"]["data_raw"])
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR


def fetch_html(url: str, headers: dict | None = None, timeout: int = 30) -> str:
    """Fetch a URL and return the response text.

    Raises requests.HTTPError on non-2xx status.
    """
    hdrs = {**_DEFAULT_HEADERS, **(headers or {})}
    resp = requests.get(url, headers=hdrs, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def fetch_cached(
    url: str,
    filename: str,
    cfg: dict,
    max_age_hours: float = 24.0,
    headers: dict | None = None,
    timeout: int = 30,
) -> str:
    """Fetch a URL with local file caching.

    If a cached file exists and is younger than max_age_hours, returns its
    contents without making a network request. Otherwise fetches, saves to
    data/raw/{filename}, and returns the content.

    Args:
        url:            URL to fetch.
        filename:       Cache filename (saved in data/raw/).
        cfg:            Loaded config dict.
        max_age_hours:  Re-fetch if cache is older than this (0 = always fetch).
        headers:        Optional extra HTTP headers.
        timeout:        Request timeout in seconds.

    Returns:
        Response text (from cache or network).
    """
    cache_path = _get_cache_dir(cfg) / filename
    if cache_path.exists() and max_age_hours > 0:
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < max_age_hours:
            return cache_path.read_text(encoding="utf-8")

    text = fetch_html(url, headers=headers, timeout=timeout)
    cache_path.write_text(text, encoding="utf-8")
    return text


def fetch_with_retry(
    url: str,
    headers: dict | None = None,
    timeout: int = 30,
    max_retries: int = 3,
    rate_limit_seconds: float = 1.5,
) -> str:
    """Fetch a URL with rate limiting and exponential backoff on 429s.

    Args:
        url:                 URL to fetch.
        headers:             Optional extra HTTP headers.
        timeout:             Request timeout in seconds.
        max_retries:         Max retry attempts on 429/5xx.
        rate_limit_seconds:  Minimum delay between requests.

    Returns:
        Response text.

    Raises:
        requests.HTTPError after exhausting retries.
    """
    hdrs = {**_DEFAULT_HEADERS, **(headers or {})}
    time.sleep(rate_limit_seconds)

    for attempt in range(max_retries + 1):
        resp = requests.get(url, headers=hdrs, timeout=timeout)
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt < max_retries:
                wait = rate_limit_seconds * (2 ** attempt)
                print(f"  ⚠ {resp.status_code} on {url} — retrying in {wait:.0f}s")
                time.sleep(wait)
                continue
        resp.raise_for_status()
        return resp.text

    resp.raise_for_status()  # will raise on the last failed attempt
    return ""  # unreachable


def fetch_html_js(url: str, wait_selector: str | None = None, timeout: int = 30000) -> str:
    """Fetch a JS-rendered page using Playwright (headless Chromium).

    Use this when fetch_html() returns an empty or incomplete page.
    Requires: playwright install chromium

    Args:
        url:           Page URL.
        wait_selector: Optional CSS selector to wait for before returning HTML.
        timeout:       Playwright timeout in milliseconds.
    """
    from playwright.sync_api import sync_playwright  # lazy import

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(extra_http_headers=_DEFAULT_HEADERS)
        page.goto(url, timeout=timeout)
        if wait_selector:
            page.wait_for_selector(wait_selector, timeout=timeout)
        else:
            page.wait_for_load_state("networkidle", timeout=timeout)
        html = page.content()
        browser.close()
    return html


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_html_table(html: str, table_index: int = 0) -> pd.DataFrame:
    """Extract a <table> from HTML by index and return it as a DataFrame.

    Cleans up column names: lowercase, spaces → underscores.
    """
    tables = pd.read_html(html)
    if not tables:
        raise ValueError("No tables found in the provided HTML.")
    if table_index >= len(tables):
        raise IndexError(
            f"table_index {table_index} out of range — page has {len(tables)} table(s)."
        )
    df = tables[table_index]
    df.columns = [
        str(c).strip().lower().replace(" ", "_").replace("-", "_")
        for c in df.columns
    ]
    return df


def parse_html_scrape(
    html: str,
    row_selector: str,
    field_map: dict[str, str],
) -> pd.DataFrame:
    """Scrape structured rows from HTML using CSS selectors.

    Args:
        html:          Raw HTML string.
        row_selector:  CSS selector that matches each "row" element.
        field_map:     Dict mapping output column name → CSS selector
                       relative to each row element.
                       Use '' (empty string) to get the row's own text.

    Example:
        parse_html_scrape(html, "tr.data-row", {"name": "td.name", "value": "td.val"})
    """
    soup = BeautifulSoup(html, "lxml")
    rows = soup.select(row_selector)
    records = []
    for row in rows:
        record: dict[str, str] = {}
        for col, selector in field_map.items():
            el = row.select_one(selector) if selector else row
            record[col] = el.get_text(" ", strip=True) if el else ""
        records.append(record)
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def download_file(url: str, dest: Path, headers: dict | None = None, timeout: int = 60) -> Path:
    """Stream-download a file (CSV, JSON, zip, etc.) to dest and return the path."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    hdrs = {**_DEFAULT_HEADERS, **(headers or {})}
    with requests.get(url, headers=hdrs, timeout=timeout, stream=True) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
    return dest


# ---------------------------------------------------------------------------
# Source-driven ingest (reads config.yaml sources block)
# ---------------------------------------------------------------------------

def ingest_source(
    name: str,
    cfg: dict,
    save_raw: bool = True,
    js_wait_selector: str | None = None,
    row_selector: str | None = None,
    field_map: dict[str, str] | None = None,
    rate_limit_seconds: float = 1.0,
) -> pd.DataFrame:
    """Ingest a named source from config.yaml and return a DataFrame.

    Args:
        name:               Key under `sources:` in config.yaml.
        cfg:                Loaded config dict (from load_config()).
        save_raw:           If True, save the raw HTML/bytes to data/raw/.
        js_wait_selector:   Passed to fetch_html_js() if js_render is true.
        row_selector:       Required for html_scrape type.
        field_map:          Required for html_scrape type.
        rate_limit_seconds: Polite delay before fetching.
    """
    source = cfg["sources"][name]
    url: str = source["url"]
    source_type: str = source.get("type", "html_table")
    js_render: bool = source.get("js_render", False)
    table_index: int = source.get("table_index", 0)

    time.sleep(rate_limit_seconds)

    if source_type == "csv":
        dest = raw_path(cfg, f"{name}.csv")
        download_file(url, dest)
        return pd.read_csv(dest, encoding=cfg["settings"]["encoding"])

    if source_type == "json":
        dest = raw_path(cfg, f"{name}.json")
        download_file(url, dest)
        with open(dest, encoding=cfg["settings"]["encoding"]) as f:
            data = json.load(f)
        return pd.json_normalize(data)

    # HTML-based types
    html = fetch_html_js(url, wait_selector=js_wait_selector) if js_render else fetch_html(url)

    if save_raw:
        raw_path(cfg, f"{name}.html").write_text(html, encoding="utf-8")

    if source_type == "html_table":
        return parse_html_table(html, table_index=table_index)

    if source_type == "html_scrape":
        if row_selector is None or field_map is None:
            raise ValueError("html_scrape requires row_selector and field_map arguments.")
        return parse_html_scrape(html, row_selector, field_map)

    raise ValueError(f"Unknown source type '{source_type}'. Use: html_table, html_scrape, csv, json.")


# ---------------------------------------------------------------------------
# Project-specific ingest — higher-education-cost
# ---------------------------------------------------------------------------
#
# Three authoritative U.S. federal sources (all public domain):
#   1. IPEDS (NCES)         — per-survey, per-year ZIPs of CSVs.
#   2. College Scorecard    — one bulk ZIP (Dept. of Education).
#   3. BLS CPI-U            — via the BLS public timeseries API (the
#                             download.bls.gov flat-file host hard-blocks
#                             automated GETs with a 403, so the API is used).
#
# Every function DOWNLOADS the source file verbatim into data/raw/ and returns
# a DataFrame of the raw contents. NO cleaning/transformation happens here —
# that is the job of the 02-clean stage.


def download_ipeds_survey(survey_file: str, cfg: dict, timeout: int = 120) -> Path:
    """Download one IPEDS complete-data-file ZIP into data/raw/ verbatim.

    IPEDS Data Center serves each survey component, each collection year, as a
    zipped CSV at a stable URL pattern:

        https://nces.ed.gov/ipeds/datacenter/data/<SURVEY_FILE>.zip

    where <SURVEY_FILE> is e.g. HD2022, IC2022_AY, F2122_F1A, F2122_F2, EFFY2022.
    (Confirmed live 2026-09-30 — all return 200 + application/x-zip-compressed.)

    Args:
        survey_file: IPEDS file stem WITHOUT the .zip extension (e.g. "HD2022").
        cfg:         Loaded config dict.
        timeout:     Request timeout in seconds (IPEDS ZIPs can be several MB).

    Returns:
        Path to the downloaded ZIP in data/raw/.
    """
    url = f"https://nces.ed.gov/ipeds/datacenter/data/{survey_file}.zip"
    dest = raw_path(cfg, f"ipeds/{survey_file}.zip")
    time.sleep(1.5)  # workspace rate-limit rule (>=1.0s)
    download_file(url, dest, timeout=timeout)
    return dest


def read_ipeds_zip(zip_path: Path) -> pd.DataFrame:
    """Read the primary CSV out of an IPEDS survey ZIP into a DataFrame.

    IPEDS ZIPs contain the data CSV (named like the file stem, lowercased) and
    sometimes a "_rv" revised-data variant. This reads the main (non-_rv) CSV.
    The raw ZIP on disk is the untouched artifact; this is just to load it for
    inspection / DuckDB registration.
    """
    with zipfile.ZipFile(zip_path) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csv_names:
            raise ValueError(f"No CSV inside {zip_path}")
        # Prefer the non-revised file if both exist (e.g. hd2022.csv vs hd2022_rv.csv)
        primary = sorted(csv_names, key=lambda n: ("_rv" in n.lower(), len(n)))[0]
        with zf.open(primary) as fh:
            # latin-1: IPEDS CSVs occasionally carry non-UTF-8 bytes in text fields.
            df = pd.read_csv(io.BytesIO(fh.read()), encoding="latin-1", low_memory=False)
    return df


def ingest_scorecard(cfg: dict, timeout: int = 300) -> tuple[Path, pd.DataFrame]:
    """Download the College Scorecard 'Most Recent Institution-Level Data' ZIP.

    The bulk host moved from ed-public-download.app.cloud.gov (now 404) to
    ed-public-download.scorecard.network (confirmed live 2026-09-30 via the
    data.ed.gov CKAN package listing). The ZIP holds a single CSV with every
    Title IV institution's most-recent cohort: net price, cost of attendance,
    completion rate, and post-enrollment earnings.

    Returns:
        (path_to_zip_in_data_raw, dataframe_of_the_csv_inside).
    """
    url = cfg["sources"]["scorecard"]["url"]
    dest = raw_path(cfg, "scorecard/Most-Recent-Cohorts-Institution.zip")
    time.sleep(1.5)
    download_file(url, dest, timeout=timeout)
    with zipfile.ZipFile(dest) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csv_names:
            raise ValueError(f"No CSV inside {dest}")
        with zf.open(csv_names[0]) as fh:
            df = pd.read_csv(io.BytesIO(fh.read()), encoding="utf-8", low_memory=False)
    return dest, df


def fetch_bls_series(
    series_ids: list[str],
    start_year: int,
    end_year: int,
    annual: bool = True,
    api_key: str | None = None,
    timeout: int = 60,
) -> pd.DataFrame:
    """Fetch one or more BLS series via the public timeseries API (v2).

    Used instead of the download.bls.gov flat files because that host returns a
    403 Akamai block page to automated GETs (confirmed 2026-09-30, even with a
    full browser header set). The public API is keyless for modest use (25
    requests/day, up to 10 years per request); an optional registration key
    (BLS_API_KEY in .env) raises the limits but is NOT required here.

    Args:
        series_ids: BLS series IDs, e.g. ["CUUR0000SA0"] (CPI-U All Items) or
                    ["CUUR0000SEEB01"] (CPI-U college tuition & fees subindex).
        start_year: First year (inclusive).
        end_year:   Last year (inclusive).
        annual:     Request annual averages (M13) in addition to monthly.
        api_key:    Optional BLS registration key.
        timeout:    Request timeout in seconds.

    Returns:
        Long-format DataFrame: series_id, year, period, period_name, value,
        footnotes — the raw API payload rows, untouched.
    """
    url = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
    payload: dict[str, Any] = {
        "seriesid": series_ids,
        "startyear": str(start_year),
        "endyear": str(end_year),
        "annualaverage": annual,
    }
    if api_key:
        payload["registrationkey"] = api_key

    time.sleep(1.5)
    resp = requests.post(
        url, json=payload, headers={"Content-Type": "application/json"}, timeout=timeout
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS API error: {body.get('status')} — {body.get('message')}")

    records: list[dict[str, Any]] = []
    for series in body["Results"]["series"]:
        sid = series["seriesID"]
        for row in series["data"]:
            records.append(
                {
                    "series_id": sid,
                    "year": row["year"],
                    "period": row["period"],
                    "period_name": row["periodName"],
                    "value": row["value"],
                    "footnotes": "; ".join(
                        f.get("text", "") for f in row.get("footnotes", []) if f
                    ),
                }
            )
    return pd.DataFrame(records)
