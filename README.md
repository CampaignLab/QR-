# QR Link Tracker

Simple Flask tool for creating short links, UTM variants, QR codes, and a password-protected analytics dashboard.

## Features

- Create one short URL for a destination link
- Generate a quick direct QR code without creating a short link
- Generate UTM variants on that short URL
- Generate QR codes that point to tracked short URLs
- Record every short-link visit before redirecting
- View visit and unique visitor totals, UTM breakdowns, daily trends, top links, and recent visits
- Recover generated campaign links from the campaign analytics page
- Export finished campaigns to CSV and clean up old campaign data

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

- `ANALYTICS_PASSWORD`: required for the creator and analytics pages; short links stay public
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
- `ANALYTICS_PASSWORD`: the shared password for creator and analytics pages
- `PUBLIC_BASE_URL`: the deployed site URL, for example `https://links.example.com`

The app creates the required tables on cold start if they do not exist. The production Postgres schema is also available in `schema.sql` if you prefer to run it manually in Neon first.

## Data Cleanup Direction

For finished campaigns, export the campaign CSV from its analytics page before cleanup. Cleanup deletes campaign `visits`, can optionally delete saved `generated_links`, and can optionally deactivate campaign short links. Short links stay active by default so old QR codes do not break.
