// ══════════════════════════════
// Mistake Correction (MC)
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
    showToast('Connection error. Please check your internet.');
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
    showToast('Connection error. Please check your internet.');
    return null;
  }
}

// ─────────────────────────────────────────────────────────
// STATE MANAGEMENT
// ─────────────────────────────────────────────────────────
let currentUser = null;
let currentMCUnitIndex = 0; // 0-indexed (0=Unit 1, 4=Unit 5)
const activeMCSessions = {}; // unit (1..5) -> { session_id, slots, total }
const exState = {}; // exId -> { selected, checked, correct }
let mcSubmittedUnits = {};
let isSubmittingMC = false;
let lastCompletedMCUnit = null;

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

function getMCStorageKey() {
  if (!currentUser) return null;
  return `mc_state_${currentUser.id}_${getTodayDateIST()}`;
}

function getExState(id) {
  if (!exState[id]) exState[id] = { selected: null, checked: false, correct: false };
  return exState[id];
}

function saveMCState() {
  const key = getMCStorageKey();
  if (!key) return;
  const inputs = {};
  document.querySelectorAll('.fill-input').forEach(inp => {
    if (inp.id && inp.value) inputs[inp.id] = inp.value;
  });
  const state = {
    date: getTodayDateIST(),
    exState,
    inputs,
    submittedUnits: mcSubmittedUnits || {}
  };
  try {
    localStorage.setItem(key, JSON.stringify(state));
  } catch (e) {
    console.warn('Could not save MC state', e);
  }
}

function restoreSavedMCState() {
  const key = getMCStorageKey();
  if (!key) return;
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return;
    const state = JSON.parse(raw);
    if (!state) return;

    if (state.inputs) {
      for (const [id, val] of Object.entries(state.inputs)) {
        const inp = document.getElementById(id);
        if (inp && !inp.readOnly) inp.value = val;
      }
    }
  } catch (e) {
    console.warn('Could not restore MC state', e);
  }
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
  const e = document.getElementById('auth-error');
  if (e) { e.textContent = msg; e.style.display = 'block'; }
}
function hideError() {
  const e = document.getElementById('auth-error');
  if (e) e.style.display = 'none';
}

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
  if (!email || !password) return showError('Please enter email and password.');
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

  document.getElementById('tb-avatar').textContent   = user.fname[0].toUpperCase();
  document.getElementById('tb-name').textContent     = user.fname + ' ' + user.lname;
  document.getElementById('tb-grade').textContent    = 'Grade ' + user.grade + ' · ' + user.city;
  document.getElementById('cover-grade').textContent = 'Grade ' + user.grade;
  document.getElementById('tb-streak').textContent   = '🔥 ' + (user.streak || 1) + ' day streak';

  updateProgress(user);
  initTipsAndHints();
  restoreSavedMCState();

  document.querySelectorAll('.fill-input').forEach(inp => {
    inp.removeEventListener('input', saveMCState);
    inp.addEventListener('input', saveMCState);
  });

  // Initialize active unit (Unit 1 by default)
  await initMCUnit(currentMCUnitIndex + 1);
}

function updateProgress(u) {
  const best = u.mcBestScores || [0,0,0,0,0];
  best.forEach((s, i) => {
    const pct   = Math.round((s / 15) * 100);
    const bar   = document.getElementById('pb' + (i + 1));
    const score = document.getElementById('ps' + (i + 1));
    if (bar)   bar.style.width   = pct + '%';
    if (score) score.textContent = s + '/15';
  });
}

