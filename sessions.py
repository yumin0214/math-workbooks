from flask import Blueprint, request, jsonify, g
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo
import logging

from auth_guard import require_auth
from models import db, CSBSession, MCSession, CSBBestScore, MCBestScore, MCTypeStat
from user import build_user_response

logger = logging.getLogger(__name__)
sessions_bp = Blueprint('sessions', __name__)

ALLOWED_MC_TYPES = {'findMistake', 'tf', 'radio', 'fill'}

try:
    IST = ZoneInfo("Asia/Kolkata")
except Exception:
    IST = timezone(timedelta(hours=5, minutes=30))


def get_ist_now() -> datetime:
    return datetime.now(IST)


# ─────────────────────────────────────────────────────────
# HELPER — parse strict integers (rejecting booleans/floats)
# ─────────────────────────────────────────────────────────
def parse_strict_int(val, name: str) -> int:
    if isinstance(val, bool) or val is None:
        raise ValueError(f"{name} must be an integer.")
    if isinstance(val, int):
        return val
    if isinstance(val, str) and val.strip().lstrip('-').isdigit():
        return int(val.strip())
    raise ValueError(f"{name} must be an integer.")


# ─────────────────────────────────────────────────────────
# HELPER — format today's date for display in the dashboard
# Output: "15 Jan 2025"  (matches JS toLocaleDateString en-IN format in IST)
# ─────────────────────────────────────────────────────────
def format_display_date() -> str:
    d = get_ist_now()
    return f"{d.day} {d.strftime('%b %Y')}"


# ─────────────────────────────────────────────────────────
# HELPER — update the student's daily streak (IST day boundaries)
#
# Rules:
#   - If they already practised today → do nothing
#   - If they practised yesterday → increment streak
#   - If they haven't practised in 2+ days → reset streak to 1
# ─────────────────────────────────────────────────────────
def update_streak(user) -> None:
    today_dt  = get_ist_now().date()
    today     = today_dt.isoformat()
    yesterday = (today_dt - timedelta(days=1)).isoformat()

    if user.last_date == today:
        return  # already practised today, nothing to do

    if user.last_date == yesterday:
        user.streak = (user.streak or 0) + 1
    else:
        user.streak = 1   # streak broken or first session ever

    user.last_date = today


# ─────────────────────────────────────────────────────────
# HELPER — update a best score row, or create it if missing
# ─────────────────────────────────────────────────────────
def upsert_csb_best(user_id: int, unit: int, score: int) -> None:
    row = CSBBestScore.query.filter_by(user_id=user_id, unit=unit).first()
    if row:
        if score > row.best_score:
            row.best_score = score
    else:
        db.session.add(CSBBestScore(user_id=user_id, unit=unit, best_score=score))


def upsert_mc_best(user_id: int, unit: int, score: int) -> None:
    row = MCBestScore.query.filter_by(user_id=user_id, unit=unit).first()
    if row:
        if score > row.best_score:
            row.best_score = score
    else:
        db.session.add(MCBestScore(user_id=user_id, unit=unit, best_score=score))


