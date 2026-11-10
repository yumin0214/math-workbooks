// ─────────────────────────────────────────────────────────
// CONFIG — update API_BASE to your Railway URL when deployed
// ─────────────────────────────────────────────────────────
const API_BASE = '';  // same-origin now that Flask serves the frontend too
const TOKEN_KEY = 'csb_token';

// ─────────────────────────────────────────────────────────
// UI HELPERS
// ─────────────────────────────────────────────────────────
function switchTab(tab){
  document.querySelectorAll('.auth-tab').forEach(t=>t.classList.remove('active'));
  event.target.classList.add('active');
  document.getElementById('form-login').style.display=tab==='login'?'':'none';
  document.getElementById('form-signup').style.display=tab==='signup'?'':'none';
  document.getElementById('auth-heading').textContent=tab==='login'?'Welcome back!':'Create your account';
  document.getElementById('auth-sub').textContent=tab==='login'?'Login to continue your practice streak.':'Join SpeedCalc and start your maths journey.';
  hideError();
}
function showError(m){ const e=document.getElementById('auth-error'); e.textContent=m; e.style.display='block'; }
function hideError(){ document.getElementById('auth-error').style.display='none'; }
function setLoading(btn, loading){
  btn.disabled = loading;
  btn.textContent = loading ? '⏳ Please wait...' : btn.dataset.label;
}

// ─────────────────────────────────────────────────────────
// SIGNUP — POST /api/auth/signup
// ─────────────────────────────────────────────────────────
async function doSignup(){
  const fname   = document.getElementById('su-fname').value.trim();
  const lname   = document.getElementById('su-lname').value.trim();
  const grade   = document.getElementById('su-grade').value;
  const age     = document.getElementById('su-age').value.trim();
  const school  = document.getElementById('su-school').value.trim();
  const city    = document.getElementById('su-city').value.trim();
  const email   = document.getElementById('su-email').value.trim().toLowerCase();
  const password = document.getElementById('su-password').value;
  const confirm  = document.getElementById('su-confirm').value;

  if(!fname||!lname||!grade||!age||!school||!city||!email||!password)
    return showError('Please fill in all fields.');
  if(password !== confirm) return showError('Passwords do not match.');
  if(password.length < 6)  return showError('Password must be at least 6 characters.');

  const btn = document.querySelector('#form-signup .btn-primary');
  btn.dataset.label = btn.textContent;
  setLoading(btn, true);
  hideError();

  try {
    const res = await fetch(API_BASE + '/api/auth/signup', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ fname, lname, grade, age, school, city, email, password })
    });
    const data = await res.json();
    if (!res.ok) return showError(data.error || 'Sign up failed. Please try again.');
    localStorage.setItem(TOKEN_KEY, data.token);
    window.location.href = '/dashboard';
  } catch (err) {
    showError('Could not connect to server. Please check your connection.');
  } finally {
    setLoading(btn, false);
  }
}

// ─────────────────────────────────────────────────────────
// LOGIN — POST /api/auth/login
// ─────────────────────────────────────────────────────────
async function doLogin(){
  const email    = document.getElementById('login-email').value.trim().toLowerCase();
  const password = document.getElementById('login-password').value;
  if(!email||!password) return showError('Please enter your email and password.');

  const btn = document.querySelector('#form-login .btn-primary');
  btn.dataset.label = btn.textContent;
  setLoading(btn, true);
  hideError();

  try {
    const res = await fetch(API_BASE + '/api/auth/login', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ email, password })
    });
    const data = await res.json();
    if (!res.ok) return showError(data.error || 'Login failed. Please try again.');
    localStorage.setItem(TOKEN_KEY, data.token);
    window.location.href = '/dashboard';
  } catch (err) {
    showError('Could not connect to server. Please check your connection.');
  } finally {
    setLoading(btn, false);
  }
}

// ─────────────────────────────────────────────────────────
// AUTO-REDIRECT — if token exists and is valid, skip login
// ─────────────────────────────────────────────────────────
window.addEventListener('load', async () => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) return;
  try {
    const res = await fetch(API_BASE + '/api/user', {
      headers: { 'Authorization': 'Bearer ' + token }
    });
    if (res.ok) window.location.href = '/dashboard';
    else localStorage.removeItem(TOKEN_KEY); // token invalid, stay on login
  } catch (err) {
    // Server unreachable — stay on login page, don't clear token yet
  }
});
