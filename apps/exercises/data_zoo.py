from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DATA_SCIENCE_SECTORS = [
    "healthcare",
    "finance",
    "retail",
    "marketing",
    "human_resources",
    "education",
    "sports",
    "transportation",
    "real_estate",
    "manufacturing",
    "agriculture",
    "environment",
    "energy",
    "government_demographics",
    "biology",
    "astronomy",
    "ecommerce",
    "insurance",
    "hospitality",
    "crime",
]

ZOO_DATA_DIR = Path(__file__).resolve().parent / "zoo_data"

SECTOR_FIELD_MAP = {
    "healthcare": ["patient_id", "admission_age", "length_of_stay_days", "readmission_risk", "department", "severity_score", "insurance_type", "medication_cost", "discharge_status"],
    "finance": ["account_id", "annual_income", "credit_limit", "loan_amount", "loan_term_months", "risk_score", "late_payments", "customer_tenure", "default_flag"],
    "retail": ["store_id", "basket_size", "unit_price", "discount_pct", "channel", "region", "loyalty_score", "return_flag", "revenue"],
    "marketing": ["customer_id", "age", "segment", "channel", "campaign_spend", "email_clicks", "conversion_rate", "repeat_purchase", "purchase_value"],
    "human_resources": ["employee_id", "age", "tenure_years", "department", "overtime", "monthly_income", "job_satisfaction", "performance_score", "attrition"],
    "education": ["student_id", "attendance_rate", "study_hours", "math_score", "reading_score", "teacher_experience", "school_type", "support_index", "pass_status"],
    "sports": ["player_id", "games_played", "points", "assists", "rebounds", "minutes", "plus_minus", "team", "win_flag"],
    "transportation": ["route_id", "distance_km", "load_tons", "traffic_index", "delivery_time_h", "fuel_cost", "weather_delay", "on_time_rate", "service_quality"],
    "real_estate": ["property_id", "sqft", "bedrooms", "bathrooms", "year_built", "neighborhood", "lot_size", "tax_amount", "sale_price"],
    "manufacturing": ["machine_id", "temperature_c", "vibration_mm", "maintenance_hours", "throughput_units", "defect_rate", "downtime_hours", "operator_experience", "quality_grade"],
    "agriculture": ["farm_id", "soil_ph", "rainfall_mm", "temperature_c", "fertilizer_kg", "irrigation_hours", "yield_tons", "pest_pressure", "harvest_quality"],
    "environment": ["station_id", "air_quality_index", "water_ph", "rainfall_mm", "temperature_c", "soil_moisture", "pollution_level", "species_count", "ecosystem_health"],
    "energy": ["site_id", "generation_mw", "demand_mw", "temperature_c", "maintenance_status", "price_per_mwh", "renewable_share", "outage_hours", "efficiency_score"],
    "government_demographics": ["district_id", "unemployment_rate", "median_income", "crime_rate", "school_attendance", "population_density", "service_access", "policy_support", "outcome_index"],
    "biology": ["sample_id", "species", "body_mass_g", "flipper_length_mm", "bill_length_mm", "sex", "island", "year", "survival_flag"],
    "astronomy": ["object_id", "orbital_period_days", "planet_radius_re", "stellar_teff", "stellar_mass", "discovery_year", "method", "equilibrium_temp", "confirmed"],
    "ecommerce": ["order_id", "items", "payment_value", "freight_value", "review_score", "category", "delivery_days", "weekend_flag", "repeat_customer"],
    "insurance": ["policy_id", "age", "bmi", "children", "smoker", "region", "charges", "claim_flag", "risk_score"],
    "hospitality": ["booking_id", "lead_time", "nights", "adults", "children", "meal", "market_segment", "adr", "is_canceled"],
    "crime": ["incident_id", "district", "hour", "arrest", "domestic", "latitude", "longitude", "primary_type", "severity"],
}

