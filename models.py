from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

db = SQLAlchemy()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────
# USERS
# One row per student who signs up.
# Password is never stored plain — only the bcrypt hash.
# ─────────────────────────────────────────────────────────
class User(db.Model):
    __tablename__ = 'users'

    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    fname         = db.Column(db.String(100), nullable=False)
    lname         = db.Column(db.String(100), nullable=False)
    grade         = db.Column(db.Integer, nullable=False)
    age           = db.Column(db.Integer)
    school        = db.Column(db.String(255))
    city          = db.Column(db.String(100))
    streak        = db.Column(db.Integer, default=0)
    last_date     = db.Column(db.String(20))   # ISO date string e.g. "2025-01-15"
    created_at    = db.Column(db.DateTime, default=utc_now)

    # Relationships — deleting a user cascades to all their data
    csb_sessions    = db.relationship('CSBSession',    backref='user', lazy=True, cascade='all, delete-orphan')
    mc_sessions     = db.relationship('MCSession',     backref='user', lazy=True, cascade='all, delete-orphan')
    csb_best_scores = db.relationship('CSBBestScore',  backref='user', lazy=True, cascade='all, delete-orphan')
    mc_best_scores  = db.relationship('MCBestScore',   backref='user', lazy=True, cascade='all, delete-orphan')
    mc_type_stats   = db.relationship('MCTypeStat',    backref='user', lazy=True, cascade='all, delete-orphan')

    # Adaptive learning relationships
    learning_sessions = db.relationship('LearningSession', backref='user', lazy=True, cascade='all, delete-orphan')
    csb_attempts      = db.relationship('CSBQuestionAttempt', backref='user', lazy=True, cascade='all, delete-orphan')
    mc_attempts       = db.relationship('MCQuestionAttempt', backref='user', lazy=True, cascade='all, delete-orphan')
    csb_retries       = db.relationship('CSBRetryQueue', backref='user', lazy=True, cascade='all, delete-orphan')
    mc_retries        = db.relationship('MCRetryQueue', backref='user', lazy=True, cascade='all, delete-orphan')


# ─────────────────────────────────────────────────────────
# CALCULATION SPEED BOOSTER — SESSIONS (Legacy Summary)
# One new row each time a student checks answers in the CSB workbook.
# ─────────────────────────────────────────────────────────
class CSBSession(db.Model):
    __tablename__ = 'csb_sessions'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    unit       = db.Column(db.Integer, nullable=False)   # 1-5
    score      = db.Column(db.Integer, nullable=False)
    total      = db.Column(db.Integer, nullable=False)   # 20 for units 1-4, 30 for unit 5
    mood       = db.Column(db.String(20), default='–')
    date       = db.Column(db.String(30))                # "15 Jan 2025" — matches dashboard display
    created_at = db.Column(db.DateTime, default=utc_now)


# ─────────────────────────────────────────────────────────
# MISTAKE CORRECTION — SESSIONS (Legacy Summary)
# One new row each time a student submits a unit in the MC workbook.
# ─────────────────────────────────────────────────────────
class MCSession(db.Model):
    __tablename__ = 'mc_sessions'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    unit       = db.Column(db.Integer, nullable=False)   # 1-5
    score      = db.Column(db.Integer, nullable=False)
    total      = db.Column(db.Integer, nullable=False)   # always 15
    mood       = db.Column(db.String(20), default='–')
    date       = db.Column(db.String(30))
    created_at = db.Column(db.DateTime, default=utc_now)


# ─────────────────────────────────────────────────────────
# CSB BEST SCORES
# 5 rows per user (one per unit). Updated in-place when beaten.
# ─────────────────────────────────────────────────────────
class CSBBestScore(db.Model):
    __tablename__ = 'csb_best_scores'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    unit       = db.Column(db.Integer, nullable=False)
    best_score = db.Column(db.Integer, default=0)

    __table_args__ = (db.UniqueConstraint('user_id', 'unit', name='uq_csb_user_unit'),)


# ─────────────────────────────────────────────────────────
# MC BEST SCORES
# Same structure, one row per unit per user for the MC workbook.
# ─────────────────────────────────────────────────────────
class MCBestScore(db.Model):
    __tablename__ = 'mc_best_scores'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    unit       = db.Column(db.Integer, nullable=False)
    best_score = db.Column(db.Integer, default=0)

    __table_args__ = (db.UniqueConstraint('user_id', 'unit', name='uq_mc_user_unit'),)


# ─────────────────────────────────────────────────────────
# MC QUESTION TYPE STATS
# Tracks cumulative accuracy per question type (across all sessions).
# type_key is one of: findMistake, tf, radio, fill
# ─────────────────────────────────────────────────────────
class MCTypeStat(db.Model):
    __tablename__ = 'mc_type_stats'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type_key   = db.Column(db.String(50), nullable=False)
    attempted  = db.Column(db.Integer, default=0)
    correct    = db.Column(db.Integer, default=0)

    __table_args__ = (db.UniqueConstraint('user_id', 'type_key', name='uq_mc_user_type'),)