// ─────────────────────────────────────────────────────────
// ADAPTIVE SESSION START & DYNAMIC SLOT RENDERING
// ─────────────────────────────────────────────────────────
async function initMCUnit(unit) {
  if (!currentUser) return;
  const btn = document.getElementById('submit-u' + unit);

  // If already active in memory, no need to re-fetch
  if (activeMCSessions[unit] && activeMCSessions[unit].session_id) {
    return;
  }

  const res = await apiPost('/api/sessions/mc/start', { unit });
  if (!res) {
    showToast('⚠️ Could not connect to server.');
    return;
  }

  if (res.error) {
    if (res.error === 'Unit already completed today.') {
      if (btn) {
        btn.disabled = true;
        btn.textContent = '✅ Completed Today';
      }
      showToast(`ℹ️ Unit ${unit} already completed today. Practice again tomorrow!`);
      return;
    }
    showToast('⚠️ ' + res.error);
    return;
  }

  const sessionId = res.session_id;
  const slots = res.slots || [];
  activeMCSessions[unit] = {
    session_id: sessionId,
    slots: slots,
    total: res.total || 15
  };

  localStorage.setItem(`mc_active_session_${currentUser.id}_${unit}`, sessionId);

  // Render slots, dynamic replacement variants, and restore attempts
  slots.forEach(s => {
    const exId = `u${unit}q${s.slot_number}`;
    const card = document.getElementById(exId);
    if (!card) return;

    // Check if slot was assigned an adaptive replacement variant
    if (s.replacement_for_id && s.presented_question_id !== s.replacement_for_id) {
      let badge = card.querySelector('.badge-variant');
      if (!badge) {
        badge = document.createElement('span');
        badge.className = 'badge-variant';
        badge.style.cssText = 'font-size:10px;font-weight:700;color:#1e40af;background:#dbeafe;border:1px solid #bfdbfe;border-radius:4px;padding:2px 6px;margin-left:6px;display:inline-block;';
        badge.textContent = 'Adaptive Variant';
        const typeEl = card.querySelector('.ex-type');
        if (typeEl) typeEl.appendChild(badge);
      }
      if (s.title) {
        const titleEl = card.querySelector('.ex-title');
        if (titleEl) titleEl.textContent = s.title;
      }
      if (s.prompt_text) {
        const probBox = card.querySelector('.problem-box');
        if (probBox) probBox.innerHTML = s.prompt_text;
      }
    }

    // Restore submitted attempt if already answered in this session
    if (s.answered) {
      const state = getExState(exId);
      state.checked = true;
      state.correct = s.is_correct;
      state.selected = s.submitted_answer;

      const checkBtn = card.querySelector('.check-btn');
      if (checkBtn) {
        checkBtn.disabled = true;
        checkBtn.textContent = '✅ Checked';
      }
      unlockHint(card);

      if (s.submitted_answer !== null && s.submitted_answer !== undefined) {
        const selStr = String(s.submitted_answer).trim();

        // Lock Step buttons
        card.querySelectorAll('.step-btn').forEach((b, idx) => {
          b.classList.add('locked');
          if (String(idx) === selStr) {
            b.classList.add('selected');
            b.classList.add(s.is_correct ? 'correct' : 'incorrect');
          }
        });

        // Lock TF buttons
        card.querySelectorAll('.tf-btn').forEach(b => {
          b.classList.add('locked');
          const btnVal = b.dataset.val || (b.textContent.includes('True') ? 'true' : 'false');
          if (btnVal.toLowerCase() === selStr.toLowerCase()) {
            b.classList.add('selected');
            b.classList.add(s.is_correct ? 'correct' : 'incorrect');
          }
        });

        // Lock Radio buttons
        card.querySelectorAll('.radio-btn').forEach(b => {
          b.classList.add('locked');
          const bVal = String(b.dataset.val || b.getAttribute('data-val') || '').trim().toUpperCase();
          if (bVal === selStr.toUpperCase()) {
            b.classList.add('selected');
            b.classList.add(s.is_correct ? 'correct' : 'incorrect');
          }
        });
        card.querySelectorAll('input[type="radio"]').forEach(inp => inp.disabled = true);

        // Lock Fill inputs
        const fillInputs = card.querySelectorAll('.fill-input');
        fillInputs.forEach(inp => {
          inp.classList.add('locked');
          inp.readOnly = true;
          inp.classList.add(s.is_correct ? 'correct' : 'incorrect');
        });

        try {
          if (selStr.startsWith('[') && selStr.endsWith(']')) {
            const arr = JSON.parse(selStr);
            fillInputs.forEach((inp, i) => {
              if (arr[i] !== undefined) inp.value = arr[i];
            });
          } else if (selStr.includes('|||')) {
            const arr = selStr.split('|||');
            fillInputs.forEach((inp, i) => {
              if (arr[i] !== undefined) inp.value = arr[i].trim();
            });
          } else if (fillInputs.length === 1) {
            fillInputs[0].value = selStr;
          }
        } catch (e) {}
      }

      showResult(exId, s.is_correct ? 1 : 0, 1);
    }
  });

  if (res.resumed) {
    showToast(`⚡ Resumed in-progress Unit ${unit} session.`);
  }
}

