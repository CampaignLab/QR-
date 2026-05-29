# QR Link Tracker

Simple Flask tool for creating short links, UTM variants, QR codes, and a password-protected analytics dashboard.

## Features

- Create one short URL for a destination link
- Generate UTM variants on that short URL
- Generate QR codes that point to tracked short URLs
- Record every short-link visit before redirecting
- View dashboard totals, UTM breakdowns, daily visits, top links, and recent visits

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run Locally

```bash
$env:ANALYTICS_PASSWORD = "change-me"
$env:PUBLIC_BASE_URL = "http://127.0.0.1:5000"
python app.py
```

Then open `http://127.0.0.1:5000`.

## Configuration

- `ANALYTICS_PASSWORD`: required to view `/analytics`
- `SECRET_KEY`: recommended for stable login sessions
- `DATABASE_URL`: Neon/Postgres connection string for production
- `DB_BACKEND`: optional, defaults to `postgres` when `DATABASE_URL` is set and `sqlite` otherwise
- `DATABASE_PATH`: optional local SQLite path, defaults to `link_tracker.db`
- `PUBLIC_BASE_URL`: optional public origin for generated short URLs, such as `https://your-domain.com`

## Tests

```bash
python -m unittest discover -s tests
```

## Deployment Notes

The included `api/index.py` and `vercel.json` provide a Vercel Python entrypoint for the Flask app.

Use local SQLite for development and Neon Postgres for Vercel production. In Vercel, set:

- `DATABASE_URL`: the Neon pooled connection string
- `SECRET_KEY`: a long random value
- `ANALYTICS_PASSWORD`: the dashboard password
- `PUBLIC_BASE_URL`: the deployed site URL, for example `https://links.example.com`

The app creates the required tables on cold start if they do not exist. The production Postgres schema is also available in `schema.sql` if you prefer to run it manually in Neon first.
