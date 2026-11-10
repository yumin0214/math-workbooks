from flask import Blueprint, request, jsonify
from datetime import datetime, timezone, timedelta
import logging
import re
import bcrypt
import jwt

from config import Config
from models import db, User, CSBBestScore, MCBestScore, MCTypeStat

logger = logging.getLogger(__name__)
auth_bp = Blueprint('auth', __name__)

EMAIL_REGEX = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


# ─────────────────────────────────────────────────────────
# HELPER — create a JWT token for a user
# ─────────────────────────────────────────────────────────
def create_token(user_id: int) -> str:
    """
    Create a signed JWT token containing the user's ID.
    Expires in 7 days. The frontend stores this and sends it
    with every subsequent request in the Authorization header.
    """
    from flask import current_app
    secret = current_app.config.get('SECRET_KEY') or Config.SECRET_KEY
    payload = {
        'user_id': user_id,
        'exp': datetime.now(timezone.utc) + timedelta(days=7)
    }
    return jwt.encode(payload, secret, algorithm='HS256')


# ─────────────────────────────────────────────────────────
# POST /api/auth/signup
# ─────────────────────────────────────────────────────────
@auth_bp.route('/signup', methods=['POST'])
def signup():
    """
    Register a new student account.

    Expects JSON body:
        { email, password, fname, lname, grade, age, school, city }

    Returns:
        201 { token } on success
        4xx { error } on failure
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Invalid request body.'}), 400

    # 1. Names validation & trimming
    fname = str(data.get('fname') or '').strip()
    lname = str(data.get('lname') or '').strip()
    if not fname or not lname:
        return jsonify({'error': 'Please enter your first and last name.'}), 400
    if len(fname) > 50 or len(lname) > 50:
        return jsonify({'error': 'Name must be 50 characters or less.'}), 400

    # 2. Email validation
    email = str(data.get('email') or '').lower().strip()
    if not email or len(email) > 254 or not EMAIL_REGEX.match(email):
        return jsonify({'error': 'Please enter a valid email address.'}), 400

    # 3. Password validation
    raw_password = data.get('password')
    if not isinstance(raw_password, str):
        return jsonify({'error': 'Please enter your password.'}), 400
    if len(raw_password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters.'}), 400
    password_bytes = raw_password.encode('utf-8')
    if len(password_bytes) > 72:
        return jsonify({'error': 'Password cannot exceed 72 bytes.'}), 400

    # 4. Grade validation (Classes 6–10)
    raw_grade = data.get('grade')
    if isinstance(raw_grade, bool) or raw_grade is None:
        return jsonify({'error': 'Please select a valid grade (Class 6–10).'}), 400
    try:
        grade = int(raw_grade)
    except (ValueError, TypeError):
        return jsonify({'error': 'Please select a valid grade (Class 6–10).'}), 400
    if grade not in range(6, 11):
        return jsonify({'error': 'Grade must be between Class 6 and 10.'}), 400

    # 5. Optional fields
    raw_age = data.get('age')
    age = 0
    if raw_age is not None and not isinstance(raw_age, bool):
        try:
            age = int(raw_age)
            if age < 0 or age > 100:
                age = 0
        except (ValueError, TypeError):
            age = 0

    school = str(data.get('school') or '').strip()[:100]
    city   = str(data.get('city') or '').strip()[:100]

    # Check if email already taken
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'An account with this email already exists. Please login.'}), 409

    # 6. Database transaction with rollback
    try:
        password_hash = bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode('utf-8')

        user = User(
            email=email,
            password_hash=password_hash,
            fname=fname,
            lname=lname,
            grade=grade,
            age=age,
            school=school,
            city=city,
            streak=0,
            last_date=None
        )
        db.session.add(user)
        db.session.flush()

        # Initialise best score rows for all 5 units (both workbooks)
        for unit in range(1, 6):
            db.session.add(CSBBestScore(user_id=user.id, unit=unit, best_score=0))
            db.session.add(MCBestScore(user_id=user.id,  unit=unit, best_score=0))

        # Initialise MC question type stats
        for type_key in ['findMistake', 'tf', 'radio', 'fill']:
            db.session.add(MCTypeStat(
                user_id=user.id,
                type_key=type_key,
                attempted=0,
                correct=0
            ))

        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error("Signup database transaction failed: %s", exc)
        return jsonify({'error': 'An error occurred while creating your account. Please try again.'}), 500

    token = create_token(user.id)
    return jsonify({'token': token}), 201


# ─────────────────────────────────────────────────────────
# POST /api/auth/login
# ─────────────────────────────────────────────────────────
@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Log in with email and password.

    Expects JSON body:
        { email, password }

    Returns:
        200 { token } on success
        4xx { error } on failure
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Invalid request body.'}), 400

    email = str(data.get('email') or '').lower().strip()
    raw_password = data.get('password')

    if not email or not raw_password or not isinstance(raw_password, str):
        return jsonify({'error': 'Please enter your email and password.'}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'error': 'No account found with this email. Please sign up.'}), 404

    password_bytes = raw_password.encode('utf-8')
    if len(password_bytes) > 72:
        return jsonify({'error': 'Incorrect password. Please try again.'}), 401

    if not bcrypt.checkpw(password_bytes, user.password_hash.encode('utf-8')):
        return jsonify({'error': 'Incorrect password. Please try again.'}), 401

    token = create_token(user.id)
    return jsonify({'token': token}), 200
