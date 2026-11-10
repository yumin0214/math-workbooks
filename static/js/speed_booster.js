// ══════════════════════════════
// Calculation Speed Booster (CSB)
// Adaptive Learning System (Version 1) Frontend Controller
// ══════════════════════════════

const API_BASE = '';  // same-origin Flask backend
const TOKEN_KEY = 'csb_token';

// ─────────────────────────────────────────────────────────
// API HELPERS
// ─────────────────────────────────────────────────────────
function getToken() { return localStorage.getItem(TOKEN_KEY); }
function setToken(t) { localStorage.setItem(TOKEN_KEY, t); }
function clearToken() { localStorage.removeItem(TOKEN_KEY); }

async function apiGet(path) {
  try {
    const res = await fetch(API_BASE + path, {
      headers: { 'Authorization': 'Bearer ' + getToken() }
    });
    if (res.status === 401) { clearToken(); window.location.href = '/login'; return null; }
    return await res.json();
  } catch (err) {
    showToast('❌ Connection error. Please check your internet.');
    return null;
  }
}

async function apiPost(path, body = {}) {
  try {
    const res = await fetch(API_BASE + path, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + getToken() },
      body:    JSON.stringify(body)
    });
    if (res.status === 401) { clearToken(); window.location.href = '/login'; return null; }
    return await res.json();
  } catch (err) {
    showToast('❌ Connection error. Please check your internet.');
    return null;
  }
}

// ─────────────────────────────────────────────────────────
// STATE MANAGEMENT
// ─────────────────────────────────────────────────────────
let currentUser = null;
let currentUnitIndex = 0; // 0-indexed (0=Unit 1, 4=Unit 5)
const activeCSBSessions = {}; // unit (1..5) -> { session_id, questions, total, completed }
let isSubmitting = false;
let lastCompletedUnit = null;

