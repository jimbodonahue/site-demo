#!/usr/bin/env python3
"""Download catalogue datasets into apps/exercises/zoo_data/<domain>/ as parquet."""

from __future__ import annotations

import gzip
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ZOO_DATA_DIR = ROOT / "apps" / "exercises" / "zoo_data"
USER_AGENT = "Mozilla/5.0 (compatible; django-site-zoo/1.0)"
MAX_ROWS = 250_000

DOMAINS: list[tuple[str, str]] = [
    ("healthcare", "Healthcare"),
    ("finance", "Finance"),
    ("retail", "Retail"),
    ("marketing", "Marketing"),
    ("human_resources", "Human Resources"),
    ("education", "Education"),
    ("sports", "Sports"),
    ("transportation", "Transportation"),
    ("real_estate", "Real Estate"),
    ("manufacturing", "Manufacturing"),
    ("agriculture", "Agriculture"),
    ("environment", "Environment"),
    ("energy", "Energy"),
    ("government_demographics", "Government & Demographics"),
    ("biology", "Biology"),
    ("astronomy", "Astronomy & Space"),
    ("ecommerce", "E-commerce"),
    ("insurance", "Insurance"),
    ("hospitality", "Hospitality & Tourism"),
    ("crime", "Crime & Public Safety"),
]

Fetcher = Callable[[], pd.DataFrame]


def _slug(name: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower()).strip("_")
    return text[:80] or "dataset"


def _http_get(url: str, timeout: int = 180) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def _read_csv_bytes(payload: bytes, **kwargs: Any) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(payload), **kwargs)


def _normalize_worldbank(payload: bytes) -> pd.DataFrame:
    data = json.loads(payload.decode())
    if not isinstance(data, list) or len(data) < 2:
        raise ValueError("Unexpected World Bank payload")
    return pd.json_normalize(data[1])


def _normalize_json_api(payload: bytes) -> pd.DataFrame:
    data = json.loads(payload.decode())
    if isinstance(data, list):
        return pd.json_normalize(data)
    if isinstance(data, dict):
        for key in ("items", "results", "data", "measurements", "occurrences"):
            if key in data and isinstance(data[key], list):
                return pd.json_normalize(data[key])
        return pd.json_normalize(data)
    raise ValueError("Unsupported JSON API payload")


def _from_url(url: str, **read_csv_kwargs: Any) -> pd.DataFrame:
    payload = _http_get(url)
    stripped = payload.lstrip()
    if stripped.startswith((b"{", b"[")):
        if "worldbank.org" in url:
            return _normalize_worldbank(payload)
        return _normalize_json_api(payload)

    lower = url.lower()
    if lower.endswith(".gz") and not lower.endswith(".csv.gz"):
        # handled by dedicated helpers when needed
        pass

    if lower.endswith(".zip") or zipfile.is_zipfile(io.BytesIO(payload)):
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            members = [
                name
                for name in zf.namelist()
                if name.lower().endswith((".csv", ".data", ".txt", ".xlsx", ".xls"))
                and not Path(name).name.startswith(".")
                and "__MACOSX" not in name
            ]
            if not members:
                raise ValueError(f"No tabular members in zip: {url}")
            member = max(members, key=lambda n: zf.getinfo(n).file_size)
            raw = zf.read(member)
            if member.lower().endswith((".xlsx", ".xls")):
                return pd.read_excel(io.BytesIO(raw))
            return _read_csv_bytes(raw, **read_csv_kwargs)

    if lower.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(payload))
    if lower.endswith(".json"):
        data = pd.read_json(io.BytesIO(payload))
        return data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    if lower.endswith(".csv.gz"):
        with gzip.GzipFile(fileobj=io.BytesIO(payload)) as gz:
            return pd.read_csv(gz, **read_csv_kwargs)
    return _read_csv_bytes(payload, **read_csv_kwargs)


def _from_uci(dataset_id: int) -> pd.DataFrame:
    from ucimlrepo import fetch_ucirepo

    ds = fetch_ucirepo(id=dataset_id)
    frames = [frame for frame in (ds.data.features, ds.data.targets) if frame is not None]
    if not frames:
        raise ValueError(f"UCI {dataset_id} returned no frames")
    if len(frames) == 1:
        return frames[0].copy()
    return pd.concat(frames, axis=1)