// ─────────────────────────────────────────────────────────
// SERVER-SIDE ATTEMPT SUBMISSION
// ─────────────────────────────────────────────────────────
async function submitSlotAttempt(exId, userAns, inputs = []) {
  if (!currentUser) {
    showToast('Not logged in.');
    return;
  }
  const m = exId.match(/^u(\d+)q(\d+)$/);
  if (!m) return;
  const unit = parseInt(m[1], 10);
  const slotNumber = parseInt(m[2], 10);

  const session = activeMCSessions[unit];
  if (!session || !session.session_id) {
    showToast('⚠️ No active session found. Please reload this unit.');
    return;
  }

  const card = document.getElementById(exId);
  const checkBtn = card ? card.querySelector('.check-btn') : null;
  if (checkBtn && checkBtn.disabled) return;

  if (checkBtn) {
    checkBtn.disabled = true;
    checkBtn.textContent = 'Checking...';
  }

  const res = await apiPost('/api/sessions/mc/attempt', {
    session_id: session.session_id,
    slot_number: slotNumber,
    answer: userAns
  });

  if (!res) {
    if (checkBtn) {
      checkBtn.disabled = false;
      checkBtn.textContent = '✅ Check Answer';
    }
    showToast('⚠️ Connection error. Please try again.');
    return;
  }

  if (res.error) {
    if (checkBtn) {
      checkBtn.disabled = false;
      checkBtn.textContent = '✅ Check Answer';
    }
    showToast('⚠️ ' + res.error);
    return;
  }

  const isCorrect = res.is_correct;
  const state = getExState(exId);
  state.checked = true;
  state.correct = isCorrect;
  state.selected = userAns;

  if (card) {
    unlockHint(card);

    card.querySelectorAll('.step-btn').forEach(btn => {
      btn.classList.add('locked');
      if (btn.classList.contains('selected')) {
        btn.classList.add(isCorrect ? 'correct' : 'incorrect');
      }
    });

    card.querySelectorAll('.tf-btn').forEach(btn => {
      btn.classList.add('locked');
      if (btn.classList.contains('selected')) {
        btn.classList.add(isCorrect ? 'correct' : 'incorrect');
      }
    });

    card.querySelectorAll('.radio-btn').forEach(btn => {
      btn.classList.add('locked');
      if (btn.classList.contains('selected')) {
        btn.classList.add(isCorrect ? 'correct' : 'incorrect');
      }
    });
    card.querySelectorAll('input[type="radio"]').forEach(inp => {
      inp.disabled = true;
    });

    const fillInputs = inputs.length ? inputs : card.querySelectorAll('.fill-input');
    fillInputs.forEach(inp => {
      inp.classList.add('locked');
      inp.readOnly = true;
      inp.classList.add(isCorrect ? 'correct' : 'incorrect');
    });

    showResult(exId, isCorrect ? 1 : 0, 1);
  }

  saveMCState();
  showToast(isCorrect ? '✅ Correct!' : '❌ Incorrect — check the hint for guidance.');
}

// ─────────────────────────────────────────────────────────
// CARD CHECK FUNCTIONS (Zero client answer grading)
// ─────────────────────────────────────────────────────────
async function checkFTM(exId, correctIdx) {
  const state = getExState(exId);
  if (state.checked) return;
  if (state.selected === null || state.selected === undefined) {
    showToast('Please select a step first!');
    return;
  }
  await submitSlotAttempt(exId, state.selected);
}

async function checkTF(exId, correctAnswer) {
  const state = getExState(exId);
  if (state.checked) return;
  if (!state.selected) {
    showToast('Please select True or False first!');
    return;
  }
  await submitSlotAttempt(exId, state.selected);
}

async function checkRadio(exId, correctAnswer) {
  const state = getExState(exId);
  if (state.checked) return;
  if (!state.selected) {
    showToast('Please select an option first!');
    return;
  }
  await submitSlotAttempt(exId, state.selected);
}