// IST Date Helper (UTC+5:30)
function getTodayDateIST() {
  const d = new Date();
  const utc = d.getTime() + (d.getTimezoneOffset() * 60000);
  const istDate = new Date(utc + (3600000 * 5.5));
  const year = istDate.getFullYear();
  const month = String(istDate.getMonth() + 1).padStart(2, '0');
  const day = String(istDate.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function getCSBStorageKey() {
  if (!currentUser) return null;
  return `csb_state_${currentUser.id}_${getTodayDateIST()}`;
}

function saveCSBState() {
  const key = getCSBStorageKey();
  if (!key) return;
  const inputs = {};
  document.querySelectorAll('.drill-q input').forEach(inp => {
    if (inp.id && inp.value) inputs[inp.id] = inp.value;
  });
  const state = {
    date: getTodayDateIST(),
    inputs
  };
  try {
    localStorage.setItem(key, JSON.stringify(state));
  } catch (e) {}
}

// Local draft keys scoped to user and unit so they persist across midnight and sessions
function getCSBDraftKey(unit) {
  if (!currentUser) return null;
  return `csb_drafts_${currentUser.id}_u${unit}`;
}

function saveCSBInputDraft(unit, pos, value) {
  const key = getCSBDraftKey(unit);
  if (!key) return;
  let drafts = {};
  try {
    const raw = localStorage.getItem(key);
    if (raw) drafts = JSON.parse(raw) || {};
  } catch (e) {}
  drafts[pos] = value;
  try {
    localStorage.setItem(key, JSON.stringify(drafts));
  } catch (e) {}
  saveCSBState();
}

function restoreCSBInputDrafts(unit) {
  const key = getCSBDraftKey(unit);
  if (!key) return;
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return;
    const drafts = JSON.parse(raw);
    if (!drafts) return;
    for (const [pos, val] of Object.entries(drafts)) {
      const inp = document.querySelector(`#unit-${unit - 1} input[data-pos="${pos}"]`);
      if (inp) {
        inp.value = val;
      }
    }
  } catch (e) {
    console.warn('Could not restore CSB input drafts', e);
  }
}

function clearCSBInputDrafts(unit) {
  const key = getCSBDraftKey(unit);
  if (key) {
    localStorage.removeItem(key);
  }
}

function attachCSBInputListeners(unit) {
  const unitEl = document.getElementById(`unit-${unit - 1}`);
  if (!unitEl) return;
  unitEl.querySelectorAll('.drill-q input[data-pos]').forEach(inp => {
    const onInput = (e) => {
      const pos = e.target.getAttribute('data-pos');
      const val = e.target.value;
      saveCSBInputDraft(unit, pos, val);
    };
    if (inp._csbHandler) {
      inp.removeEventListener('input', inp._csbHandler);
    }
    inp._csbHandler = onInput;
    inp.addEventListener('input', onInput);
  });
}

// ─────────────────────────────────────────────────────────
// AUTH
// ─────────────────────────────────────────────────────────
function switchTab(tab) {
  document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
  if (event && event.target) event.target.classList.add('active');
  document.getElementById('form-login').style.display = tab === 'login' ? '' : 'none';
  document.getElementById('form-signup').style.display = tab === 'signup' ? '' : 'none';
  hideError();
}

function showError(msg) {
  const el = document.getElementById('auth-error');
  el.textContent = msg; el.style.display = 'block';
}
function hideError() { document.getElementById('auth-error').style.display = 'none'; }

async function doSignup() {
  const fname    = document.getElementById('su-fname').value.trim();
  const lname    = document.getElementById('su-lname').value.trim();
  const grade    = document.getElementById('su-grade').value;
  const age      = document.getElementById('su-age').value.trim();
  const school   = document.getElementById('su-school').value.trim();
  const city     = document.getElementById('su-city').value.trim();
  const email    = document.getElementById('su-email').value.trim().toLowerCase();
  const password = document.getElementById('su-password').value;
  const confirm  = document.getElementById('su-confirm').value;

  if (!fname||!lname||!grade||!age||!school||!city||!email||!password)
    return showError('Please fill in all fields.');
  if (password !== confirm) return showError('Passwords do not match.');
  if (password.length < 6)  return showError('Password must be at least 6 characters.');

  hideError();
  try {
    const res = await fetch(API_BASE + '/api/auth/signup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fname, lname, grade, age, school, city, email, password })
    });
    const data = await res.json();
    if (!res.ok) return showError(data.error || 'Sign up failed.');
    setToken(data.token);
    const user = await apiGet('/api/user');
    if (user) await loadWorkbook(user);
  } catch (err) {
    showError('Could not connect to server. Please try again.');
  }
}