# ─────────────────────────────────────────────────────────
# ADAPTIVE LEARNING SYSTEM — 6 NEW ADDITIVE TABLES
# ─────────────────────────────────────────────────────────

class LearningSession(db.Model):
    __tablename__ = 'learning_sessions'

    id                 = db.Column(db.Integer, primary_key=True)
    user_id            = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    workbook           = db.Column(db.String(10), nullable=False)       # 'CSB' or 'MC'
    unit               = db.Column(db.Integer, nullable=False)          # 1 to 5
    started_at         = db.Column(db.DateTime, default=utc_now, nullable=False)
    submitted_at       = db.Column(db.DateTime, nullable=True)
    cancelled_at       = db.Column(db.DateTime, nullable=True)
    completed_ist_date = db.Column(db.String(10), nullable=True)        # 'YYYY-MM-DD'
    status             = db.Column(db.String(20), default='active', nullable=False)  # 'active', 'submitted', 'cancelled'
    score              = db.Column(db.Integer, nullable=True)
    total              = db.Column(db.Integer, nullable=False)          # 15, 20, or 30
    legacy_session_id  = db.Column(db.Integer, nullable=True)           # FK to csb_sessions(id) or mc_sessions(id)

    # Relationships
    csb_attempts = db.relationship('CSBQuestionAttempt', backref='learning_session', lazy=True, cascade='all, delete-orphan')
    mc_slots     = db.relationship('MCSessionSlot',      backref='learning_session', lazy=True, cascade='all, delete-orphan')
    mc_attempts  = db.relationship('MCQuestionAttempt',  backref='learning_session', lazy=True, cascade='all, delete-orphan')

    __table_args__ = (
        db.CheckConstraint("workbook IN ('CSB', 'MC')", name='chk_ls_workbook'),
        db.CheckConstraint("unit BETWEEN 1 AND 5", name='chk_ls_unit'),
        db.CheckConstraint("status IN ('active', 'submitted', 'cancelled')", name='chk_ls_status'),
        db.CheckConstraint(
            "(workbook = 'MC' AND total = 15) OR "
            "(workbook = 'CSB' AND unit BETWEEN 1 AND 4 AND total = 20) OR "
            "(workbook = 'CSB' AND unit = 5 AND total = 30)",
            name='chk_ls_workbook_total'
        ),
        db.CheckConstraint("score IS NULL OR (score >= 0 AND score <= total)", name='chk_ls_score_range'),
        db.CheckConstraint(
            "((status = 'active') AND (submitted_at IS NULL) AND (completed_ist_date IS NULL) AND (score IS NULL) AND (cancelled_at IS NULL)) OR "
            "((status = 'cancelled') AND (submitted_at IS NULL) AND (completed_ist_date IS NULL) AND (score IS NULL) AND (cancelled_at IS NOT NULL)) OR "
            "((status = 'submitted') AND (submitted_at IS NOT NULL) AND (completed_ist_date IS NOT NULL) AND (score IS NOT NULL) AND (cancelled_at IS NULL))",
            name='chk_ls_lifecycle_dates'
        ),
        db.Index('ix_ls_user_lookup', 'user_id', 'workbook', 'unit'),
    )


class CSBQuestionAttempt(db.Model):
    __tablename__ = 'csb_question_attempts'

    id                   = db.Column(db.Integer, primary_key=True)
    user_id              = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    learning_session_id  = db.Column(db.Integer, db.ForeignKey('learning_sessions.id', ondelete='CASCADE'), nullable=False)
    csb_session_id       = db.Column(db.Integer, db.ForeignKey('csb_sessions.id'), nullable=True)
    completed_ist_date   = db.Column(db.String(10), nullable=True)
    unit                 = db.Column(db.Integer, nullable=False)
    position             = db.Column(db.Integer, nullable=False)        # 0 to 19 or 0 to 29
    question_fingerprint = db.Column(db.String(200), nullable=False)
    question_text        = db.Column(db.String(500), nullable=False)
    correct_answer       = db.Column(db.String(100), nullable=False)
    operation_tag        = db.Column(db.String(50), nullable=False)
    difficulty_band      = db.Column(db.String(20), nullable=False)
    submitted_answer     = db.Column(db.String(200), nullable=True)
    is_correct           = db.Column(db.Boolean, nullable=True)
    is_retry             = db.Column(db.Boolean, default=False, nullable=False)
    retry_source_id      = db.Column(db.Integer, db.ForeignKey('csb_retry_queue.id'), nullable=True)
    submitted_at         = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint('learning_session_id', 'position', name='uq_csba_session_pos'),
        db.Index('ix_csba_user_op', 'user_id', 'operation_tag'),
        db.Index('ix_csba_user_fp', 'user_id', 'question_fingerprint'),
    )