# ─────────────────────────────────────────────────────────
# POST /api/sessions/csb
# Called after the student clicks "Check My Answers" in the CSB workbook.
# ─────────────────────────────────────────────────────────
@sessions_bp.route('/csb', methods=['POST'])
@require_auth
def save_csb_session():
    """
    Save a Calculation Speed Booster session.

    Expects JSON body:
        { unit: 1-5, score: int, total: int, mood: str (optional) }

    Returns the updated full user object so the frontend can
    refresh the dashboard without an extra GET /api/user call.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Invalid request body.'}), 400

    user = g.user

    # 1. Type and value validation
    try:
        unit  = parse_strict_int(data.get('unit'), 'Unit')
        score = parse_strict_int(data.get('score'), 'Score')
        total = parse_strict_int(data.get('total'), 'Total')
    except ValueError as err:
        return jsonify({'error': str(err)}), 400

    # 2. Domain boundary checks
    if unit not in range(1, 6):
        return jsonify({'error': 'Unit must be between 1 and 5.'}), 400

    expected_total = 30 if unit == 5 else 20
    if total != expected_total:
        return jsonify({'error': f'Total questions for Unit {unit} must be {expected_total}.'}), 400

    if score < 0 or score > total:
        return jsonify({'error': f'Score must be between 0 and {total}.'}), 400

    mood = str(data.get('mood') or '–')[:20]

    # 3. Database transaction with rollback
    try:
        session = CSBSession(
            user_id=user.id,
            unit=unit,
            score=score,
            total=total,
            mood=mood,
            date=format_display_date()
        )
        db.session.add(session)
        upsert_csb_best(user.id, unit, score)
        update_streak(user)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error("Failed to save CSB session for user %s: %s", user.id, exc)
        return jsonify({'error': 'An error occurred while saving your session. Please try again.'}), 500

    return jsonify(build_user_response(user)), 200


# ─────────────────────────────────────────────────────────
# POST /api/sessions/mc
# Called after the student clicks "Submit Unit" in the MC workbook.
# ─────────────────────────────────────────────────────────
@sessions_bp.route('/mc', methods=['POST'])
@require_auth
def save_mc_session():
    """
    Save a Mistake Correction session.

    Expects JSON body:
        {
            unit: 1-5,
            score: int,
            total: int,
            mood: str (optional),
            typeStats:   { findMistake: int, tf: int, radio: int, fill: int },
            typeCorrect: { findMistake: int, tf: int, radio: int, fill: int }
        }
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Invalid request body.'}), 400

    user = g.user

    # 1. Type and value validation
    try:
        unit  = parse_strict_int(data.get('unit'), 'Unit')
        score = parse_strict_int(data.get('score'), 'Score')
        total = parse_strict_int(data.get('total'), 'Total')
    except ValueError as err:
        return jsonify({'error': str(err)}), 400

    if unit not in range(1, 6):
        return jsonify({'error': 'Unit must be between 1 and 5.'}), 400

    if total < 1 or total > 15:
        return jsonify({'error': 'Total questions must be between 1 and 15.'}), 400

    if score < 0 or score > total:
        return jsonify({'error': f'Score must be between 0 and {total}.'}), 400

    mood = str(data.get('mood') or '–')[:20]

    # 2. Validate question-type stats
    raw_type_stats = data.get('typeStats')
    raw_type_correct = data.get('typeCorrect')
    if raw_type_stats is not None and not isinstance(raw_type_stats, dict):
        return jsonify({'error': 'typeStats must be an object.'}), 400
    if raw_type_correct is not None and not isinstance(raw_type_correct, dict):
        return jsonify({'error': 'typeCorrect must be an object.'}), 400

    type_stats = raw_type_stats or {}
    type_correct = raw_type_correct or {}

    if len(type_stats) > len(ALLOWED_MC_TYPES) or len(type_correct) > len(ALLOWED_MC_TYPES):
        return jsonify({'error': 'Too many question type entries.'}), 400

    cleaned_stats = {}
    for k in set(type_stats.keys()).union(set(type_correct.keys())):
        if k not in ALLOWED_MC_TYPES:
            return jsonify({'error': f'Invalid question type key: {k}'}), 400
        try:
            att = parse_strict_int(type_stats.get(k, 0), f'{k} attempted')
            cor = parse_strict_int(type_correct.get(k, 0), f'{k} correct')
        except ValueError as err:
            return jsonify({'error': str(err)}), 400

        if att < 0 or cor < 0:
            return jsonify({'error': 'Question type counts cannot be negative.'}), 400
        if cor > att:
            return jsonify({'error': f'Correct count cannot exceed attempted count for {k}.'}), 400

        cleaned_stats[k] = (att, cor)

    # Cross-check sums if stats were provided
    if cleaned_stats:
        sum_attempted = sum(att for att, cor in cleaned_stats.values())
        sum_correct = sum(cor for att, cor in cleaned_stats.values())
        if sum_attempted != total:
            return jsonify({'error': f'Sum of question type attempts ({sum_attempted}) must match total ({total}).'}), 400
        if sum_correct != score:
            return jsonify({'error': f'Sum of question type correct ({sum_correct}) must match score ({score}).'}), 400

    # 3. Database transaction with rollback
    try:
        session = MCSession(
            user_id=user.id,
            unit=unit,
            score=score,
            total=total,
            mood=mood,
            date=format_display_date()
        )
        db.session.add(session)
        upsert_mc_best(user.id, unit, score)

        for type_key, (att, cor) in cleaned_stats.items():
            row = MCTypeStat.query.filter_by(user_id=user.id, type_key=type_key).first()
            if row:
                row.attempted += att
                row.correct   += cor
            else:
                db.session.add(MCTypeStat(
                    user_id=user.id,
                    type_key=type_key,
                    attempted=att,
                    correct=cor
                ))

        update_streak(user)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error("Failed to save MC session for user %s: %s", user.id, exc)
        return jsonify({'error': 'An error occurred while saving your session. Please try again.'}), 500

    return jsonify(build_user_response(user)), 200


# ─────────────────────────────────────────────────────────
# ADAPTIVE LEARNING SYSTEM (V1) ROUTES
# ─────────────────────────────────────────────────────────
from sessions_adaptive import (
    handle_csb_start, handle_csb_cancel, handle_csb_submit,
    handle_mc_start, handle_mc_attempt, handle_mc_cancel, handle_mc_submit
)


@sessions_bp.route('/csb/start', methods=['POST'])
@require_auth
def csb_start():
    """Start or resume a Calculation Speed Booster learning session."""
    return handle_csb_start()


@sessions_bp.route('/csb/cancel', methods=['POST'])
@require_auth
def csb_cancel():
    """Cancel an active CSB learning session."""
    return handle_csb_cancel()


@sessions_bp.route('/csb/submit', methods=['POST'])
@require_auth
def csb_submit():
    """Batch-submit a completed CSB learning session."""
    return handle_csb_submit()


@sessions_bp.route('/mc/start', methods=['POST'])
@require_auth
def mc_start():
    """Start or resume a Mistake Correction learning session."""
    return handle_mc_start()


@sessions_bp.route('/mc/attempt', methods=['POST'])
@require_auth
def mc_attempt():
    """Grade and record an attempt for a specific MC session slot."""
    return handle_mc_attempt()


@sessions_bp.route('/mc/cancel', methods=['POST'])
@require_auth
def mc_cancel():
    """Cancel an active MC learning session."""
    return handle_mc_cancel()


@sessions_bp.route('/mc/submit', methods=['POST'])
@require_auth
def mc_submit():
    """Submit a completed 15-question MC learning session."""
    return handle_mc_submit()