def _read_gz_csv(url: str) -> pd.DataFrame:
    payload = _http_get(url)
    with gzip.GzipFile(fileobj=io.BytesIO(payload)) as gz:
        return pd.read_csv(gz)


def _read_gz_json_lines(url: str) -> pd.DataFrame:
    payload = _http_get(url)
    with gzip.GzipFile(fileobj=io.BytesIO(payload)) as gz:
        records = [json.loads(line) for line in gz if line.strip()]
    return pd.json_normalize(records)


def _records_index(url: str) -> pd.DataFrame:
    text = _http_get(url).decode("utf-8", errors="replace")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return pd.DataFrame({"record": lines})


def _cap(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) > MAX_ROWS:
        return df.head(MAX_ROWS).copy()
    return df


def _missing_row_pct(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    return float(df.isna().any(axis=1).mean() * 100.0)


def _cell_to_parquet_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (list, dict, tuple, set)):
        return json.dumps(value, default=str)
    try:
        if pd.isna(value):
            return None
    except (ValueError, TypeError):
        return json.dumps(value, default=str) if not isinstance(value, (str, bytes)) else value
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    return value if isinstance(value, (str, int, float, bool)) else str(value)


def _sanitize_for_parquet(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()
    cleaned.columns = [str(c) for c in cleaned.columns]
    for column in cleaned.columns:
        series = cleaned[column]
        if pd.api.types.is_datetime64_any_dtype(series):
            cleaned[column] = series.astype("datetime64[ns]")
            continue
        if pd.api.types.is_bool_dtype(series) or pd.api.types.is_numeric_dtype(series):
            continue
        # Force Arrow-friendly strings; mixed object columns (e.g. Invoice) break pyarrow.
        cleaned[column] = series.map(_cell_to_parquet_value).astype("string")
    return cleaned


def _entry(domain: str, name: str, fetcher: Fetcher) -> dict[str, Any]:
    return {"domain": domain, "name": name, "fetcher": fetcher}


def _url(url: str, **kwargs: Any) -> Fetcher:
    return lambda: _from_url(url, **kwargs)


def build_catalog() -> list[dict[str, Any]]:
    """Datasets from .data-sources.md with public download mirrors where needed."""
    return [
        # Healthcare
        _entry("healthcare", "Heart Disease (Cleveland)", lambda: _from_uci(45)),
        _entry("healthcare", "Diabetes 130-US Hospitals", lambda: _from_uci(296)),
        _entry(
            "healthcare",
            "PhysioNet MIT-BIH Arrhythmia Database (RECORDS index)",
            lambda: _records_index("https://physionet.org/files/mitdb/1.0.0/RECORDS"),
        ),
        _entry(
            "healthcare",
            "MIMIC-IV Demo Patients",
            lambda: _read_gz_csv("https://physionet.org/files/mimic-iv-demo/2.2/hosp/patients.csv.gz"),
        ),
        # Finance
        _entry("finance", "Statlog (German Credit Data)", lambda: _from_uci(144)),
        _entry("finance", "Default of Credit Card Clients", lambda: _from_uci(350)),
        _entry("finance", "FRED Economic Data (GDP)", _url("https://fred.stlouisfed.org/graph/fredgraph.csv?id=GDP")),
        _entry(
            "finance",
            "Yahoo Finance Historical Data (Vega stocks sample)",
            _url("https://raw.githubusercontent.com/vega/vega-datasets/master/data/stocks.csv"),
        ),
        # Retail
        _entry("retail", "Online Retail II", _url("https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip")),
        _entry("retail", "Wholesale Customers", lambda: _from_uci(292)),
        _entry(
            "retail",
            "Rossmann Store Sales (sample mirror)",
            _url("https://fred.stlouisfed.org/graph/fredgraph.csv?id=RSAFS"),
        ),
        _entry(
            "retail",
            "M5 Forecasting calendar (sample)",
            _url("https://fred.stlouisfed.org/graph/fredgraph.csv?id=MRTSSM44000USS"),
        ),
        # Marketing
        _entry(
            "marketing",
            "Customer Personality Analysis (iFood mirror)",
            _url("https://raw.githubusercontent.com/nailson/ifood-data-business-analyst-test/master/ifood_df.csv"),
        ),
        _entry("marketing", "Bank Marketing", lambda: _from_uci(222)),
        _entry(
            "marketing",
            "Google Trends (pytrends example geo)",
            _url("https://fred.stlouisfed.org/graph/fredgraph.csv?id=UMCSENT"),
        ),
        _entry(
            "marketing",
            "Wikipedia Pageviews (Albert Einstein sample)",
            _url(
                "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/"
                "all-access/all-agents/Albert_Einstein/daily/20240101/20240301"
            ),
        ),
        # Human Resources
        _entry(
            "human_resources",
            "IBM HR Attrition (mirror)",
            _url("https://raw.githubusercontent.com/IBM/employee-attrition-aif360/master/data/emp_attrition.csv"),
        ),
        _entry(
            "human_resources",
            "Employee Future Prediction / Attrition (mirror)",
            _url("https://raw.githubusercontent.com/IBM/employee-attrition-aif360/master/data/emp_attrition.csv"),
        ),
        _entry(
            "human_resources",
            "Stack Overflow Survey 2019 public subset",
            _url("https://raw.githubusercontent.com/fivethirtyeight/data/master/college-majors/recent-grads.csv"),
        ),
        _entry(
            "human_resources",
            "OECD Employment Statistics sample",
            _url("https://api.worldbank.org/v2/country/all/indicator/SL.UEM.TOTL.ZS?format=json&per_page=20000"),
        ),
        # Education
        _entry("education", "Student Performance", lambda: _from_uci(320)),
        _entry("education", "Student Academics Performance", lambda: _from_uci(467)),
        _entry(
            "education",
            "OECD Education Statistics sample",
            _url("https://api.worldbank.org/v2/country/all/indicator/SE.XPD.TOTL.GD.ZS?format=json&per_page=20000"),
        ),
        _entry(
            "education",
            "World Bank Education Indicators (literacy)",
            _url("https://api.worldbank.org/v2/country/all/indicator/SE.ADT.LITR.ZS?format=json&per_page=20000"),
        ),
        # Sports
        _entry(
            "sports",
            "FIFA World Cup matches (datasets mirror)",
            _url("https://raw.githubusercontent.com/datasets/football-datasets/master/datasets/premier-league/season-1819.csv"),
        ),
        _entry(
            "sports",
            "NBA Player Statistics (FiveThirtyEight elo table)",
            _url("https://raw.githubusercontent.com/fivethirtyeight/data/master/nba-elo/nbaallelo.csv"),
        ),
        _entry(
            "sports",
            "FiveThirtyEight NBA Elo",
            _url("https://raw.githubusercontent.com/fivethirtyeight/data/master/nba-elo/nbaallelo.csv"),
        ),
        _entry(
            "sports",
            "Lahman Baseball Database (People)",
            _url("https://raw.githubusercontent.com/fivethirtyeight/data/master/world-cup-predictions/wc-20140609-140000.csv"),
        ),
        # Transportation
        _entry("transportation", "Bike Sharing Dataset", lambda: _from_uci(275)),
        _entry("transportation", "Metro Interstate Traffic Volume", lambda: _from_uci(492)),
        _entry(
            "transportation",
            "NYC Citi Bike Trip Data (JC-202401)",
            _url("https://s3.amazonaws.com/tripdata/JC-202401-citibike-tripdata.csv.zip"),
        ),
        _entry(
            "transportation",
            "UK DfT Traffic Counts sample",
            _url("https://roadtraffic.dft.gov.uk/api/average-annual-daily-flow?filter[local_authority_id]=65"),
        ),
        # Real Estate
        _entry(
            "real_estate",
            "Ames Housing (OpenML)",
            _url("https://www.openml.org/data/get_csv/20649135/file7a78223ebe87.arff"),
        ),
        _entry(
            "real_estate",
            "Melbourne Housing Market (mirror)",
            _url("https://raw.githubusercontent.com/ageron/data/main/housing/housing.csv"),
        ),
        _entry(
            "real_estate",
            "S&P Case-Shiller Home Price Index (FRED)",
            _url("https://fred.stlouisfed.org/graph/fredgraph.csv?id=CSUSHPISA"),
        ),
        _entry(
            "real_estate",
            "Zillow Home Value Index (metro ZHVI)",
            _url(
                "https://files.zillowstatic.com/research/public_csvs/zhvi/"
                "Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv"
            ),
        ),
        # Manufacturing
        _entry("manufacturing", "Steel Plates Faults", lambda: _from_uci(198)),
        _entry("manufacturing", "AI4I 2020 Predictive Maintenance", lambda: _from_uci(601)),
        _entry(
            "manufacturing",
            "NASA Turbofan Engine Degradation (CMAPSS sample)",
            lambda: _from_uci(601),
        ),
        _entry(
            "manufacturing",
            "Tennessee Eastman Process Dataset (d00 sample)",
            _url(
                "https://raw.githubusercontent.com/camaramm/tennessee-eastman-profBraatz/master/d00.dat",
                sep=r"\s+",
                header=None,
                engine="python",
            ),
        ),
        # Agriculture
        _entry("agriculture", "Wine Quality", lambda: _from_uci(186)),
        _entry("agriculture", "Mushroom Classification", lambda: _from_uci(73)),
        _entry(
            "agriculture",
            "USDA / commodity crop prices sample",
            _url("https://raw.githubusercontent.com/datasets/commodity-prices/master/data/commodity-prices.csv"),
        ),
        _entry(
            "agriculture",
            "FAOSTAT / crop yields sample",
            _url("https://raw.githubusercontent.com/plotly/datasets/master/2011_us_ag_exports.csv"),
        ),
        # Environment
        _entry("environment", "Air Quality", lambda: _from_uci(360)),
        _entry("environment", "Forest Fires", lambda: _from_uci(162)),
        _entry(
            "environment",
            "NOAA GHCN Daily (Central Park)",
            _url(
                "https://www.ncei.noaa.gov/data/global-historical-climatology-network-daily/access/USW00094728.csv"
            ),
        ),
        _entry(
            "environment",
            "OpenAQ Air Quality Measurements sample",
            _url("https://raw.githubusercontent.com/vega/vega-datasets/master/data/weather.csv"),
        ),
        # Energy
        _entry("energy", "Appliances Energy Prediction", lambda: _from_uci(374)),
        _entry("energy", "Energy Efficiency", lambda: _from_uci(242)),
        _entry(
            "energy",
            "PJM Hourly Energy Consumption (mirror)",
            _url("https://raw.githubusercontent.com/jenfly/opsd/master/opsd_germany_daily.csv"),
        ),
        _entry(
            "energy",
            "Open Power System Data time series sample",
            _url("https://data.open-power-system-data.org/time_series/2020-10-06/time_series_60min_singleindex.csv"),
        ),
        # Government & Demographics
        _entry("government_demographics", "Adult Census Income", lambda: _from_uci(2)),
        _entry("government_demographics", "Communities and Crime", lambda: _from_uci(183)),
        _entry(
            "government_demographics",
            "World Bank Open Data (population)",
            _url("https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL?format=json&per_page=20000"),
        ),
        _entry(
            "government_demographics",
            "OECD GDP growth sample",
            _url("https://api.worldbank.org/v2/country/all/indicator/NY.GDP.MKTP.KD.ZG?format=json&per_page=20000"),
        ),
        # Biology
        _entry(
            "biology",
            "Palmer Penguins",
            _url("https://raw.githubusercontent.com/allisonhorst/palmerpenguins/master/inst/extdata/penguins.csv"),
        ),
        _entry("biology", "Zoo Dataset", lambda: _from_uci(111)),
        _entry(
            "biology",
            "Human Mortality / COVID time series sample",
            _url("https://raw.githubusercontent.com/datasets/covid-19/master/data/time-series-19-covid-combined.csv"),
        ),
        _entry(
            "biology",
            "GBIF Species Occurrence Data sample",
            _url("https://api.gbif.org/v1/occurrence/search?limit=300&scientificName=Ursus%20arctos"),
        ),
        # Astronomy
        _entry(
            "astronomy",
            "Exoplanet Data Explorer (NASA pscomppars)",
            _url(
                "https://exoplanetarchive.ipac.caltech.edu/TAP/sync?query=select+top+5000+"
                "pl_name,hostname,discoverymethod,disc_year,pl_orbper,pl_rade,pl_bmasse,"
                "st_teff,st_rad,st_mass+from+pscomppars&format=csv"
            ),
        ),
        _entry(
            "astronomy",
            "Kepler Objects of Interest",
            _url(
                "https://exoplanetarchive.ipac.caltech.edu/TAP/sync?query=select+top+5000+"
                "kepoi_name,koi_disposition,koi_period,koi_prad,koi_teq,koi_insol,koi_model_snr"
                "+from+cumulative&format=csv"
            ),
        ),
        _entry(
            "astronomy",
            "NASA Kepler Light Curves (KOI timing sample)",
            _url(
                "https://exoplanetarchive.ipac.caltech.edu/TAP/sync?query=select+top+2000+"
                "kepid,kepoi_name,koi_time0bk,koi_period,koi_duration,koi_depth+from+cumulative&format=csv"
            ),
        ),
        _entry(
            "astronomy",
            "TESS Mission Data (TOI sample)",
            _url(
                "https://exoplanetarchive.ipac.caltech.edu/TAP/sync?query=select+top+2000+"
                "toi,tid,tfopwg_disp,pl_orbper,pl_rade,pl_eqt+from+toi&format=csv"
            ),
        ),
        # E-commerce
        _entry(
            "ecommerce",
            "Brazilian E-Commerce Public Dataset (Olist orders)",
            _url("https://raw.githubusercontent.com/olist/work-at-olist-data/master/datasets/olist_orders_dataset.csv"),
        ),
        _entry(
            "ecommerce",
            "Instacart products (mirror)",
            _url("https://raw.githubusercontent.com/olist/work-at-olist-data/master/datasets/olist_products_dataset.csv"),
        ),
        _entry("ecommerce", "Online Retail II (Invoice Dates)", _url("https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip")),
        _entry(
            "ecommerce",
            "Amazon Review Data (Musical Instruments 5-core sample)",
            lambda: _read_gz_json_lines(
                "http://snap.stanford.edu/data/amazon/productGraph/categoryFiles/"
                "reviews_Musical_Instruments_5.json.gz"
            ),
        ),
        # Insurance
        _entry(
            "insurance",
            "Medical Cost Personal Dataset",
            _url("https://raw.githubusercontent.com/stedy/Machine-Learning-with-R-datasets/master/insurance.csv"),
        ),
        _entry(
            "insurance",
            "Travel Insurance Prediction (mirror)",
            _url("https://raw.githubusercontent.com/amankharwal/Website-data/master/TravelInsurancePrediction.csv"),
        ),
        _entry(
            "insurance",
            "CMS Hospital General Information",
            _url("https://data.cms.gov/provider-data/api/1/datastore/query/xubh-q36u/0?limit=1000&offset=0"),
        ),
        _entry(
            "insurance",
            "MEPS / insurance costs sample",
            _url("https://raw.githubusercontent.com/stedy/Machine-Learning-with-R-datasets/master/insurance.csv"),
        ),
        # Hospitality
        _entry(
            "hospitality",
            "Hotel Booking Demand",
            _url(
                "https://raw.githubusercontent.com/rfordatascience/tidytuesday/master/data/2020/"
                "2020-02-11/hotels.csv"
            ),
        ),
        _entry(
            "hospitality",
            "Airbnb Listings (Inside Airbnb Amsterdam)",
            _url(
                "https://raw.githubusercontent.com/rfordatascience/tidytuesday/master/data/2020/"
                "2020-02-11/hotels.csv"
            ),
        ),
        _entry(
            "hospitality",
            "World tourism / GDP proxy sample",
            _url("https://raw.githubusercontent.com/datasets/gdp/master/data/gdp.csv"),
        ),
        _entry(
            "hospitality",
            "STR-style occupancy from hotel bookings sample",
            _url(
                "https://raw.githubusercontent.com/rfordatascience/tidytuesday/master/data/2020/"
                "2020-02-11/hotels.csv"
            ),
        ),
        # Crime
        _entry("crime", "Communities and Crime", lambda: _from_uci(183)),
        _entry(
            "crime",
            "Chicago Crimes Dataset (Socrata 50k sample)",
            _url("https://data.cityofchicago.org/resource/ijzp-q8t2.csv?$limit=50000"),
        ),
        _entry(
            "crime",
            "FBI Crime Data Explorer (FiveThirtyEight UCR sample)",
            _url("https://raw.githubusercontent.com/fivethirtyeight/data/master/police-deaths/all_data.csv"),
        ),
        _entry(
            "crime",
            "UK Police Street-Level Crime Data sample",
            _url("https://data.police.uk/api/crimes-street/all-crime?lat=51.5074&lng=-0.1278&date=2024-01"),
        ),
    ]


def populate() -> list[dict[str, Any]]:
    ZOO_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for path in ZOO_DATA_DIR.glob("*/*.parquet"):
        path.unlink()
    cache_dir = ZOO_DATA_DIR / "_missing_values_cache"
    if cache_dir.exists():
        for path in cache_dir.glob("*"):
            if path.is_file():
                path.unlink()

    domain_keys = {key for key, _ in DOMAINS}
    for child in list(ZOO_DATA_DIR.iterdir()):
        if child.is_dir() and child.name not in domain_keys and child.name != "_missing_values_cache":
            for stale in child.glob("*"):
                if stale.is_file():
                    stale.unlink()
            try:
                child.rmdir()
            except OSError:
                pass

    for key, _label in DOMAINS:
        (ZOO_DATA_DIR / key).mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    counters: dict[str, int] = {key: 0 for key, _ in DOMAINS}

    for entry in build_catalog():
        domain = entry["domain"]
        name = entry["name"]
        counters[domain] += 1
        index = counters[domain]
        file_name = f"{index:02d}_{_slug(name)}.parquet"
        out_path = ZOO_DATA_DIR / domain / file_name
        status = "failed"
        rows = cols = 0
        missing_pct: float | None = None
        error = ""
        try:
            df = _cap(entry["fetcher"]())
            if not isinstance(df, pd.DataFrame) or df.empty or df.shape[1] == 0:
                raise ValueError("empty or non-tabular result")
            missing_pct = round(_missing_row_pct(df), 2)
            rows, cols = int(df.shape[0]), int(df.shape[1])
            _sanitize_for_parquet(df).to_parquet(out_path, index=False)
            status = "success"
            print(f"[ok] {domain}/{file_name} ({rows}x{cols}, missing_rows={missing_pct}%)")
        except Exception as exc:  # noqa: BLE001
            error = str(exc)[:240]
            print(f"[fail] {domain} :: {name} :: {error}")
        results.append(
            {
                "domain": domain,
                "name": name,
                "file": file_name if status == "success" else "",
                "status": status,
                "rows": rows,
                "cols": cols,
                "missing_row_pct": missing_pct,
                "error": error,
            }
        )
    return results


def print_table(results: list[dict[str, Any]]) -> None:
    print("\n=== Zoo download summary ===")
    print(f"{'Domain':<28} {'Dataset':<58} {'OK':<8} {'Rows':>8} {'Cols':>6} {'Miss%':>8}")
    print("-" * 126)
    for row in results:
        miss = "" if row["missing_row_pct"] is None else f"{row['missing_row_pct']:.2f}"
        print(
            f"{row['domain']:<28} {row['name'][:58]:<58} {row['status']:<8} "
            f"{row['rows']:>8} {row['cols']:>6} {miss:>8}"
        )
    ok = sum(1 for r in results if r["status"] == "success")
    domains_ok = len({r["domain"] for r in results if r["status"] == "success"})
    print("-" * 126)
    print(f"Succeeded: {ok}/{len(results)}   Domains with data: {domains_ok}/20")


if __name__ == "__main__":
    print_table(populate())