async function checkFill(exId, inputIds) {
  const state = getExState(exId);
  if (state.checked) return;
  const card = document.getElementById(exId);
  const inputs = (inputIds || []).map(id => document.getElementById(id)).filter(Boolean);
  if (!inputs.length && card) {
    card.querySelectorAll('.fill-input').forEach(inp => inputs.push(inp));
  }
  const vals = inputs.map(inp => inp.value.trim());
  if (vals.some(v => v === '')) {
    showToast('Please fill in all blanks before checking!');
    return;
  }
  const answerPayload = vals.length === 1 ? vals[0] : vals;
  await submitSlotAttempt(exId, answerPayload, inputs);
}

function showResult(exId, correct, total) {
  const el = document.getElementById(exId + '-result');
  if (!el) return;
  const pct = (correct / total) * 100;
  let cls, msg;
  if (pct === 100) { cls = 'result-correct'; msg = '✅ Perfect! ' + correct + '/' + total + ' correct.'; }
  else if (pct >= 50) { cls = 'result-partial'; msg = '⚠️ ' + correct + '/' + total + ' correct — review the hint!'; }
  else { cls = 'result-wrong'; msg = '❌ ' + correct + '/' + total + ' correct — check the hint for guidance.'; }
  el.innerHTML = '<div class="result-row ' + cls + '">' + msg + '</div>';
}

// ─────────────────────────────────────────────────────────
// SELECTION HANDLERS
// ─────────────────────────────────────────────────────────
function selectStep(btn, exId, idx) {
  if (getExState(exId).checked) return;
  document.getElementById(exId).querySelectorAll('.step-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  getExState(exId).selected = idx;
  saveMCState();
}

function selectTF(btn, exId, val) {
  if (getExState(exId).checked) return;
  document.getElementById(exId).querySelectorAll('.tf-btn').forEach(b => {
    b.classList.remove('selected');
    b.dataset.val = b.textContent.includes('True') ? 'true' : 'false';
  });
  btn.classList.add('selected');
  btn.dataset.val = val;
  getExState(exId).selected = val;
  saveMCState();
}

function selectRadio(btn, exId, val) {
  if (getExState(exId).checked) return;
  const card = document.getElementById(exId);
  card.querySelectorAll('.radio-btn').forEach(b => {
    b.classList.remove('selected');
    if (!b.dataset.val && b.getAttribute('data-val')) {
      b.dataset.val = b.getAttribute('data-val');
    }
  });
  btn.classList.add('selected');
  btn.dataset.val = val;
  getExState(exId).selected = val;
  saveMCState();
}

// ─────────────────────────────────────────────────────────
// HINT & TIP TOGGLES
// ─────────────────────────────────────────────────────────
function unlockHint(card) {
  const hintBtn = card.querySelector('.hint-btn');
  if (hintBtn) {
    hintBtn.disabled = false;
    hintBtn.textContent = '💡 Show hint';
    hintBtn.title = '';
  }
}

function toggleHint(btn) {
  if (btn.disabled) return;
  const box = btn.nextElementSibling;
  if (box && box.classList.contains('hint-reveal')) {
    box.classList.toggle('visible');
    btn.textContent = box.classList.contains('visible') ? 'Hide hint' : 'Show hint';
  }
}

function toggleTip(btn) {
  const tipBox = btn.nextElementSibling;
  if (tipBox && tipBox.classList.contains('tip-box')) {
    tipBox.classList.toggle('visible');
    btn.textContent = tipBox.classList.contains('visible') ? '💡 Hide Tip' : '💡 Show Tip';
  }
}

function initTipsAndHints() {
  document.querySelectorAll('.hint-btn').forEach(btn => {
    btn.disabled = true;
    btn.textContent = '🔒 Hint (Check answer first)';
    btn.title = 'Attempt and check your answer to unlock the hint';
  });

  document.querySelectorAll('.tip-box').forEach(tip => {
    if (tip.previousElementSibling && tip.previousElementSibling.classList.contains('tip-toggle-btn')) {
      return;
    }
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'tip-toggle-btn';
    btn.textContent = '💡 Show Tip';
    btn.onclick = function() { toggleTip(this); };
    tip.parentNode.insertBefore(btn, tip);
  });
}

// ─────────────────────────────────────────────────────────
// UNIT SUBMISSION (Strict 15/15 Completion)
// ─────────────────────────────────────────────────────────
async function submitUnit(unitNum) {
  if (!currentUser) { showToast('Not logged in.'); return; }
  if (isSubmittingMC) return;

  const btn = document.getElementById('submit-u' + unitNum);
  if (btn && btn.disabled) return;

  const session = activeMCSessions[unitNum];
  if (!session || !session.session_id) {
    showToast('⚠️ No active session found. Please reload this unit.');
    return;
  }

  // Count answered exercises in this unit
  let answeredCount = 0;
  for (let q = 1; q <= 15; q++) {
    const s = exState['u' + unitNum + 'q' + q];
    if (s && s.checked) answeredCount++;
  }

  // Strict 100% completion requirement
  if (answeredCount < 15) {
    showToast(`⚠️ Please complete all 15 exercises before submitting! (${answeredCount}/15 completed)`);
    return;
  }

  isSubmittingMC = true;
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Saving...';
  }

  // Submit to adaptive API endpoint
  const saved = await apiPost('/api/sessions/mc/submit', {
    session_id: session.session_id,
    mood: '-'
  });

  if (saved && !saved.error && saved.score !== undefined) {
    currentUser = saved.user || currentUser;
    updateProgress(currentUser);

    const score = saved.score;
    const total = saved.total || 15;

    if (btn) {
      btn.disabled = true;
      btn.textContent = `✅ Unit ${unitNum} Submitted (${score}/${total})`;
    }

    delete activeMCSessions[unitNum];
    localStorage.removeItem(`mc_active_session_${currentUser.id}_${unitNum}`);

    showToast(`✅ Unit ${unitNum} saved! Score: ${score}/${total}`);
    showCompletionModal(unitNum, score, total);
  } else {
    if (btn) {
      btn.disabled = false;
      btn.textContent = `Submit Unit ${unitNum} & Save Score`;
    }
    const errMsg = (saved && saved.error) ? `⚠️ ${saved.error}` : 'Could not save. Please check your connection and try again.';
    showToast(errMsg);
  }
  isSubmittingMC = false;
}

