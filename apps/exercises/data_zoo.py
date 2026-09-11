from __future__ import annotations

import io
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

DATA_SCIENCE_SECTORS = [
    "biostatistics",
    "econometrics",
    "agriculture",
    "finance",
    "marketing",
    "healthcare",
    "manufacturing",
    "energy",
    "public_policy",
    "education",
    "environmental_science",
    "transportation",
]

ZOO_DATA_DIR = Path(__file__).resolve().parent / "zoo_data"
SECTOR_FIELD_MAP = {
    "biostatistics": ["patient_id", "age", "sex", "BMI", "smoking_status", "blood_pressure", "cholesterol", "exercise_hours", "outcome"],
    "econometrics": ["household_id", "income", "education_years", "employment_status", "region", "housing_cost", "savings_rate", "credit_score", "purchase_decision"],
    "agriculture": ["farm_id", "soil_ph", "rainfall_mm", "temperature_c", "fertilizer_kg", "irrigation_hours", "yield_tons", "pest_pressure", "harvest_quality"],
    "finance": ["account_id", "annual_income", "credit_limit", "loan_amount", "loan_term_months", "risk_score", "late_payments", "customer_tenure", "default_flag"],
    "marketing": ["customer_id", "age", "segment", "channel", "campaign_spend", "email_clicks", "conversion_rate", "repeat_purchase", "purchase_value"],
    "healthcare": ["patient_id", "admission_age", "length_of_stay_days", "readmission_risk", "department", "severity_score", "insurance_type", "medication_cost", "discharge_status"],
    "manufacturing": ["machine_id", "temperature_c", "vibration_mm", "maintenance_hours", "throughput_units", "defect_rate", "downtime_hours", "operator_experience", "quality_grade"],
    "energy": ["site_id", "generation_mw", "demand_mw", "temperature_c", "maintenance_status", "price_per_mwh", "renewable_share", "outage_hours", "efficiency_score"],
    "public_policy": ["district_id", "unemployment_rate", "median_income", "crime_rate", "school_attendance", "population_density", "service_access", "policy_support", "outcome_index"],
    "education": ["student_id", "attendance_rate", "study_hours", "math_score", "reading_score", "teacher_experience", "school_type", "support_index", "pass_status"],
    "environmental_science": ["station_id", "air_quality_index", "water_ph", "rainfall_mm", "temperature_c", "soil_moisture", "pollution_level", "species_count", "ecosystem_health"],
    "transportation": ["route_id", "distance_km", "load_tons", "traffic_index", "delivery_time_h", "fuel_cost", "weather_delay", "on_time_rate", "service_quality"],
}

