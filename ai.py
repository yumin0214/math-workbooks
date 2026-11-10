import logging
from flask import Blueprint, jsonify, g

from config import Config
from auth_guard import require_auth
from models import CSBBestScore, MCBestScore, CSBSession, MCSession, MCTypeStat
from rule_engine import generate_csb_report, generate_mc_report

logger = logging.getLogger(__name__)
ai_bp = Blueprint('ai', __name__)

# Legacy Anthropic model identifier (preserved for optional future reference)
MODEL = 'claude-sonnet-4-20250514'

# Question type display names for the MC report
MC_TYPE_NAMES = {
    'findMistake': 'Find the Mistake',
    'tf':          'True or False',
    'radio':       'Which One is Right',
    'fill':        'Fill the Step / Fix & Solve',
}


# ─────────────────────────────────────────────────────────
# OPTIONAL HELPER — call Anthropic API if key is present
# ─────────────────────────────────────────────────────────
def call_anthropic(prompt: str) -> str:
    """
    Optional helper function if an external LLM is explicitly desired in future.
    Default reporting routes no longer depend on this, guaranteeing zero-cost
    deterministic operation without external API keys.
    """
    import anthropic
    client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        messages=[{'role': 'user', 'content': prompt}]
    )
    return message.content[0].text


# ─────────────────────────────────────────────────────────
# POST /api/ai/csb-report
# Generates performance analysis for the Speed Booster workbook.
# Uses deterministic rule_engine.py without paid external APIs.
# ─────────────────────────────────────────────────────────
@ai_bp.route('/csb-report', methods=['POST'])
@require_auth
def csb_report():
    """
    Build a personalized CSB performance report using the student's
    actual data from the database and the deterministic rule engine.

    Returns:
        200 { report: "<Rule-generated text with 4 standard headings>" }
    """
    user = g.user

    try:
        best_rows = (
            CSBBestScore.query
            .filter_by(user_id=user.id)
            .order_by(CSBBestScore.unit)
            .all()
        )
        sessions = (
            CSBSession.query
            .filter_by(user_id=user.id)
            .order_by(CSBSession.created_at)
            .all()
        )

        report_text = generate_csb_report(user, sessions, best_rows)
        return jsonify({'report': report_text}), 200
    except Exception as exc:
        logger.error("Failed to generate CSB report for user %s: %s", user.id, exc)
        return jsonify({'error': 'Report generation failed. Please try again.'}), 500


# ─────────────────────────────────────────────────────────
# POST /api/ai/mc-report
# Generates mistake pattern analysis for the MC workbook.
# Uses deterministic rule_engine.py without paid external APIs.
# ─────────────────────────────────────────────────────────
@ai_bp.route('/mc-report', methods=['POST'])
@require_auth
def mc_report():
    """
    Build a personalized MC error pattern report using the student's
    actual data from the database and the deterministic rule engine.

    Returns:
        200 { report: "<Rule-generated text with 4 standard headings>" }
    """
    user = g.user

    try:
        best_rows = (
            MCBestScore.query
            .filter_by(user_id=user.id)
            .order_by(MCBestScore.unit)
            .all()
        )
        sessions = (
            MCSession.query
            .filter_by(user_id=user.id)
            .order_by(MCSession.created_at)
            .all()
        )
        type_rows = MCTypeStat.query.filter_by(user_id=user.id).all()

        report_text = generate_mc_report(user, sessions, best_rows, type_rows)
        return jsonify({'report': report_text}), 200
    except Exception as exc:
        logger.error("Failed to generate MC report for user %s: %s", user.id, exc)
        return jsonify({'error': 'Report generation failed. Please try again.'}), 500
