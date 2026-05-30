import os
import sqlite3
import unittest
import uuid
from contextlib import contextmanager

from app import app, init_db, unique_count


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

    def login(self, password="secret"):
        os.environ["ANALYTICS_PASSWORD"] = password
        return self.client.post(
            "/login",
            data={"password": password},
            follow_redirects=True,
        )

    def test_normalizes_url_and_creates_short_link(self):
        self.login()

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

    def test_qr_only_generates_direct_qr_without_short_link(self):
        self.login()

        response = self.client.post(
            "/",
            data={"mode": "qr_only", "url": "example.com/quick"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"QR code created", response.data)
        self.assertIn(b"https://example.com/quick", response.data)
        self.assertIn(b"data:image/png;base64,", response.data)
        self.assertNotIn(b"https://sho.rt/s/", response.data)

        with self.db() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM short_links").fetchone()[0], 0
            )

    def test_utm_variants_use_one_short_code_with_query_variants(self):
        self.login()

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
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM generated_links").fetchone()[0], 2
            )

    def test_redirect_records_visit_and_applies_utm_params(self):
        self.login()
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

    def test_site_requires_password_and_renders_after_login(self):
        os.environ["ANALYTICS_PASSWORD"] = "secret"

        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

        response = self.client.post(
            "/login",
            data={"password": "secret"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Destination URL", response.data)

        response = self.client.get("/analytics")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Total Visits", response.data)

    def test_site_reports_missing_password(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 503)
        self.assertIn(b"ANALYTICS_PASSWORD", response.data)

    def test_short_links_are_public_before_redirecting(self):
        self.login()
        self.client.post("/", data={"url": "example.com"})
        with self.db() as db:
            code = db.execute("SELECT code FROM short_links").fetchone()["code"]

        with self.client.session_transaction() as session:
            session.clear()
        os.environ["ANALYTICS_PASSWORD"] = "secret"

        response = self.client.get(f"/s/{code}", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "https://example.com")

    def test_unique_visitors_count_ip_user_agent_per_day(self):
        self.login()
        self.client.post("/", data={"url": "example.com"})
        with self.db() as db:
            code = db.execute("SELECT code FROM short_links").fetchone()["code"]
            link_id = db.execute("SELECT id FROM short_links").fetchone()["id"]

        for _ in range(2):
            self.client.get(
                f"/s/{code}",
                follow_redirects=False,
                headers={"User-Agent": "Same Browser"},
            )
        self.client.get(
            f"/s/{code}",
            follow_redirects=False,
            headers={"User-Agent": "Different Browser"},
        )

        with app.app_context():
            self.assertEqual(unique_count(short_link_id=link_id), 2)

        with self.db() as db:
            db.execute(
                "UPDATE visits SET visited_at = DATETIME('now', '-1 day') WHERE id = (SELECT MIN(id) FROM visits)"
            )
            db.commit()

        with app.app_context():
            self.assertEqual(unique_count(short_link_id=link_id), 3)

    def test_analytics_renders_unique_metric_views(self):
        self.login()
        self.client.post("/", data={"url": "example.com"})
        with self.db() as db:
            code = db.execute("SELECT code FROM short_links").fetchone()["code"]

        self.client.get(f"/s/{code}", headers={"User-Agent": "Same Browser"})
        self.client.get(f"/s/{code}", headers={"User-Agent": "Same Browser"})

        response = self.client.get("/analytics?metric=uniques")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Unique Visitors", response.data)
        self.assertIn(b"Showing charts and rankings by unique visitors.", response.data)

        response = self.client.get(f"/analytics/link/{code}?metric=uniques")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Daily Unique Visitors", response.data)

    def test_campaign_page_lists_generated_links_even_without_visits(self):
        self.login()
        self.client.post(
            "/",
            data={
                "url": "example.com/path",
                "enable_utm_set": "on",
                "utm_campaign": "launch",
                "utm_variants": "qr,offline\nemail,digital",
            },
        )

        response = self.client.get("/analytics/campaign/launch")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"https://sho.rt/s/", response.data)
        self.assertIn(b"utm_source=qr", response.data)
        self.assertIn(b"utm_source=email", response.data)
        self.assertIn(b"Never", response.data)

    def test_campaign_export_includes_generated_links_and_visits(self):
        self.login()
        self.client.post(
            "/",
            data={
                "url": "example.com/path",
                "enable_utm_set": "on",
                "utm_campaign": "launch",
                "utm_variants": "qr,offline",
            },
        )
        with self.db() as db:
            code = db.execute("SELECT code FROM short_links").fetchone()["code"]
        self.client.get(
            f"/s/{code}?utm_source=qr&utm_medium=offline&utm_campaign=launch",
            headers={"User-Agent": "Export Browser"},
        )

        response = self.client.get("/analytics/campaign/launch/export.csv")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/csv")
        self.assertIn("attachment;", response.headers["Content-Disposition"])
        self.assertIn(b"generated_link", response.data)
        self.assertIn(b"visit", response.data)
        self.assertIn(b"utm_source=qr", response.data)
        self.assertIn(b"Export Browser", response.data)

    def test_campaign_cleanup_deletes_visits_but_keeps_links_active_by_default(self):
        self.login()
        self.client.post(
            "/",
            data={
                "url": "example.com/path",
                "enable_utm_set": "on",
                "utm_campaign": "launch",
                "utm_variants": "qr,offline",
            },
        )
        with self.db() as db:
            code = db.execute("SELECT code FROM short_links").fetchone()["code"]
        self.client.get(
            f"/s/{code}?utm_source=qr&utm_medium=offline&utm_campaign=launch"
        )

        response = self.client.post(
            "/analytics/campaign/launch/cleanup",
            data={
                "confirm_campaign": "launch",
                "export_confirmed": "on",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Cleanup complete", response.data)
        with self.db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM visits").fetchone()[0], 0)
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM generated_links").fetchone()[0], 1
            )
            self.assertEqual(
                db.execute("SELECT is_active FROM short_links").fetchone()[0], 1
            )

    def test_campaign_cleanup_can_delete_generated_links_and_deactivate_shortlinks(self):
        self.login()
        self.client.post(
            "/",
            data={
                "url": "example.com/path",
                "enable_utm_set": "on",
                "utm_campaign": "launch",
                "utm_variants": "qr,offline",
            },
        )

        response = self.client.post(
            "/analytics/campaign/launch/cleanup",
            data={
                "confirm_campaign": "launch",
                "export_confirmed": "on",
                "delete_generated": "on",
                "deactivate_links": "on",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        with self.db() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM generated_links").fetchone()[0], 0
            )
            self.assertEqual(
                db.execute("SELECT is_active FROM short_links").fetchone()[0], 0
            )

    def test_campaign_cleanup_requires_confirmation(self):
        self.login()

        response = self.client.post(
            "/analytics/campaign/launch/cleanup",
            data={"confirm_campaign": "wrong", "export_confirmed": "on"},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Type the exact campaign name", response.data)


if __name__ == "__main__":
    unittest.main()
