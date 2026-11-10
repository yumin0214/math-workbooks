from flask import Blueprint, jsonify, g

from auth_guard import require_auth
from models import CSBSession, MCSession, CSBBestScore, MCBestScore, MCTypeStat

user_bp = Blueprint('user', __name__)

# All question type keys the MC workbook tracks
MC_TYPE_KEYS = ['findMistake', 'tf', 'radio', 'fill']


# ─────────────────────────────────────────────────────────
# HELPER — assemble the full user JSON the frontend expects
# ─────────────────────────────────────────────────────────
def build_user_response(user) -> dict:
    """
    Builds a JSON-serialisable dict that matches the shape the
    frontend previously read out of localStorage. This means the
    frontend needs almost no changes — it just reads this response
    instead of calling getUsers()[email].

    Shape returned:
    {
        id, email, fname, lname, grade, age, school, city,
        streak, lastDate,
        bestScores:   [u1, u2, u3, u4, u5],   (CSB, max 20/20/20/20/30)
        mcBestScores: [u1, u2, u3, u4, u5],   (MC,  max 15 each)
        sessions:   [ { date, unit, score, total, mood }, ... ],
        mcSessions: [ { date, unit, score, total, mood }, ... ],
        mcTypeStats: {
            findMistake: { a: <attempted>, c: <correct> },
            tf:          { a, c },
            radio:       { a, c },
            fill:        { a, c }
        }
    }
    """
    # ── Best scores (always 5 elements, 0 if unit not played) ──
    csb_rows = CSBBestScore.query.filter_by(user_id=user.id).order_by(CSBBestScore.unit).all()
    mc_rows  = MCBestScore.query.filter_by(user_id=user.id).order_by(MCBestScore.unit).all()

    best_scores    = [0, 0, 0, 0, 0]
    mc_best_scores = [0, 0, 0, 0, 0]
    for row in csb_rows:
        if 1 <= row.unit <= 5:
            best_scores[row.unit - 1] = row.best_score
    for row in mc_rows:
        if 1 <= row.unit <= 5:
            mc_best_scores[row.unit - 1] = row.best_score

    # ── Sessions ──
    csb_sessions = (
        CSBSession.query
        .filter_by(user_id=user.id)
        .order_by(CSBSession.created_at)
        .all()
    )
    mc_sessions = (
        MCSession.query
        .filter_by(user_id=user.id)
        .order_by(MCSession.created_at)
        .all()
    )

    sessions_list = [
        {'date': s.date, 'unit': s.unit, 'score': s.score, 'total': s.total, 'mood': s.mood or '–'}
        for s in csb_sessions
    ]
    mc_sessions_list = [
        {'date': s.date, 'unit': s.unit, 'score': s.score, 'total': s.total, 'mood': s.mood or '–'}
        for s in mc_sessions
    ]

    # ── MC type stats (guarantee all 4 keys are present) ──
    type_rows = MCTypeStat.query.filter_by(user_id=user.id).all()
    stats_by_key = {t.type_key: t for t in type_rows}
    mc_type_stats = {}
    for key in MC_TYPE_KEYS:
        row = stats_by_key.get(key)
        mc_type_stats[key] = {
            'a': row.attempted if row else 0,
            'c': row.correct   if row else 0
        }

    return {
        'id':            user.id,
        'email':         user.email,
        'fname':         user.fname,
        'lname':         user.lname,
        'grade':         user.grade,
        'age':           user.age,
        'school':        user.school,
        'city':          user.city,
        'streak':        user.streak or 0,
        'lastDate':      user.last_date,
        'bestScores':    best_scores,
        'mcBestScores':  mc_best_scores,
        'sessions':      sessions_list,
        'mcSessions':    mc_sessions_list,
        'mcTypeStats':   mc_type_stats,
    }


# ─────────────────────────────────────────────────────────
# GET /api/user
# ─────────────────────────────────────────────────────────
@user_bp.route('/user', methods=['GET'])
@require_auth
def get_user():
    """
    Returns the full user data object for the logged-in student.
    Called once when the dashboard or workbook page loads.
    The frontend uses this instead of getUsers()[email] from localStorage.
    """
    return jsonify(build_user_response(g.user)), 200
