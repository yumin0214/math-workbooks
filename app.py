from flask import Flask, jsonify

from config import Config
from models import db
from pages import pages_bp
from auth import auth_bp
from user import user_bp
from sessions import sessions_bp
from ai import ai_bp


def create_app(config_override: dict = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_override:
        app.config.update(config_override)

    # ── DATABASE ─────────────────────────────────────────────
    db.init_app(app)

    # ── BLUEPRINTS ───────────────────────────────────────────
    # pages_bp serves the frontend (HTML templates from /templates,
    # CSS/JS from /static). Everything else is the JSON API.
    # Since the frontend and API are now served by this single Flask
    # app on one origin, there is no cross-origin traffic and no
    # CORS configuration is needed.
    app.register_blueprint(pages_bp)
    app.register_blueprint(auth_bp,     url_prefix='/api/auth')
    app.register_blueprint(user_bp,     url_prefix='/api')
    app.register_blueprint(sessions_bp, url_prefix='/api/sessions')
    app.register_blueprint(ai_bp,       url_prefix='/api/ai')

    # ── CREATE TABLES ────────────────────────────────────────
    # Creates all DB tables defined in models.py if they don't exist yet.
    # Safe to run on every startup — does not overwrite existing data.
    with app.app_context():
        db.create_all()

    # ── HEALTH CHECK ─────────────────────────────────────────
    # Render (and any uptime monitor) can use this to verify the
    # server is alive.
    @app.route('/health')
    def health():
        return jsonify({'status': 'ok', 'service': 'SpeedCalc'}), 200

    # ── GLOBAL ERROR HANDLERS ────────────────────────────────
    # These only apply to /api/* routes in practice, since page
    # routes render templates directly. Kept JSON so existing
    # frontend error handling (which expects JSON) keeps working.
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'error': 'Endpoint not found.'}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({'error': 'Method not allowed.'}), 405

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({'error': 'Internal server error.'}), 500

    return app


# Create the app instance (used by gunicorn in production)
app = create_app()

if __name__ == '__main__':
    # Local development only — Render uses gunicorn via Procfile
    app.run(debug=True, port=5000)