// ─────────────────────────────────────────────────────────
// CANCELLATION
// ─────────────────────────────────────────────────────────
async function cancelMCSession(unitNum) {
  const session = activeMCSessions[unitNum];
  if (!session || !session.session_id) return;
  const ok = confirm(`Cancel active Unit ${unitNum} session and restart?`);
  if (!ok) return;

  showToast('Cancelling session...');
  const res = await apiPost('/api/sessions/mc/cancel', { session_id: session.session_id });
  if (res && res.error) {
    showToast('⚠️ ' + res.error);
    return;
  }
  delete activeMCSessions[unitNum];
  for (let q = 1; q <= 15; q++) {
    delete exState['u' + unitNum + 'q' + q];
  }
  showToast('Session cancelled. Restarting unit...');
  await initMCUnit(unitNum);
}

// ─────────────────────────────────────────────────────────
// COMPLETION MODAL & NAVIGATION
// ─────────────────────────────────────────────────────────
function showCompletionModal(unit, score, total) {
  lastCompletedMCUnit = unit;
  const modal = document.getElementById('completion-modal');
  if (!modal) return;
  const emoji = document.getElementById('completion-emoji');
  const title = document.getElementById('completion-title');
  const subtitle = document.getElementById('completion-subtitle');
  const badge = document.getElementById('completion-score-badge');
  const nextBtn = document.getElementById('btn-next-unit');

  if (emoji) emoji.textContent = unit === 5 ? '🏆' : '🎉';
  if (title) title.textContent = unit === 5 ? 'Workbook Complete!' : `Unit ${unit} Complete!`;
  if (subtitle) subtitle.textContent = unit === 5 ? 'All 5 units finished! Outstanding dedication.' : 'Your score has been saved to your profile.';
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
  if (lastCompletedMCUnit && lastCompletedMCUnit < 5) {
    showUnit(lastCompletedMCUnit);
  }
}

async function showUnit(idx) {
  currentMCUnitIndex = idx;
  const unitNum = idx + 1;
  document.querySelectorAll('.unit-page').forEach((p, i) => p.classList.toggle('active', i === idx));
  const colors = ['#1a56db', '#059669', '#dc2626', '#d97706', '#7c3aed'];
  document.querySelectorAll('.unit-tab').forEach((t, i) => {
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
    await initMCUnit(unitNum);
  }
}

let toastTimer;
function showToast(msg) {
  const t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 2800);
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
