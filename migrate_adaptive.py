"""
migrate_adaptive.py — Safe Database Migration for Adaptive Learning System (V1)
Applies the 6 additive tables, CHECK constraints, and partial unique indexes.
Guarantees zero modifications to existing tables and existing rows.
"""

import sys
import os
import sqlite3

SCHEMA_SQL = """
-- 1. learning_sessions
CREATE TABLE IF NOT EXISTS learning_sessions (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id            INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    workbook           VARCHAR(10) NOT NULL,      -- 'CSB' or 'MC'
    unit               INTEGER NOT NULL,           -- 1 to 5
    started_at         DATETIME NOT NULL,          -- UTC timestamp
    submitted_at       DATETIME,                   -- UTC timestamp upon completion
    cancelled_at       DATETIME,                   -- UTC timestamp upon cancellation
    completed_ist_date VARCHAR(10),                -- "YYYY-MM-DD" server-enforced IST date
    status             VARCHAR(20) NOT NULL DEFAULT 'active',
                                                   -- 'active' | 'submitted' | 'cancelled'
    score              INTEGER,                    -- Verified unit score
    total              INTEGER NOT NULL,           -- 15, 20, or 30
    legacy_session_id  INTEGER,                    -- FK to csb_sessions(id) or mc_sessions(id)

    CONSTRAINT chk_ls_workbook CHECK (workbook IN ('CSB', 'MC')),
    CONSTRAINT chk_ls_unit CHECK (unit BETWEEN 1 AND 5),
    CONSTRAINT chk_ls_status CHECK (status IN ('active', 'submitted', 'cancelled')),
    CONSTRAINT chk_ls_workbook_total CHECK (
        (workbook = 'MC' AND total = 15) OR
        (workbook = 'CSB' AND unit BETWEEN 1 AND 4 AND total = 20) OR
        (workbook = 'CSB' AND unit = 5 AND total = 30)
    ),
    CONSTRAINT chk_ls_score_range CHECK (
        score IS NULL OR (score >= 0 AND score <= total)
    ),
    CONSTRAINT chk_ls_lifecycle_dates CHECK (
        (status = 'active' AND submitted_at IS NULL AND completed_ist_date IS NULL AND score IS NULL AND cancelled_at IS NULL) OR
        (status = 'cancelled' AND submitted_at IS NULL AND completed_ist_date IS NULL AND score IS NULL AND cancelled_at IS NOT NULL) OR
        (status = 'submitted' AND submitted_at IS NOT NULL AND completed_ist_date IS NOT NULL AND score IS NOT NULL AND cancelled_at IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS ix_ls_user_lookup ON learning_sessions(user_id, workbook, unit);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ls_single_active
    ON learning_sessions(user_id, workbook, unit)
    WHERE status = 'active';

CREATE UNIQUE INDEX IF NOT EXISTS uq_ls_completed_daily
    ON learning_sessions(user_id, workbook, unit, completed_ist_date)
    WHERE status = 'submitted';


-- 2. csb_question_attempts
CREATE TABLE IF NOT EXISTS csb_question_attempts (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id              INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    learning_session_id  INTEGER NOT NULL REFERENCES learning_sessions(id) ON DELETE CASCADE,
    csb_session_id       INTEGER REFERENCES csb_sessions(id),
    completed_ist_date   VARCHAR(10),
    unit                 INTEGER NOT NULL,
    position             INTEGER NOT NULL,       -- 0 to 19 (or 0 to 29 for Unit 5)
    question_fingerprint VARCHAR(200) NOT NULL,  -- Canonical non-commutative string
    question_text        VARCHAR(500) NOT NULL,
    correct_answer       VARCHAR(100) NOT NULL,
    operation_tag        VARCHAR(50) NOT NULL,
    difficulty_band      VARCHAR(20) NOT NULL,
    submitted_answer     VARCHAR(200),
    is_correct           BOOLEAN,
    is_retry             BOOLEAN NOT NULL DEFAULT 0,
    retry_source_id      INTEGER REFERENCES csb_retry_queue(id),
    submitted_at         DATETIME,

    UNIQUE(learning_session_id, position)
);

CREATE INDEX IF NOT EXISTS ix_csba_user_op ON csb_question_attempts(user_id, operation_tag);
CREATE INDEX IF NOT EXISTS ix_csba_user_fp ON csb_question_attempts(user_id, question_fingerprint);


-- 3. mc_session_slots
CREATE TABLE IF NOT EXISTS mc_session_slots (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    learning_session_id    INTEGER NOT NULL REFERENCES learning_sessions(id) ON DELETE CASCADE,
    slot_number            INTEGER NOT NULL,       -- 1 to 15
    presented_question_id  VARCHAR(20) NOT NULL,   -- e.g. "u1q8" or "u1q8_v1"
    replacement_for_id     VARCHAR(20),            -- Original question replaced (or NULL)
    retry_source_id        INTEGER REFERENCES mc_retry_queue(id),
    question_snapshot_json TEXT NOT NULL,         -- Immutable declarative JSON
    content_version        VARCHAR(50) NOT NULL,   -- Registry version identifier
    assigned_at            DATETIME NOT NULL,

    CONSTRAINT chk_mcs_slot CHECK (slot_number BETWEEN 1 AND 15),
    UNIQUE(learning_session_id, slot_number),
    UNIQUE(learning_session_id, presented_question_id)
);

CREATE INDEX IF NOT EXISTS ix_mcs_session ON mc_session_slots(learning_session_id);


-- 4. mc_question_attempts
CREATE TABLE IF NOT EXISTS mc_question_attempts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    learning_session_id INTEGER NOT NULL REFERENCES learning_sessions(id) ON DELETE CASCADE,
    slot_id             INTEGER NOT NULL REFERENCES mc_session_slots(id) ON DELETE CASCADE,
    mc_session_id       INTEGER REFERENCES mc_sessions(id),
    submitted_answer    VARCHAR(500) NOT NULL,
    is_correct          BOOLEAN NOT NULL,
    submitted_at        DATETIME NOT NULL,

    UNIQUE(slot_id)
);

CREATE INDEX IF NOT EXISTS ix_mca_session ON mc_question_attempts(learning_session_id);
CREATE INDEX IF NOT EXISTS ix_mca_user ON mc_question_attempts(user_id);


-- 5. csb_retry_queue
CREATE TABLE IF NOT EXISTS csb_retry_queue (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                 INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    unit                    INTEGER NOT NULL,
    question_fingerprint    VARCHAR(200) NOT NULL,
    question_text           VARCHAR(500) NOT NULL,
    correct_answer          VARCHAR(100) NOT NULL,
    operation_tag           VARCHAR(50) NOT NULL,
    difficulty_band         VARCHAR(20) NOT NULL,
    incorrect_session_count INTEGER NOT NULL DEFAULT 1,
    first_incorrect_date    VARCHAR(10) NOT NULL,
    last_incorrect_date     VARCHAR(10) NOT NULL,
    status                  VARCHAR(30) NOT NULL DEFAULT 'pending',
    resolved_at             DATETIME,
    replaced_by_fingerprint VARCHAR(200)
);

CREATE INDEX IF NOT EXISTS ix_csbr_lookup ON csb_retry_queue(user_id, unit, status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_csbr_active_pending
    ON csb_retry_queue(user_id, unit, question_fingerprint)
    WHERE status = 'pending';


-- 6. mc_retry_queue
CREATE TABLE IF NOT EXISTS mc_retry_queue (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                 INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    unit                    INTEGER NOT NULL,
    question_id             VARCHAR(20) NOT NULL,
    concept_tag             VARCHAR(100) NOT NULL,
    difficulty_tier         VARCHAR(20) NOT NULL,
    incorrect_session_count INTEGER NOT NULL DEFAULT 1,
    first_incorrect_date    VARCHAR(10) NOT NULL,
    last_incorrect_date     VARCHAR(10) NOT NULL,
    status                  VARCHAR(30) NOT NULL DEFAULT 'pending',
    resolved_at             DATETIME,
    replaces_question_id    VARCHAR(20),
    replacement_question_id VARCHAR(20)
);

CREATE INDEX IF NOT EXISTS ix_mcr_lookup ON mc_retry_queue(user_id, unit, status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_mcr_active_pending
    ON mc_retry_queue(user_id, unit, question_id)
    WHERE status = 'pending';
"""


