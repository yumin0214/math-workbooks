# SpeedCalc — Single Flask Service

This app used to be two deployments (a static frontend on Netlify + an API
on Render). It's now one Flask app that serves everything — HTML pages,
CSS/JS, and the JSON API — on a single origin.

## Project structure

```
speedcalc/
├── app.py                 # App factory, blueprint registration, health check
├── pages.py                # Routes that render the HTML templates
├── auth.py                 # /api/auth/* (signup, login)
├── auth_guard.py            # @require_auth JWT decorator
├── user.py                  # /api/user
├── sessions.py               # /api/sessions/*
├── ai.py                     # /api/ai/* (Anthropic-powered reports)
├── models.py                 # SQLAlchemy models
├── config.py                 # Env-based config
├── requirements.txt
├── Procfile                  # gunicorn app:app
├── templates/                # All HTML pages (Jinja2)
│   ├── index.html
│   ├── login.html
│   ├── dashboard.html
│   ├── calculation_speed_booster.html
│   └── mistake_correction.html
└── static/
    ├── css/                   # One stylesheet per page (extracted from <style>)
    └── js/                    # One script per page (extracted from <script>)
```

## Routes

| URL                     | Serves                              |
|--------------------------|--------------------------------------|
| `/`                      | `index.html` (marketing page)         |
| `/login`                  | `login.html`                          |
| `/dashboard`              | `dashboard.html`                      |
| `/speed-booster`          | `calculation_speed_booster.html`      |
| `/mistake-correction`     | `mistake_correction.html`             |
| `/health`                 | JSON health check                     |
| `/api/auth/signup`        | POST — create account                 |
| `/api/auth/login`         | POST — login                          |
| `/api/user`               | GET — current user (JWT required)     |
| `/api/sessions/csb`       | POST — save Speed Booster session     |
| `/api/sessions/mc`        | POST — save Mistake Correction session|
| `/api/ai/csb-report`      | POST — AI performance report          |
| `/api/ai/mc-report`       | POST — AI mistake-pattern report      |

Static assets are served automatically by Flask from `/static/...` (Flask's
default behaviour — no extra config needed).

## What changed from the old two-service setup

- **No more CORS.** The frontend JS used to call a separate API origin
  (`http://localhost:5000` or a Render URL). All the JS files now use
  `const API_BASE = ''`, so `fetch(API_BASE + '/api/...')` hits the same
  origin the page was served from. `flask-cors` has been removed from
  `requirements.txt` and there's no `CORS(...)` call in `app.py` anymore.
- **Inline CSS/JS extracted.** Each HTML file used to carry a large inline
  `<style>` and `<script>` block. Those are now `static/css/<page>.css` and
  `static/js/<page>.js`, linked in with
  `{{ url_for('static', filename='css/...') }}` /
  `{{ url_for('static', filename='js/...') }}`, so browsers cache them and
  they're just plain static files (no Jinja processing happens inside them).
- **Internal navigation now uses real Flask routes** instead of static
  filenames — e.g. `href="login.html"` became `href="/login"`, and
  `window.location.href = 'dashboard.html'` became
  `window.location.href = '/dashboard'` in the extracted JS. This works
  because the JS files are plain static files and can't use Jinja's
  `url_for`, so plain root-relative paths are used instead (and they match
  the routes registered in `pages.py`).
- **Auth is unchanged.** Still JWT in `localStorage`, still
  `Authorization: Bearer <token>` on every API call, still bcrypt password
  hashing. None of that needed to change since it was always same-origin
  from the browser's perspective once served from one Flask app.

## Running locally

```bash
python3 -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env           # then edit .env with your own values

python app.py                  # dev server on http://127.0.0.1:5000
```

Visit `http://127.0.0.1:5000/` — the whole app (marketing page, login,
dashboard, both workbooks, and the API) is now on that one URL.

## Deploying to Render as a single Web Service

1. Push this project to a Git repo.
2. On Render: **New → Web Service**, connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: leave blank (Render will use the `Procfile`:
   `web: gunicorn app:app`) — or set it explicitly to `gunicorn app:app`.
5. Add environment variables in the Render dashboard:
   - `JWT_SECRET_KEY` — a long random string
   - `DATABASE_URL` — e.g. a Render Postgres instance's internal URL
     (Render provides this in `postgres://...` form; `config.py` already
     rewrites it to `postgresql://...` for SQLAlchemy)
   - `ANTHROPIC_API_KEY` — your Anthropic API key for the AI reports
6. Deploy. Render gives you one URL (e.g. `https://speedcalc.onrender.com`)
   that serves the frontend pages, static assets, and the API — no second
   service, no CORS configuration, no separate Netlify deploy needed.
