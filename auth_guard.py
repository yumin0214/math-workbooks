from functools import wraps
from flask import request, jsonify, g, current_app
import jwt

from config import Config
from models import db, User


def require_auth(f):
    """
    Decorator that protects an endpoint with JWT authentication.

    How it works:
    1. Reads the Authorization header: "Bearer <token>"
    2. Decodes the JWT and checks it's valid and not expired
    3. Loads the user from the database and stores them in Flask's g object
    4. The route handler can then access g.user for the current user

    Usage:
        @some_blueprint.route('/protected')
        @require_auth
        def protected_route():
            user = g.user   # the logged-in User object
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ', 1)[1]

        if not token:
            return jsonify({'error': 'Authentication token missing. Please log in again.'}), 401

        secret = current_app.config.get('SECRET_KEY') or Config.SECRET_KEY

        try:
            payload = jwt.decode(token, secret, algorithms=['HS256'])
            user_id = payload.get('user_id')
            if not isinstance(user_id, int):
                return jsonify({'error': 'Invalid token payload. Please log in again.'}), 401

            user = db.session.get(User, user_id)
            if not user:
                return jsonify({'error': 'User not found. Please log in again.'}), 401
            g.user = user

        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Session expired. Please log in again.'}), 401

        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token. Please log in again.'}), 401

        return f(*args, **kwargs)

    return decorated
