import os
import sqlite3
import unittest
import uuid
from contextlib import contextmanager

from app import app, init_db


class LinkTrackerTestCase(unittest.TestCase):
    def setUp(self):
        os.makedirs(".test-tmp", exist_ok=True)
        self.db_path = os.path.abspath(
            os.path.join(".test-tmp", f"analytics-test-{uuid.uuid4().hex}.db")
        )
        app.config.update(
            DATABASE=self.db_path,
            DATABASE_URL="",
            DB_BACKEND="sqlite",
            TESTING=True,
            DB_INITIALIZED=False,
            PUBLIC_BASE_URL="https://sho.rt",
        )
        os.environ.pop("ANALYTICS_PASSWORD", None)
        with app.app_context():
            init_db()
            app.config["DB_INITIALIZED"] = True
        self.client = app.test_client()

    def tearDown(self):
        for suffix in ("", "-journal", "-wal", "-shm"):
            try:
                os.remove(f"{self.db_path}{suffix}")
            except FileNotFoundError:
                pass

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def test_normalizes_url_and_creates_short_link(self):
        response = self.client.post(
            "/",
            data={"url": "example.com", "title": "Example"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"https://sho.rt/s/", response.data)

        with self.db() as db:
            link = db.execute("SELECT * FROM short_links").fetchone()
            self.assertEqual(link["destination_url"], "https://example.com")
            self.assertEqual(link["title"], "Example")

    def test_utm_variants_use_one_short_code_with_query_variants(self):
        response = self.client.post(
            "/",
            data={
                "url": "example.com/path",
                "enable_utm_set": "on",
                "utm_campaign": "launch",
                "utm_variants": "qr,offline\nemail,digital",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"https://sho.rt/s/", response.data)
        self.assertIn(b"utm_source=qr", response.data)
        self.assertIn(b"utm_source=email", response.data)

        with self.db() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM short_links").fetchone()[0], 1
            )

    def test_redirect_records_visit_and_applies_utm_params(self):
        self.client.post("/", data={"url": "example.com/path?existing=1"})
        with self.db() as db:
            code = db.execute("SELECT code FROM short_links").fetchone()["code"]

        response = self.client.get(
            f"/s/{code}?utm_source=qr&utm_medium=offline&utm_campaign=launch",
            follow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0 Chrome/120.0"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["Location"],
            "https://example.com/path?existing=1&utm_source=qr&utm_medium=offline&utm_campaign=launch",
        )

        with self.db() as db:
            visit = db.execute("SELECT * FROM visits").fetchone()
            self.assertEqual(visit["utm_source"], "qr")
            self.assertEqual(visit["utm_medium"], "offline")
            self.assertEqual(visit["utm_campaign"], "launch")
            self.assertEqual(visit["browser"], "Chrome")

    def test_analytics_requires_password_and_renders_after_login(self):
        os.environ["ANALYTICS_PASSWORD"] = "secret"

        response = self.client.get("/analytics")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/analytics/login", response.headers["Location"])

        response = self.client.post(
            "/analytics/login",
            data={"password": "secret"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Total Visits", response.data)

    def test_analytics_reports_missing_password(self):
        response = self.client.get("/analytics")

        self.assertEqual(response.status_code, 503)
        self.assertIn(b"ANALYTICS_PASSWORD", response.data)


if __name__ == "__main__":
    unittest.main()