class MCSessionSlot(db.Model):
    __tablename__ = 'mc_session_slots'

    id                     = db.Column(db.Integer, primary_key=True)
    learning_session_id    = db.Column(db.Integer, db.ForeignKey('learning_sessions.id', ondelete='CASCADE'), nullable=False)
    slot_number            = db.Column(db.Integer, nullable=False)        # 1 to 15
    presented_question_id  = db.Column(db.String(20), nullable=False)
    replacement_for_id     = db.Column(db.String(20), nullable=True)
    retry_source_id        = db.Column(db.Integer, db.ForeignKey('mc_retry_queue.id'), nullable=True)
    question_snapshot_json = db.Column(db.Text, nullable=False)
    content_version        = db.Column(db.String(50), nullable=False)
    assigned_at            = db.Column(db.DateTime, default=utc_now, nullable=False)

    attempts = db.relationship('MCQuestionAttempt', backref='slot', lazy=True, cascade='all, delete-orphan')

    __table_args__ = (
        db.CheckConstraint("slot_number BETWEEN 1 AND 15", name='chk_mcs_slot'),
        db.UniqueConstraint('learning_session_id', 'slot_number', name='uq_mcs_session_slot'),
        db.UniqueConstraint('learning_session_id', 'presented_question_id', name='uq_mcs_session_qid'),
        db.Index('ix_mcs_session', 'learning_session_id'),
    )


class MCQuestionAttempt(db.Model):
    __tablename__ = 'mc_question_attempts'

    id                  = db.Column(db.Integer, primary_key=True)
    user_id             = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    learning_session_id = db.Column(db.Integer, db.ForeignKey('learning_sessions.id', ondelete='CASCADE'), nullable=False)
    slot_id             = db.Column(db.Integer, db.ForeignKey('mc_session_slots.id', ondelete='CASCADE'), nullable=False)
    mc_session_id       = db.Column(db.Integer, db.ForeignKey('mc_sessions.id'), nullable=True)
    submitted_answer    = db.Column(db.String(500), nullable=False)
    is_correct          = db.Column(db.Boolean, nullable=False)
    submitted_at        = db.Column(db.DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('slot_id', name='uq_mca_slot'),
        db.Index('ix_mca_session', 'learning_session_id'),
        db.Index('ix_mca_user', 'user_id'),
    )


class CSBRetryQueue(db.Model):
    __tablename__ = 'csb_retry_queue'

    id                      = db.Column(db.Integer, primary_key=True)
    user_id                 = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    unit                    = db.Column(db.Integer, nullable=False)
    question_fingerprint    = db.Column(db.String(200), nullable=False)
    question_text           = db.Column(db.String(500), nullable=False)
    correct_answer          = db.Column(db.String(100), nullable=False)
    operation_tag           = db.Column(db.String(50), nullable=False)
    difficulty_band         = db.Column(db.String(20), nullable=False)
    incorrect_session_count = db.Column(db.Integer, default=1, nullable=False)
    first_incorrect_date    = db.Column(db.String(10), nullable=False)
    last_incorrect_date     = db.Column(db.String(10), nullable=False)
    status                  = db.Column(db.String(30), default='pending', nullable=False)  # 'pending', 'resolved', 'replaced'
    resolved_at             = db.Column(db.DateTime, nullable=True)
    replaced_by_fingerprint = db.Column(db.String(200), nullable=True)

    __table_args__ = (
        db.Index('ix_csbr_lookup', 'user_id', 'unit', 'status'),
    )


class MCRetryQueue(db.Model):
    __tablename__ = 'mc_retry_queue'

    id                      = db.Column(db.Integer, primary_key=True)
    user_id                 = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    unit                    = db.Column(db.Integer, nullable=False)
    question_id             = db.Column(db.String(20), nullable=False)
    concept_tag             = db.Column(db.String(100), nullable=False)
    difficulty_tier         = db.Column(db.String(20), nullable=False)
    incorrect_session_count = db.Column(db.Integer, default=1, nullable=False)
    first_incorrect_date    = db.Column(db.String(10), nullable=False)
    last_incorrect_date     = db.Column(db.String(10), nullable=False)
    status                  = db.Column(db.String(30), default='pending', nullable=False)  # 'pending', 'resolved', 'replaced', 'unresolved_replacement'
    resolved_at             = db.Column(db.DateTime, nullable=True)
    replaces_question_id    = db.Column(db.String(20), nullable=True)
    replacement_question_id = db.Column(db.String(20), nullable=True)

    __table_args__ = (
        db.Index('ix_mcr_lookup', 'user_id', 'unit', 'status'),
    )