SECTOR_FACTORIES = {
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
    "retail": {
        "store_id": lambda rng: np.arange(1, 10001),
        "basket_size": lambda rng: rng.integers(1, 40, size=10000),
        "unit_price": lambda rng: np.round(rng.uniform(1, 200, size=10000), 2),
        "discount_pct": lambda rng: np.round(rng.uniform(0, 0.4, size=10000), 3),
        "channel": lambda rng: rng.choice(["store", "online", "app"], size=10000),
        "region": lambda rng: rng.choice(["north", "south", "east", "west"], size=10000),
        "loyalty_score": lambda rng: np.round(rng.uniform(0, 1, size=10000), 3),
        "return_flag": lambda rng: rng.choice([0, 1], size=10000, p=[0.9, 0.1]),
        "revenue": lambda rng: np.round(rng.normal(85, 40, size=10000), 2),
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
    "human_resources": {
        "employee_id": lambda rng: np.arange(1, 10001),
        "age": lambda rng: rng.integers(20, 65, size=10000),
        "tenure_years": lambda rng: rng.integers(0, 30, size=10000),
        "department": lambda rng: rng.choice(["sales", "rd", "hr", "ops"], size=10000),
        "overtime": lambda rng: rng.choice(["Yes", "No"], size=10000),
        "monthly_income": lambda rng: np.round(rng.normal(6500, 2500, size=10000), 2),
        "job_satisfaction": lambda rng: rng.integers(1, 5, size=10000),
        "performance_score": lambda rng: np.round(rng.uniform(1, 5, size=10000), 2),
        "attrition": lambda rng: rng.choice([0, 1], size=10000, p=[0.84, 0.16]),
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
    "sports": {
        "player_id": lambda rng: np.arange(1, 10001),
        "games_played": lambda rng: rng.integers(1, 82, size=10000),
        "points": lambda rng: np.round(rng.normal(12, 8, size=10000), 1),
        "assists": lambda rng: np.round(rng.normal(3, 2, size=10000), 1),
        "rebounds": lambda rng: np.round(rng.normal(5, 3, size=10000), 1),
        "minutes": lambda rng: np.round(rng.normal(24, 10, size=10000), 1),
        "plus_minus": lambda rng: np.round(rng.normal(0, 8, size=10000), 1),
        "team": lambda rng: rng.choice(["A", "B", "C", "D"], size=10000),
        "win_flag": lambda rng: rng.choice([0, 1], size=10000),
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
    "real_estate": {
        "property_id": lambda rng: np.arange(1, 10001),
        "sqft": lambda rng: rng.integers(500, 4500, size=10000),
        "bedrooms": lambda rng: rng.integers(1, 6, size=10000),
        "bathrooms": lambda rng: np.round(rng.uniform(1, 4, size=10000), 1),
        "year_built": lambda rng: rng.integers(1900, 2024, size=10000),
        "neighborhood": lambda rng: rng.choice(["north", "south", "east", "west"], size=10000),
        "lot_size": lambda rng: rng.integers(1000, 20000, size=10000),
        "tax_amount": lambda rng: np.round(rng.normal(4500, 1800, size=10000), 2),
        "sale_price": lambda rng: np.round(rng.lognormal(12.2, 0.4, size=10000), 2),
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
    "environment": {
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
    "government_demographics": {
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
    "biology": {
        "sample_id": lambda rng: np.arange(1, 10001),
        "species": lambda rng: rng.choice(["Adelie", "Chinstrap", "Gentoo"], size=10000),
        "body_mass_g": lambda rng: rng.integers(2700, 6300, size=10000),
        "flipper_length_mm": lambda rng: rng.integers(170, 235, size=10000),
        "bill_length_mm": lambda rng: np.round(rng.normal(44, 6, size=10000), 1),
        "sex": lambda rng: rng.choice(["male", "female"], size=10000),
        "island": lambda rng: rng.choice(["Biscoe", "Dream", "Torgersen"], size=10000),
        "year": lambda rng: rng.choice([2007, 2008, 2009], size=10000),
        "survival_flag": lambda rng: rng.choice([0, 1], size=10000, p=[0.2, 0.8]),
    },
    "astronomy": {
        "object_id": lambda rng: np.arange(1, 10001),
        "orbital_period_days": lambda rng: np.round(rng.lognormal(2.5, 1.2, size=10000), 3),
        "planet_radius_re": lambda rng: np.round(rng.lognormal(0.3, 0.6, size=10000), 3),
        "stellar_teff": lambda rng: rng.integers(3000, 7500, size=10000),
        "stellar_mass": lambda rng: np.round(rng.uniform(0.4, 1.8, size=10000), 3),
        "discovery_year": lambda rng: rng.integers(1995, 2025, size=10000),
        "method": lambda rng: rng.choice(["Transit", "Radial Velocity", "Imaging", "Microlensing"], size=10000),
        "equilibrium_temp": lambda rng: rng.integers(200, 2500, size=10000),
        "confirmed": lambda rng: rng.choice([0, 1], size=10000, p=[0.35, 0.65]),
    },
    "ecommerce": {
        "order_id": lambda rng: np.arange(1, 10001),
        "items": lambda rng: rng.integers(1, 12, size=10000),
        "payment_value": lambda rng: np.round(rng.normal(140, 90, size=10000), 2),
        "freight_value": lambda rng: np.round(rng.normal(20, 10, size=10000), 2),
        "review_score": lambda rng: rng.integers(1, 6, size=10000),
        "category": lambda rng: rng.choice(["home", "beauty", "electronics", "sports"], size=10000),
        "delivery_days": lambda rng: rng.integers(1, 30, size=10000),
        "weekend_flag": lambda rng: rng.choice([0, 1], size=10000, p=[0.7, 0.3]),
        "repeat_customer": lambda rng: rng.choice([0, 1], size=10000, p=[0.55, 0.45]),
    },
    "insurance": {
        "policy_id": lambda rng: np.arange(1, 10001),
        "age": lambda rng: rng.integers(18, 65, size=10000),
        "bmi": lambda rng: np.round(rng.normal(30, 6, size=10000), 2),
        "children": lambda rng: rng.integers(0, 5, size=10000),
        "smoker": lambda rng: rng.choice(["yes", "no"], size=10000, p=[0.2, 0.8]),
        "region": lambda rng: rng.choice(["northeast", "northwest", "southeast", "southwest"], size=10000),
        "charges": lambda rng: np.round(rng.lognormal(9, 0.7, size=10000), 2),
        "claim_flag": lambda rng: rng.choice([0, 1], size=10000, p=[0.7, 0.3]),
        "risk_score": lambda rng: rng.integers(0, 100, size=10000),
    },
    "hospitality": {
        "booking_id": lambda rng: np.arange(1, 10001),
        "lead_time": lambda rng: rng.integers(0, 400, size=10000),
        "nights": lambda rng: rng.integers(1, 21, size=10000),
        "adults": lambda rng: rng.integers(1, 5, size=10000),
        "children": lambda rng: rng.integers(0, 4, size=10000),
        "meal": lambda rng: rng.choice(["BB", "HB", "FB", "SC"], size=10000),
        "market_segment": lambda rng: rng.choice(["Online", "Offline", "Corporate", "Groups"], size=10000),
        "adr": lambda rng: np.round(rng.normal(100, 40, size=10000), 2),
        "is_canceled": lambda rng: rng.choice([0, 1], size=10000, p=[0.63, 0.37]),
    },
    "crime": {
        "incident_id": lambda rng: np.arange(1, 10001),
        "district": lambda rng: rng.integers(1, 25, size=10000),
        "hour": lambda rng: rng.integers(0, 24, size=10000),
        "arrest": lambda rng: rng.choice([0, 1], size=10000, p=[0.8, 0.2]),
        "domestic": lambda rng: rng.choice([0, 1], size=10000, p=[0.85, 0.15]),
        "latitude": lambda rng: np.round(rng.uniform(41.6, 42.1, size=10000), 5),
        "longitude": lambda rng: np.round(rng.uniform(-87.9, -87.5, size=10000), 5),
        "primary_type": lambda rng: rng.choice(["THEFT", "BATTERY", "ASSAULT", "BURGLARY"], size=10000),
        "severity": lambda rng: rng.integers(1, 5, size=10000),
    },
}


@lru_cache(maxsize=1)
def ensure_zoo_parquet_catalog() -> dict[str, list[Path]]:
    """Return local parquet files for each domain (populated by scripts/populate_zoo.py)."""
    catalog: dict[str, list[Path]] = {}
    ZOO_DATA_DIR.mkdir(exist_ok=True)
    for sector in DATA_SCIENCE_SECTORS:
        sector_dir = ZOO_DATA_DIR / sector
        sector_dir.mkdir(exist_ok=True)
        local_paths = sorted(sector_dir.glob("*.parquet"))
        catalog[sector] = local_paths
    return catalog


def list_zoo_datasets(sector: str) -> list[Path]:
    sector_name = (sector or "").lower().strip()
    if sector_name not in DATA_SCIENCE_SECTORS:
        raise ValueError(f"Unknown sector '{sector}'. Choose one of: {', '.join(DATA_SCIENCE_SECTORS)}")
    # Bust cache so newly downloaded files appear without process restart.
    ensure_zoo_parquet_catalog.cache_clear()
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


def _sanitize_zoo_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column labels so exercise prompts can quote them safely."""
    out = df.copy()
    renamed = {}
    for column in out.columns:
        label = str(column).strip()
        label = label.replace(" ", "_").replace("-", "_")
        label = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in label)
        while "__" in label:
            label = label.replace("__", "_")
        label = label.strip("_").lower() or "column"
        renamed[column] = label
    out = out.rename(columns=renamed)
    # Deduplicate after normalization.
    seen: dict[str, int] = {}
    final_names: list[str] = []
    for name in out.columns:
        key = str(name)
        count = seen.get(key, 0)
        seen[key] = count + 1
        final_names.append(key if count == 0 else f"{key}_{count + 1}")
    out.columns = final_names
    return out


def sample_zoo_dataframe(
    sector: str,
    *,
    rows: int | None = None,
    seed: int = 42,
    dataset_file: str | None = None,
) -> pd.DataFrame:
    """Return a row-sampled frame from the Data Zoo.

    Prefers a catalog parquet when ``dataset_file`` is given or when the sector
    has local files; otherwise falls back to ``build_zoo_dataset``.
    """
    sector_name = (sector or "").lower().strip()
    if sector_name not in DATA_SCIENCE_SECTORS:
        raise ValueError(f"Unknown sector '{sector}'. Choose one of: {', '.join(DATA_SCIENCE_SECTORS)}")

    rng = np.random.default_rng(seed)
    target_rows = None if rows is None else max(1, int(rows))
    frame: pd.DataFrame | None = None

    catalog = list_zoo_datasets(sector_name)
    chosen_file = (dataset_file or "").strip()
    if chosen_file:
        frame = load_zoo_dataset_file(sector_name, chosen_file)
    elif catalog:
        path = catalog[int(rng.integers(0, len(catalog)))]
        frame = pd.read_parquet(path)

    if frame is None or frame.empty:
        frame = build_zoo_dataset(sector_name, rows=target_rows or 200, seed=seed)
    else:
        frame = _sanitize_zoo_columns(frame)
        # Drop columns that are entirely null — unusable for exercises.
        frame = frame.dropna(axis=1, how="all")
        if frame.empty:
            frame = build_zoo_dataset(sector_name, rows=target_rows or 200, seed=seed)
        elif target_rows is not None:
            if len(frame) >= target_rows:
                frame = frame.sample(n=target_rows, random_state=seed).reset_index(drop=True)
            else:
                # Upsample with replacement so short catalog files still fill the exercise.
                frame = frame.sample(n=target_rows, replace=True, random_state=seed).reset_index(drop=True)

    return frame.reset_index(drop=True)


def list_zoo_sectors() -> list[str]:
    return list(DATA_SCIENCE_SECTORS)


def default_topic_choices() -> list[dict[str, str]]:
    """Standard Data Zoo sector picker options for exercise side panels."""
    return [
        {"label": sector.replace("_", " ").title(), "value": sector}
        for sector in DATA_SCIENCE_SECTORS
    ]


# Per-exercise fallbacks when the learner has not chosen a profile topic.
EXERCISE_DEFAULT_SECTORS: dict[str, str] = {
    "pandas_intro": "insurance",
    "data_transformation": "retail",
    "messy_dataset": "retail",
    "ab_testing": "marketing",
    "descriptive_statistics": "marketing",
    "data_quality": "marketing",
    "missing_values": "healthcare",
}

ZOO_BACKED_SOURCES = frozenset(EXERCISE_DEFAULT_SECTORS)


def default_sector_for_source(source: str | None) -> str:
    return EXERCISE_DEFAULT_SECTORS.get((source or "").strip(), "marketing")


def refresh_scenario_state(
    data_state: dict[str, Any] | None,
    *,
    force_topic: str | None = None,
    change_topic_probability: float = 0.5,
    preferred_topics: list[str] | None = None,
    rng: np.random.Generator | None = None,
) -> dict[str, Any]:
    """Return a fresh scenario: new seed/dataset, optionally a new zoo topic.

    - Always assigns a new ``seed``.
    - Always picks a zoo ``dataset_file`` for the resulting topic when files exist.
    - With ``change_topic_probability`` (default 50%), switches to a different sector
      unless ``force_topic`` is provided. When ``preferred_topics`` has alternatives,
      the switch prefers those ranked preferences over the full catalog.
    """
    state = dict(data_state or {})
    generator = rng or np.random.default_rng()
    current_topic = str(state.get("data_field") or state.get("topic") or "").strip().lower()
    if current_topic not in DATA_SCIENCE_SECTORS:
        current_topic = ""

    ranked = []
    for item in preferred_topics or []:
        topic = str(item or "").strip().lower()
        if topic in DATA_SCIENCE_SECTORS and topic not in ranked:
            ranked.append(topic)

    forced = str(force_topic or "").strip().lower()
    if forced and forced in DATA_SCIENCE_SECTORS:
        new_topic = forced
    elif current_topic and float(generator.random()) < float(change_topic_probability):
        preferred_alts = [topic for topic in ranked if topic != current_topic]
        alternatives = preferred_alts or [
            sector for sector in DATA_SCIENCE_SECTORS if sector != current_topic
        ]
        new_topic = str(generator.choice(alternatives)) if alternatives else current_topic
    else:
        new_topic = current_topic or (ranked[0] if ranked else "marketing")

    state["data_field"] = new_topic
    state["topic"] = new_topic
    state["seed"] = int(generator.integers(1, 1_000_000_000))

    catalog = list_zoo_datasets(new_topic)
    if catalog:
        names = [path.name for path in catalog]
        current_file = str(state.get("dataset_file") or "").strip()
        candidates = [name for name in names if name != current_file] or names
        state["dataset_file"] = str(generator.choice(candidates))
    else:
        state.pop("dataset_file", None)

    for key in ("reference_plot", "dataset_preview_html", "target", "outcome", "numeric_columns"):
        state.pop(key, None)
    return state