async function doLogin() {
  const email    = document.getElementById('login-email').value.trim().toLowerCase();
  const password = document.getElementById('login-password').value;
  if (!email || !password) return showError('Please enter your email and password.');
  hideError();
  try {
    const res = await fetch(API_BASE + '/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    const data = await res.json();
    if (!res.ok) return showError(data.error || 'Login failed.');
    setToken(data.token);
    const user = await apiGet('/api/user');
    if (user) await loadWorkbook(user);
  } catch (err) {
    showError('Could not connect to server. Please try again.');
  }
}

function doLogout() {
  clearToken();
  window.location.href = '/login';
}

// ─────────────────────────────────────────────────────────
// WORKBOOK INITIALIZATION & PROGRESS
// ─────────────────────────────────────────────────────────
async function loadWorkbook(user) {
  currentUser = user;
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById('screen-workbook').classList.add('active');

  document.getElementById('tb-avatar').textContent = user.fname[0].toUpperCase();
  document.getElementById('tb-name').textContent   = user.fname + ' ' + user.lname;
  document.getElementById('tb-grade').textContent  = 'Grade ' + user.grade + ' · ' + user.city;
  document.getElementById('cover-grade').textContent = 'Grade ' + user.grade;
  document.getElementById('tb-streak').textContent = '🔥 ' + (user.streak || 1) + ' day streak';

  updateProgress(user);

  // Initialize the currently active unit (defaulting to Unit 1)
  await initCSBUnit(currentUnitIndex + 1);
}

function updateProgress(u) {
  const totals = [20, 20, 20, 20, 30];
  (u.bestScores || [0,0,0,0,0]).forEach((s, i) => {
    const pct = Math.round((s / totals[i]) * 100);
    const bars = document.querySelectorAll('.prog-bar-inner');
    if (bars[i]) bars[i].style.width = pct + '%';
    const scoreEl = document.getElementById('ps' + (i + 1));
    if (scoreEl) scoreEl.textContent = s + '/' + totals[i];
  });
}

// ─────────────────────────────────────────────────────────
// ADAPTIVE QUESTION RENDERING & DRILL SETUP
// ─────────────────────────────────────────────────────────
function renderCSBDrill(containerId, qs, offset = 0) {
  const c = document.getElementById(containerId);
  if (!c || !qs) return;
  c.innerHTML = '';
  qs.forEach((item, i) => {
    const pos = offset + i;
    const retryBadge = item.is_retry 
      ? `<span class="badge-retry" style="display:inline-block;margin-left:4px;font-size:10px;font-weight:700;color:#92400e;background:#fef3c7;border:1px solid #fde68a;border-radius:4px;padding:1px 5px" title="Review question from earlier practice">Retry</span>` 
      : '';
    c.innerHTML += `
      <div class="drill-q">
        <span class="q-num">${pos + 1}.</span>
        <span class="q-text-sm">${item.question_text || item.q || ''} ${retryBadge}</span>
        <input class="ans-blank-sm" data-pos="${pos}" data-unit-part="${containerId}" type="text" placeholder="__" id="dq-${containerId}-${i}">
      </div>`;
  });
}

// Start or resume adaptive session for a specific unit
async function initCSBUnit(unit) {
  if (!currentUser) return;
  const expectedTotal = unit === 5 ? 30 : 20;
  const unitEl = document.getElementById(`unit-${unit - 1}`);
  const checkBtn = unitEl ? unitEl.querySelector('.check-btn') : null;

  // If already in memory with an active session, skip re-fetching
  if (activeCSBSessions[unit] && activeCSBSessions[unit].session_id) {
    return;
  }

  const res = await apiPost('/api/sessions/csb/start', { unit });
  if (!res) {
    showToast('⚠️ Could not connect to server.');
    return;
  }

  if (res.error) {
    if (res.error === 'Unit already completed today.') {
      if (checkBtn) {
        checkBtn.disabled = true;
        checkBtn.textContent = '✅ Completed Today';
      }
      const score = (currentUser.bestScores && currentUser.bestScores[unit - 1]) || 0;
      const scVal = document.getElementById('score' + unit + '-val');
      const logSc = document.getElementById('log' + unit + '-score');
      if (scVal) scVal.textContent = score;
      if (logSc) logSc.textContent = score;
      showToast(`ℹ️ Unit ${unit} already completed today. Practice again tomorrow!`);
      return;
    }
    showToast('⚠️ ' + res.error);
    return;
  }

  const sessionId = res.session_id;
  const questions = res.questions || [];
  const total = res.total || expectedTotal;

  activeCSBSessions[unit] = {
    session_id: sessionId,
    questions: questions,
    total: total
  };

  // Render question layout
  if (unit <= 4) {
    renderCSBDrill('drill' + unit, questions, 0);
  } else {
    renderCSBDrill('drill5a', questions.slice(0, 8), 0);
    renderCSBDrill('drill5b', questions.slice(8, 16), 8);
    renderCSBDrill('drill5c', questions.slice(16, 23), 16);
    renderCSBDrill('drill5d', questions.slice(23, 30), 23);
  }

  // Restore draft answers from local storage
  restoreCSBInputDrafts(unit);

  // Attach input event listeners for real-time draft persistence
  attachCSBInputListeners(unit);

  if (checkBtn) {
    checkBtn.disabled = false;
    checkBtn.textContent = unit === 5 ? '✅ Check All Answers' : '✅ Check My Answers';
  }

  if (res.resumed) {
    showToast(`⚡ Resumed in-progress Unit ${unit} session.`);
  }
}

// ─────────────────────────────────────────────────────────
// CHECK & SUBMIT ANSWERS
// ─────────────────────────────────────────────────────────
async function checkAnswers(unit) {
  if (isSubmitting) return;
  const unitEl = document.getElementById(`unit-${unit - 1}`);
  const checkBtn = unitEl ? unitEl.querySelector('.check-btn') : null;
  if (checkBtn && checkBtn.disabled) return;

  const session = activeCSBSessions[unit];
  if (!session || !session.session_id) {
    showToast('⚠️ No active session found. Please refresh or activate this unit.');
    return;
  }

  isSubmitting = true;
  if (checkBtn) {
    checkBtn.disabled = true;
    checkBtn.textContent = 'Saving...';
  }

  showToast('Submitting answers to server...');

  // Assemble answers by position (0 to total - 1)
  const answers = [];
  for (let pos = 0; pos < session.total; pos++) {
    const inp = unitEl ? unitEl.querySelector(`input[data-pos="${pos}"]`) : null;
    const val = inp ? inp.value.trim() : '';
    answers.push({ position: pos, answer: val });
  }

  const selectedFeel = unitEl ? unitEl.querySelector('.feel-btn.selected') : null;
  const mood = selectedFeel ? selectedFeel.textContent.trim() : '–';

  // Submit to adaptive API endpoint
  const saved = await apiPost('/api/sessions/csb/submit', {
    session_id: session.session_id,
    answers: answers,
    mood: mood
  });

  if (saved && !saved.error && saved.score !== undefined) {
    currentUser = saved.user || currentUser;
    updateProgress(currentUser);

    const score = saved.score;
    const total = saved.total;

    // Update score displays
    const scVal = document.getElementById('score' + unit + '-val');
    const logSc = document.getElementById('log' + unit + '-score');
    if (scVal) scVal.textContent = score;
    if (logSc) logSc.textContent = score;

    if (unit <= 4) {
      const bestEl = document.getElementById('log' + unit + '-best');
      if (bestEl && currentUser.bestScores) {
        bestEl.textContent = currentUser.bestScores[unit - 1];
      }
    }

    if (checkBtn) {
      checkBtn.disabled = true;
      checkBtn.textContent = `✅ Completed (${score}/${total})`;
    }

    // Lock inputs
    if (unitEl) {
      unitEl.querySelectorAll('.drill-q input').forEach(inp => {
        inp.disabled = true;
      });
    }

    // Clean up local drafts for this submitted session
    clearCSBInputDrafts(unit);
    delete activeCSBSessions[unit];

    showToast(`✅ Score: ${score}/${total} — Saved!`);
    showCompletionModal(unit, score, total);
  } else {
    if (checkBtn) {
      checkBtn.disabled = false;
      checkBtn.textContent = unit === 5 ? '✅ Check All Answers' : '✅ Check My Answers';
    }
    const errMsg = (saved && saved.error) ? `⚠️ ${saved.error}` : '⚠️ Score could not be saved to server. Check connection.';
    showToast(errMsg);
  }
  isSubmitting = false;
}

// ─────────────────────────────────────────────────────────
// CANCELLATION & FRESH SESSION RESTART
// ─────────────────────────────────────────────────────────
async function cancelCurrentSessionAndRestart() {
  const unit = currentUnitIndex + 1;
  const session = activeCSBSessions[unit];

  if (session && session.session_id) {
    const confirmCancel = confirm(`Cancel current in-progress Unit ${unit} session and start fresh?`);
    if (!confirmCancel) return;

    showToast('Cancelling session...');
    const res = await apiPost('/api/sessions/csb/cancel', { session_id: session.session_id });
    if (res && res.error) {
      showToast('⚠️ ' + res.error);
      return;
    }
    clearCSBInputDrafts(unit);
    delete activeCSBSessions[unit];
    showToast('Session cancelled. Generating fresh questions...');
    await initCSBUnit(unit);
  } else {
    // If no active session in memory, load/refresh unit
    await initCSBUnit(unit);
  }
}

// Keep generateAllQuestions bound to cancellation/restart
function generateAllQuestions(showToastMsg = true) {
  cancelCurrentSessionAndRestart();
}

// ─────────────────────────────────────────────────────────
// COMPLETION MODAL & NAVIGATION
// ─────────────────────────────────────────────────────────
function showCompletionModal(unit, score, total) {
  lastCompletedUnit = unit;
  const modal = document.getElementById('completion-modal');
  if (!modal) return;
  const emoji = document.getElementById('completion-emoji');
  const title = document.getElementById('completion-title');
  const subtitle = document.getElementById('completion-subtitle');
  const badge = document.getElementById('completion-score-badge');
  const nextBtn = document.getElementById('btn-next-unit');

  if (emoji) emoji.textContent = unit === 5 ? '🏆' : '🎉';
  if (title) title.textContent = unit === 5 ? 'Workbook Complete!' : `Unit ${unit} Complete!`;
  if (subtitle) subtitle.textContent = unit === 5 ? 'Amazing effort! You completed all 5 units.' : 'Your score has been saved to your profile.';
  if (badge) badge.textContent = `Score: ${score} / ${total}`;

  if (nextBtn) {
    if (unit >= 5) {
      nextBtn.style.display = 'none';
    } else {
      nextBtn.style.display = 'block';
      nextBtn.textContent = `Proceed to Unit ${unit + 1} →`;
    }
  }
  modal.style.display = 'flex';
}

function closeCompletionModal() {
  const modal = document.getElementById('completion-modal');
  if (modal) modal.style.display = 'none';
}

function goToNextUnit() {
  closeCompletionModal();
  if (lastCompletedUnit && lastCompletedUnit < 5) {
    showUnit(lastCompletedUnit); // lastCompletedUnit (1-indexed) matches next unit's 0-indexed position
  }
}

// ─────────────────────────────────────────────────────────
// UI HELPERS & TIMER
// ─────────────────────────────────────────────────────────
async function showUnit(idx) {
  currentUnitIndex = idx;
  const unitNum = idx + 1;
  document.querySelectorAll('.unit-page').forEach((p, i) => p.classList.toggle('active', i === idx));
  document.querySelectorAll('.unit-tab').forEach((t, i) => {
    const colors = ['#1a56db', '#7c3aed', '#059669', '#dc2626', '#d97706'];
    if (i === idx) {
      t.classList.add('active');
      t.style.background = colors[i];
      t.style.color = 'white';
      t.style.borderColor = 'transparent';
    } else {
      t.classList.remove('active');
      t.style.background = '';
      t.style.color = '';
      t.style.borderColor = '';
    }
  });
  window.scrollTo(0, 0);
  if (currentUser) {
    await initCSBUnit(unitNum);
  }
}

function selectFeel(el) {
  el.parentElement.querySelectorAll('.feel-btn').forEach(s => s.classList.remove('selected'));
  el.classList.add('selected');
}

const timers = {};
function toggleTimer(id) {
  const display = document.getElementById(id + '-display');
  if (!display) return;
  const btn = display.nextElementSibling;
  if (!timers[id]) timers[id] = { running: false, remaining: id === 't5' ? 600 : 300, interval: null };
  const t = timers[id];
  if (t.running) {
    clearInterval(t.interval); t.running = false; if (btn) btn.textContent = 'Resume';
  } else {
    t.running = true; if (btn) btn.textContent = 'Pause';
    t.interval = setInterval(() => {
      if (t.remaining <= 0) {
        clearInterval(t.interval); t.running = false;
        display.textContent = '0:00'; display.style.color = '#ef4444'; if (btn) btn.textContent = 'Done!';
        showToast("⏱ Time's up! Check your answers.");
        return;
      }
      t.remaining--;
      const m = Math.floor(t.remaining / 60), s = t.remaining % 60;
      display.textContent = m + ':' + (s < 10 ? '0' : '') + s;
      if (t.remaining <= 30) display.style.color = '#fbbf24';
      if (t.remaining <= 10) display.style.color = '#ef4444';
    }, 1000);
  }
}

let toastTimer;
function showToast(msg) {
  const t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg; t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 2500);
}

// ─────────────────────────────────────────────────────────
// WINDOW LOAD INITIALIZATION
// ─────────────────────────────────────────────────────────
window.addEventListener('load', async () => {
  const token = getToken();
  if (!token) {
    document.getElementById('screen-auth').classList.add('active');
    return;
  }
  const user = await apiGet('/api/user');
  if (!user || user.error) {
    clearToken();
    document.getElementById('screen-auth').classList.add('active');
    return;
  }
  await loadWorkbook(user);
});
