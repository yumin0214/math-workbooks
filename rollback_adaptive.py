"""
rollback_adaptive.py — Safe Rollback for Adaptive Learning System (V1)
Drops the 6 new tables in strict reverse-dependency order.
Confirms zero impact on the 6 legacy tables.
"""

import sys
import os
import sqlite3

ROLLBACK_SQL = """
DROP TABLE IF EXISTS mc_question_attempts;
DROP TABLE IF EXISTS mc_session_slots;
DROP TABLE IF EXISTS mc_retry_queue;
DROP TABLE IF EXISTS csb_question_attempts;
DROP TABLE IF EXISTS csb_retry_queue;
DROP TABLE IF EXISTS learning_sessions;
"""


def run_rollback(db_path: str = 'instance/speedcalc_dev.db') -> bool:
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
        cur.executescript(ROLLBACK_SQL)
        conn.commit()

        # Verify existing table integrity
        post_counts = {}
        for t in existing_tables:
            try:
                post_counts[t] = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except sqlite3.OperationalError:
                post_counts[t] = None

        assert baseline_counts == post_counts, "CRITICAL: Legacy row count mismatch after rollback!"
        return True
    except Exception as exc:
        conn.rollback()
        print(f"Rollback failed: {exc}")
        return False
    finally:
        conn.close()


if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else 'instance/speedcalc_dev.db'
    success = run_rollback(target)
    sys.exit(0 if success else 1)