SECTOR_FACTORIES = {
    "biostatistics": {
        "patient_id": lambda rng: np.arange(1, 10001),
        "age": lambda rng: rng.integers(18, 80, size=10000),
        "sex": lambda rng: rng.choice(["female", "male"], size=10000),
        "BMI": lambda rng: np.round(rng.normal(27, 5, size=10000), 2),
        "smoking_status": lambda rng: rng.choice(["never", "former", "current"], size=10000),
        "blood_pressure": lambda rng: rng.integers(90, 180, size=10000),
        "cholesterol": lambda rng: rng.integers(120, 260, size=10000),
        "exercise_hours": lambda rng: rng.integers(0, 12, size=10000),
        "outcome": lambda rng: rng.choice(["recovered", "monitoring", "critical"], size=10000, p=[0.6, 0.3, 0.1]),
    },
    "econometrics": {
        "household_id": lambda rng: np.arange(1, 10001),
        "income": lambda rng: np.round(rng.lognormal(mean=11.2, sigma=0.7, size=10000), 2),
        "education_years": lambda rng: rng.integers(8, 20, size=10000),
        "employment_status": lambda rng: rng.choice(["employed", "self-employed", "unemployed"], size=10000),
        "region": lambda rng: rng.choice(["north", "south", "east", "west"], size=10000),
        "housing_cost": lambda rng: np.round(rng.normal(900, 250, size=10000), 2),
        "savings_rate": lambda rng: np.round(rng.uniform(0, 0.4, size=10000), 3),
        "credit_score": lambda rng: rng.integers(400, 850, size=10000),
        "purchase_decision": lambda rng: rng.choice([0, 1], size=10000, p=[0.52, 0.48]),
    },
    "agriculture": {
        "farm_id": lambda rng: np.arange(1, 10001),
        "soil_ph": lambda rng: np.round(rng.uniform(5.0, 8.5, size=10000), 2),
        "rainfall_mm": lambda rng: np.round(rng.normal(650, 180, size=10000), 1),
        "temperature_c": lambda rng: np.round(rng.normal(23, 7, size=10000), 2),
        "fertilizer_kg": lambda rng: np.round(rng.normal(190, 40, size=10000), 2),
        "irrigation_hours": lambda rng: rng.integers(1, 30, size=10000),
        "yield_tons": lambda rng: np.round(rng.normal(12, 4, size=10000), 2),
        "pest_pressure": lambda rng: rng.integers(0, 100, size=10000),
        "harvest_quality": lambda rng: rng.choice(["low", "medium", "high"], size=10000),
    },
    "finance": {
        "account_id": lambda rng: np.arange(1, 10001),
        "annual_income": lambda rng: np.round(rng.lognormal(mean=11.6, sigma=0.9, size=10000), 2),
        "credit_limit": lambda rng: np.round(rng.normal(18000, 7000, size=10000), 2),
        "loan_amount": lambda rng: np.round(rng.normal(3500, 2500, size=10000), 2),
        "loan_term_months": lambda rng: rng.choice([12, 24, 36, 48, 60], size=10000),
        "risk_score": lambda rng: rng.integers(0, 100, size=10000),
        "late_payments": lambda rng: rng.integers(0, 8, size=10000),
        "customer_tenure": lambda rng: rng.integers(1, 25, size=10000),
        "default_flag": lambda rng: rng.choice([0, 1], size=10000, p=[0.82, 0.18]),
    },
    "marketing": {
        "customer_id": lambda rng: np.arange(1, 10001),
        "age": lambda rng: rng.integers(18, 70, size=10000),
        "segment": lambda rng: rng.choice(["new", "loyal", "at_risk", "vip"], size=10000),
        "channel": lambda rng: rng.choice(["email", "social", "search", "display"], size=10000),
        "campaign_spend": lambda rng: np.round(rng.normal(450, 250, size=10000), 2),
        "email_clicks": lambda rng: rng.integers(0, 250, size=10000),
        "conversion_rate": lambda rng: np.round(rng.uniform(0.01, 0.35, size=10000), 3),
        "repeat_purchase": lambda rng: rng.choice([0, 1], size=10000, p=[0.72, 0.28]),
        "purchase_value": lambda rng: np.round(rng.normal(120, 80, size=10000), 2),
    },
    "healthcare": {
        "patient_id": lambda rng: np.arange(1, 10001),
        "admission_age": lambda rng: rng.integers(18, 90, size=10000),
        "length_of_stay_days": lambda rng: rng.integers(1, 30, size=10000),
        "readmission_risk": lambda rng: np.round(rng.uniform(0.0, 1.0, size=10000), 3),
        "department": lambda rng: rng.choice(["cardiology", "oncology", "orthopedics", "general"], size=10000),
        "severity_score": lambda rng: rng.integers(1, 10, size=10000),
        "insurance_type": lambda rng: rng.choice(["private", "public", "self_pay"], size=10000),
        "medication_cost": lambda rng: np.round(rng.normal(145, 90, size=10000), 2),
        "discharge_status": lambda rng: rng.choice(["home", "rehab", "transfer"], size=10000),
    },
    "manufacturing": {
        "machine_id": lambda rng: np.arange(1, 10001),
        "temperature_c": lambda rng: np.round(rng.normal(72, 18, size=10000), 2),
        "vibration_mm": lambda rng: np.round(rng.normal(2.8, 1.2, size=10000), 2),
        "maintenance_hours": lambda rng: rng.integers(2, 90, size=10000),
        "throughput_units": lambda rng: rng.integers(200, 2500, size=10000),
        "defect_rate": lambda rng: np.round(rng.uniform(0.0, 0.15, size=10000), 3),
        "downtime_hours": lambda rng: np.round(rng.normal(10, 6, size=10000), 2),
        "operator_experience": lambda rng: rng.integers(1, 15, size=10000),
        "quality_grade": lambda rng: rng.choice(["A", "B", "C"], size=10000),
    },
    "energy": {
        "site_id": lambda rng: np.arange(1, 10001),
        "generation_mw": lambda rng: np.round(rng.normal(420, 95, size=10000), 2),
        "demand_mw": lambda rng: np.round(rng.normal(390, 80, size=10000), 2),
        "temperature_c": lambda rng: np.round(rng.normal(22, 12, size=10000), 2),
        "maintenance_status": lambda rng: rng.choice(["normal", "scheduled", "urgent"], size=10000),
        "price_per_mwh": lambda rng: np.round(rng.normal(78, 20, size=10000), 2),
        "renewable_share": lambda rng: np.round(rng.uniform(0.15, 0.95, size=10000), 3),
        "outage_hours": lambda rng: rng.integers(0, 48, size=10000),
        "efficiency_score": lambda rng: np.round(rng.uniform(0.65, 0.99, size=10000), 3),
    },
    "public_policy": {
        "district_id": lambda rng: np.arange(1, 10001),
        "unemployment_rate": lambda rng: np.round(rng.uniform(0.02, 0.18, size=10000), 3),
        "median_income": lambda rng: np.round(rng.normal(44000, 15000, size=10000), 2),
        "crime_rate": lambda rng: np.round(rng.uniform(1, 250, size=10000), 2),
        "school_attendance": lambda rng: np.round(rng.uniform(0.7, 0.99, size=10000), 3),
        "population_density": lambda rng: np.round(rng.uniform(150, 12000, size=10000), 1),
        "service_access": lambda rng: rng.choice(["low", "medium", "high"], size=10000),
        "policy_support": lambda rng: np.round(rng.uniform(0.1, 0.95, size=10000), 3),
        "outcome_index": lambda rng: np.round(rng.normal(60, 20, size=10000), 2),
    },
    "education": {
        "student_id": lambda rng: np.arange(1, 10001),
        "attendance_rate": lambda rng: np.round(rng.uniform(0.5, 1.0, size=10000), 3),
        "study_hours": lambda rng: np.round(rng.uniform(0.5, 10, size=10000), 2),
        "math_score": lambda rng: rng.integers(40, 100, size=10000),
        "reading_score": lambda rng: rng.integers(45, 100, size=10000),
        "teacher_experience": lambda rng: rng.integers(1, 30, size=10000),
        "school_type": lambda rng: rng.choice(["public", "private", "charter"], size=10000),
        "support_index": lambda rng: np.round(rng.uniform(0.0, 1.0, size=10000), 3),
        "pass_status": lambda rng: rng.choice(["pass", "needs_support"], size=10000),
    },
    "environmental_science": {
        "station_id": lambda rng: np.arange(1, 10001),
        "air_quality_index": lambda rng: rng.integers(20, 220, size=10000),
        "water_ph": lambda rng: np.round(rng.uniform(6.0, 9.5, size=10000), 2),
        "rainfall_mm": lambda rng: np.round(rng.normal(900, 250, size=10000), 1),
        "temperature_c": lambda rng: np.round(rng.normal(18, 10, size=10000), 2),
        "soil_moisture": lambda rng: np.round(rng.uniform(10, 90, size=10000), 2),
        "pollution_level": lambda rng: rng.choice(["low", "medium", "high"], size=10000),
        "species_count": lambda rng: rng.integers(20, 200, size=10000),
        "ecosystem_health": lambda rng: rng.choice(["stable", "degraded", "recovering"], size=10000),
    },
    "transportation": {
        "route_id": lambda rng: np.arange(1, 10001),
        "distance_km": lambda rng: np.round(rng.normal(125, 55, size=10000), 2),
        "load_tons": lambda rng: np.round(rng.normal(18, 9, size=10000), 2),
        "traffic_index": lambda rng: rng.integers(1, 100, size=10000),
        "delivery_time_h": lambda rng: np.round(rng.normal(4.5, 2.2, size=10000), 2),
        "fuel_cost": lambda rng: np.round(rng.normal(180, 80, size=10000), 2),
        "weather_delay": lambda rng: rng.choice([0, 1], size=10000, p=[0.85, 0.15]),
        "on_time_rate": lambda rng: np.round(rng.uniform(0.6, 1.0, size=10000), 3),
        "service_quality": lambda rng: rng.choice(["poor", "fair", "good", "excellent"], size=10000),
    },
}

