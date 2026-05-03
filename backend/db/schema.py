import sqlite3
import os
import logging

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "../../db/jobs.db"))


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id     TEXT NOT NULL,
                source          TEXT NOT NULL,
                title           TEXT NOT NULL,
                company         TEXT NOT NULL,
                location        TEXT,
                remote_type     TEXT,
                url             TEXT NOT NULL,
                description_raw TEXT,
                salary_min      INTEGER,
                salary_max      INTEGER,
                date_posted     TEXT,
                date_scraped    TEXT NOT NULL DEFAULT (datetime('now')),
                score           REAL,
                score_breakdown TEXT,
                UNIQUE(source, external_id)
            );

            CREATE TABLE IF NOT EXISTS applications (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id           INTEGER NOT NULL REFERENCES jobs(id),
                status           TEXT NOT NULL DEFAULT 'interested',
                date_interested  TEXT DEFAULT (datetime('now')),
                date_applied     TEXT,
                date_last_action TEXT,
                cover_letter     TEXT,
                resume_variant   TEXT,
                notes            TEXT,
                contact_name     TEXT,
                contact_email    TEXT,
                follow_up_date   TEXT
            );

            CREATE TABLE IF NOT EXISTS preferences (
                id                   INTEGER PRIMARY KEY CHECK (id = 1),
                target_titles        TEXT NOT NULL DEFAULT '["Backend Engineer","Software Engineer"]',
                target_locations     TEXT NOT NULL DEFAULT '["Remote"]',
                remote_ok            INTEGER DEFAULT 1,
                hybrid_ok            INTEGER DEFAULT 1,
                onsite_ok            INTEGER DEFAULT 0,
                min_salary           INTEGER,
                max_experience_years INTEGER DEFAULT 3,
                blocked_companies    TEXT DEFAULT '[]',
                required_keywords    TEXT DEFAULT '[]',
                negative_keywords    TEXT DEFAULT '[]',
                skill_sets           TEXT DEFAULT '{"must_have":[],"strong":[],"nice":[]}',
                last_updated         TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS scrape_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                source     TEXT NOT NULL,
                run_at     TEXT NOT NULL DEFAULT (datetime('now')),
                jobs_found INTEGER DEFAULT 0,
                jobs_new   INTEGER DEFAULT 0,
                status     TEXT,
                error_msg  TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score DESC);
            CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
            CREATE INDEX IF NOT EXISTS idx_jobs_date_scraped ON jobs(date_scraped DESC);
            CREATE INDEX IF NOT EXISTS idx_applications_job_id ON applications(job_id);
            CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
        """)

        # Idempotent column migrations for existing DBs
        for migration in [
            "ALTER TABLE jobs ADD COLUMN needs_review INTEGER DEFAULT 0",
            "ALTER TABLE jobs ADD COLUMN review_reasons TEXT DEFAULT '[]'",
        ]:
            try:
                conn.execute(migration)
            except sqlite3.OperationalError:
                pass  # column already exists

        try:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_needs_review ON jobs(needs_review)"
            )
        except sqlite3.OperationalError:
            pass

    conn.close()
    print(f"Database initialized at {DB_PATH}")


if __name__ == "__main__":
    init_db()
