from flask import Blueprint, render_template

# ─────────────────────────────────────────────────────────
# FRONTEND PAGES
# Serves the HTML templates directly from Flask. This replaces
# the old setup where the frontend was hosted separately on
# Netlify and talked to the API over CORS — now everything is
# one Flask app / one origin / one URL.
# ─────────────────────────────────────────────────────────
pages_bp = Blueprint('pages', __name__)


@pages_bp.route('/')
def index():
    """Marketing / landing page."""
    return render_template('index.html')


@pages_bp.route('/login')
def login_page():
    """Login & signup page."""
    return render_template('login.html')


@pages_bp.route('/dashboard')
def dashboard_page():
    """Student dashboard (progress, reports, history)."""
    return render_template('dashboard.html')


@pages_bp.route('/speed-booster')
def speed_booster_page():
    """Calculation Speed Booster workbook."""
    return render_template('calculation_speed_booster.html')


@pages_bp.route('/mistake-correction')
def mistake_correction_page():
    """Mistake Correction workbook."""
    return render_template('mistake_correction.html')