SECTOR_DATASET_URLS: dict[str, list[str]] = {
    "biostatistics": [
        "https://raw.githubusercontent.com/plotly/datasets/master/diabetes.csv",
        "https://raw.githubusercontent.com/plotly/datasets/master/iris.csv",
        "https://raw.githubusercontent.com/plotly/datasets/master/tips.csv",
    ],
    "econometrics": [
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/income.json",
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/population.json",
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/stocks.csv",
    ],
    "agriculture": [
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/weather.csv",
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/cars.json",
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/airports.csv",
    ],
    "finance": [
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/stocks.csv",
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/sp500.csv",
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/budgets.json",
    ],
    "marketing": [
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/cars.json",
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/movies.json",
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/budgets.json",
    ],
    "healthcare": [
        "https://raw.githubusercontent.com/plotly/datasets/master/diabetes.csv",
        "https://raw.githubusercontent.com/plotly/datasets/master/iris.csv",
        "https://raw.githubusercontent.com/plotly/datasets/master/tips.csv",
    ],
    "manufacturing": [
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/cars.json",
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/flights-2k.json",
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/weather.csv",
    ],
    "energy": [
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/stocks.csv",
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/sp500.csv",
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/weather.csv",
    ],
    "public_policy": [
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/population.json",
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/unemployment-across-industries.json",
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/income.json",
    ],
    "education": [
        "https://raw.githubusercontent.com/plotly/datasets/master/gapminderDataFiveYear.csv",
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/population.json",
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/flights-2k.json",
    ],
    "environmental_science": [
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/weather.csv",
        "https://raw.githubusercontent.com/plotly/datasets/master/volcano.csv",
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/population.json",
    ],
    "transportation": [
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/flights-2k.json",
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/airports.csv",
        "https://raw.githubusercontent.com/vega/vega-datasets/master/data/cars.json",
    ],
}