def run_migration(db_path: str = 'instance/speedcalc_dev.db') -> bool:
    if not os.path.exists(db_path):
        print(f"Error: Database {db_path} does not exist.")
        return False

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    existing_tables = ['users', 'csb_sessions', 'mc_sessions', 'csb_best_scores', 'mc_best_scores', 'mc_type_stats']
    baseline_counts = {}
    for t in existing_tables:
        try:
            baseline_counts[t] = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except sqlite3.OperationalError:
            baseline_counts[t] = None

    try:
        cur.executescript(SCHEMA_SQL)
        conn.commit()

        # Verify existing table integrity
        post_counts = {}
        for t in existing_tables:
            try:
                post_counts[t] = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except sqlite3.OperationalError:
                post_counts[t] = None

        assert baseline_counts == post_counts, "CRITICAL: Legacy row count mismatch after migration!"

        # Verify new tables exist
        new_tables = ['learning_sessions', 'csb_question_attempts', 'mc_session_slots', 'mc_question_attempts', 'csb_retry_queue', 'mc_retry_queue']
        for nt in new_tables:
            cur.execute(f"SELECT COUNT(*) FROM {nt}")

        return True
    except Exception as exc:
        conn.rollback()
        print(f"Migration failed: {exc}")
        return False
    finally:
        conn.close()


if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else 'instance/speedcalc_dev.db'
    success = run_migration(target)
    sys.exit(0 if success else 1)
