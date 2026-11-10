import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # ── ENVIRONMENT & JWT ────────────────────────────────
    ENV = os.environ.get('FLASK_ENV') or os.environ.get('ENVIRONMENT') or ('production' if os.environ.get('RENDER') == 'true' else 'development')
    IS_PRODUCTION = (str(ENV).lower() == 'production')

    _secret = os.environ.get('JWT_SECRET_KEY')
    _insecure_defaults = {
        'dev-secret-change-in-production',
        'change-this-to-a-long-random-string',
        'dev-secret-local-development-only',
        'dev-secret-local-math-workbooks-only',
    }

    if IS_PRODUCTION:
        if not _secret or _secret in _insecure_defaults or len(_secret.strip()) < 32:
            raise RuntimeError(
                "FATAL: In production, JWT_SECRET_KEY must be set in the environment "
                "with a secure key of at least 32 characters."
            )
        SECRET_KEY = _secret
    else:
        SECRET_KEY = _secret if _secret else 'dev-secret-change-in-production'

    # ── DATABASE ─────────────────────────────────────────
    # Render gives DATABASE_URL starting with postgres:// but
    # SQLAlchemy 1.4+ requires postgresql:// — fix it here
    _db_url = os.environ.get('DATABASE_URL', 'sqlite:///speedcalc_dev.db')
    if _db_url.startswith('postgres://'):
        _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── ANTHROPIC ─────────────────────────────────────────
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

    # Note: no CORS / ALLOWED_ORIGINS setting needed anymore.
    # The frontend (templates + static) and the API are served by
    # this same Flask app on a single origin, so there is no
    # cross-origin request to configure for.