def _read_remote_dataset(url: str) -> pd.DataFrame:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=30) as response:
        payload = response.read()
    lower_url = url.lower()
    if lower_url.endswith(".csv"):
        return pd.read_csv(io.BytesIO(payload))
    if lower_url.endswith(".json"):
        data = pd.read_json(io.BytesIO(payload))
        if not isinstance(data, pd.DataFrame):
            return pd.DataFrame(data)
        return data
    raise ValueError(f"Unsupported remote dataset format for URL: {url}")


def _sanitize_for_parquet(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()
    for column in cleaned.columns:
        if cleaned[column].dtype == object:
            cleaned[column] = cleaned[column].map(lambda value: "" if pd.isna(value) else str(value))
    return cleaned


def _download_parquet_dataset(url: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = _sanitize_for_parquet(_read_remote_dataset(url))
    df.to_parquet(output_path, index=False)
    return output_path


@lru_cache(maxsize=1)
def ensure_zoo_parquet_catalog() -> dict[str, list[Path]]:
    catalog: dict[str, list[Path]] = {}
    ZOO_DATA_DIR.mkdir(exist_ok=True)
    for sector in DATA_SCIENCE_SECTORS:
        sources = SECTOR_DATASET_URLS.get(sector, [])
        sector_dir = ZOO_DATA_DIR / sector
        sector_dir.mkdir(exist_ok=True)
        local_paths: list[Path] = []
        for index, url in enumerate(sources, start=1):
            file_name = f"{index:02d}_{Path(urlparse(url).path).name.rsplit('.', 1)[0]}.parquet"
            output_path = sector_dir / file_name
            if not output_path.exists():
                _download_parquet_dataset(url, output_path)
            local_paths.append(output_path)
        catalog[sector] = local_paths
    return catalog


def list_zoo_datasets(sector: str) -> list[Path]:
    sector_name = (sector or "").lower().strip()
    if sector_name not in DATA_SCIENCE_SECTORS:
        raise ValueError(f"Unknown sector '{sector}'. Choose one of: {', '.join(DATA_SCIENCE_SECTORS)}")
    catalog = ensure_zoo_parquet_catalog()
    return list(catalog.get(sector_name, []))


def load_zoo_dataset_file(sector: str, dataset_file: str) -> pd.DataFrame:
    """Load a parquet file previously selected from the zoo catalog for ``sector``."""
    sector_name = (sector or "").lower().strip()
    file_name = (dataset_file or "").strip()
    if not file_name:
        raise ValueError("dataset_file is required.")

    for path in list_zoo_datasets(sector_name):
        if path.name == file_name:
            return pd.read_parquet(path)

    raise ValueError(
        f"Unknown dataset file '{file_name}' for sector '{sector_name}'. "
        f"Available: {', '.join(path.name for path in list_zoo_datasets(sector_name))}"
    )


def build_zoo_dataset(sector: str, rows: int = 1000, seed: int = 42) -> pd.DataFrame:
    sector_name = (sector or "").lower().strip()
    if sector_name not in DATA_SCIENCE_SECTORS:
        raise ValueError(f"Unknown sector '{sector}'. Choose one of: {', '.join(DATA_SCIENCE_SECTORS)}")

    rng = np.random.default_rng(seed)
    columns = SECTOR_FIELD_MAP[sector_name]
    data: dict[str, Any] = {}

    for column in columns:
        factory = SECTOR_FACTORIES[sector_name][column]
        values = factory(rng)
        if isinstance(values, np.ndarray):
            if values.size != rows:
                values = rng.choice(values, size=rows, replace=True)
        else:
            values = np.array([values] * rows)
        data[column] = values[:rows]

    return pd.DataFrame(data).head(rows)


def list_zoo_sectors() -> list[str]:
    return list(DATA_SCIENCE_SECTORS)
