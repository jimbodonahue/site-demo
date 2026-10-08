Jim's Data Gym (lite)
=====================

Size-capped mirror of `../django-site` for hosts with ~512MB disk (e.g. PythonAnywhere free).

## What differs from the full site

- **Requirements omit** `scikit-learn`, `xgboost`, `seaborn`, and `pyarrow` (those pull scipy / NVIDIA wheels and blow past 500MB with `.venv`).
- **ML track** is present but marked placeholder (`0025_lite_disable_ml_track`).
- **Zoo data** keeps smaller sectors only; heavy topics (energy, ecommerce, sports, …) are empty. Tables are stored as `.csv.gz` instead of parquet so pyarrow is not required.
- **Deploy helpers** live in `deploy/` (PythonAnywhere WSGI + notes).

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit DJANGO_SECRET_KEY etc.
python manage.py migrate
python manage.py runserver
```

See `deploy/PYTHONANYWHERE.md` for hosting steps.
