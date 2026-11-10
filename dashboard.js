// ─────────────────────────────────────────────────────────
// CONFIG — update API_BASE to your Railway URL when deployed
// ─────────────────────────────────────────────────────────
const API_BASE = '';  // same-origin now that Flask serves the frontend too
const TOKEN_KEY = 'csb_token';

// ─────────────────────────────────────────────────────────
// API HELPERS
// ─────────────────────────────────────────────────────────
function getToken()  { return localStorage.getItem(TOKEN_KEY); }
function clearToken(){ localStorage.removeItem(TOKEN_KEY); }

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

// In-memory user cache populated once from API on page load
// All render functions call getUser() which returns this variable
let currentUser = null;
function getUser()   { return currentUser; }
function saveUser(u) { currentUser = u; }   // updates in-memory cache only — no localStorage

// ── NAV ──
const ALL_PAGES = ['home','report','mc-report','history'];
function showPage(id){
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.getElementById('page-'+id).classList.add('active');
  ALL_PAGES.forEach(n=>{
    const s=document.getElementById('nav-'+n);  if(s) s.classList.toggle('active',n===id);
    const m=document.getElementById('mnav-'+n); if(m) m.classList.toggle('active',n===id);
  });
  if(id==='report')         renderReportPage();
  else if(id==='mc-report') renderMCReportPage();
  else if(id==='history')   renderHistory();
  window.scrollTo(0,0);
}

function switchWbTab(tab, btn){
  document.querySelectorAll('.wb-panel').forEach(p=>p.classList.remove('active'));
  document.getElementById('wb-panel-'+tab).classList.add('active');
  btn.closest('.wb-tabs').querySelectorAll('.wb-tab').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  if(tab==='mc') btn.classList.add('mc');
}

function switchHistTab(tab, btn){
  document.getElementById('hist-panel-speed').style.display = tab==='speed' ? '' : 'none';
  document.getElementById('hist-panel-mc').style.display    = tab==='mc'    ? '' : 'none';
  btn.closest('.wb-tabs').querySelectorAll('.wb-tab').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  if(tab==='mc') renderMCHistory();
}

function doLogout(){ clearToken(); window.location.href='/login'; }

// ── INIT ──
function initDashboard(){
  const u=getUser(); if(!u) return;
  document.getElementById('sb-avatar').textContent = u.fname[0].toUpperCase();
  document.getElementById('sb-name').textContent   = u.fname+' '+u.lname;
  document.getElementById('sb-grade').textContent  = 'Grade '+u.grade+' · '+u.city;
  const hr=new Date().getHours();
  const greet=hr<12?'Good morning':hr<17?'Good afternoon':'Good evening';
  document.getElementById('home-greeting').textContent = greet+', '+u.fname+'! 👋';
  document.getElementById('home-date').textContent = new Date().toLocaleDateString('en-IN',{weekday:'long',day:'numeric',month:'long'});
  updateStreak(u);
  renderHomeStats(u);
  renderHomeProgress(u);
  renderHomeMCProgress(u);
  renderRecentSessions(u);
  renderQuickInsight(u);
}

// ── STREAK — display only; actual tracking done server-side ──
function updateStreak(u){
  const streak = u.streak || 1;
  const el  = document.getElementById('streak-text');        if(el)  el.textContent  = streak+(streak===1?' day':' days')+' streak';
  const mel = document.getElementById('mobile-streak-text'); if(mel) mel.textContent = '🔥 '+streak+'d';
  const sel = document.getElementById('sc-streak');          if(sel) sel.textContent  = streak;
  const sub = document.getElementById('sc-streak-sub');
  if(sub) sub.textContent = streak>=7?'🏆 Week streak!':streak>=3?'📈 Keep it up!':'🎯 Build your habit';
}

// ── HOME STATS ──
function renderHomeStats(u){
  const best   = u.bestScores   || [0,0,0,0,0];
  const mcBest = u.mcBestScores || [0,0,0,0,0];
  const sessions   = (u.sessions||[]).length;
  const mcSessions = (u.mcSessions||[]).length;
  const b5=best[4];
  document.getElementById('sc-best').textContent     = b5>0 ? b5+'/30' : '–';
  document.getElementById('sc-best-sub').textContent = b5>0 ? (b5>=27?'🔥 Near perfect!':b5>=21?'✅ Great work!':'📈 Keep pushing!') : 'Not attempted yet';
  document.getElementById('sc-best-sub').style.color = b5>=21?'var(--green)':b5>0?'var(--amber)':'var(--muted)';
  const mcTop=Math.max(...mcBest);
  document.getElementById('sc-mc-best').textContent     = mcTop>0 ? mcTop+'/15' : '–';
  document.getElementById('sc-mc-best-sub').textContent = mcTop>0 ? (mcTop>=13?'🔥 Excellent accuracy!':mcTop>=10?'✅ Good work!':'📈 Keep practising!') : 'Not attempted yet';
  document.getElementById('sc-mc-best-sub').style.color = mcTop>=10?'var(--green)':mcTop>0?'var(--amber)':'var(--muted)';
  document.getElementById('sc-sessions').textContent = sessions+mcSessions;
  document.getElementById('sc-sessions-sub').textContent = '⚡ '+sessions+' speed · 🔍 '+mcSessions+' MC';
}

// ── HOME SPEED PROGRESS ──
function renderHomeProgress(u){
  const best  = u.bestScores || [0,0,0,0,0];
  const units = [{name:'Unit 1',color:'#1a56db',total:20},{name:'Unit 2',color:'#7c3aed',total:20},{name:'Unit 3',color:'#059669',total:20},{name:'Unit 4',color:'#dc2626',total:20},{name:'Unit 5',color:'#d97706',total:30}];
  document.getElementById('home-progress').innerHTML = units.map((un,i)=>{
    const pct=Math.round((best[i]/un.total)*100);
    return `<div class="prog-row"><span class="prog-label">${un.name}</span><div class="prog-bar-outer"><div class="prog-bar-inner" style="width:${pct}%;background:${un.color}"></div></div><span class="prog-score">${best[i]}/${un.total}</span></div>`;
  }).join('');
}

// ── HOME MC PROGRESS ──
function renderHomeMCProgress(u){
  const best   = u.mcBestScores || [0,0,0,0,0];
  const names  = ['Fractions','Integers','Algebra','% & Decimals','Grand Challenge'];
  const colors = ['#1a56db','#059669','#dc2626','#d97706','#7c3aed'];
  document.getElementById('home-mc-progress').innerHTML = names.map((n,i)=>{
    const pct=Math.round((best[i]/15)*100);
    return `<div class="prog-row"><span class="prog-label" style="min-width:130px">${n}</span><div class="prog-bar-outer"><div class="prog-bar-inner" style="width:${pct}%;background:${colors[i]}"></div></div><span class="prog-score">${best[i]}/15</span></div>`;
  }).join('');
  const typeStats=u.mcTypeStats||{};
  const tc=document.getElementById('home-mc-types');
  const typeInfo=[{key:'findMistake',label:'Find the Mistake',icon:'🔎',color:'#1a56db'},{key:'tf',label:'True or False',icon:'✅',color:'#059669'},{key:'radio',label:'Which One is Right',icon:'🔘',color:'#7c3aed'},{key:'fill',label:'Fill the Step',icon:'✏️',color:'#d97706'}];
  const hasData=typeInfo.some(t=>typeStats[t.key]&&typeStats[t.key].a>0);
  if(!hasData){ tc.innerHTML='<div class="empty-state" style="padding:20px"><div class="empty-state-emoji" style="font-size:28px">🎯</div><div class="empty-state-title" style="font-size:13px">No data yet</div><div class="empty-state-sub" style="font-size:12px">Submit a unit to see question type performance.</div></div>'; return; }
  tc.innerHTML=typeInfo.map(t=>{
    const st=typeStats[t.key]||{a:0,c:0}, pct=st.a>0?Math.round((st.c/st.a)*100):0;
    const barColor=pct>=80?'#059669':pct>=60?'#d97706':'#dc2626';
    return `<div class="type-row"><div class="type-badge" style="background:${t.color}20;color:${t.color}">${t.icon}</div><span class="type-label">${t.label}</span><div class="type-bar-outer"><div class="type-bar-inner" style="width:${pct}%;background:${barColor}"></div></div><span class="type-score">${st.a>0?pct+'%':'–'}</span></div>`;
  }).join('');
}

// ── RECENT SPEED SESSIONS ──
function renderRecentSessions(u){
  const sessions=(u.sessions||[]).slice(-5).reverse();
  const c=document.getElementById('home-recent');
  const unitNames=['','Mental Math','Tables','Fractions','Algebra','Mixed'];
  if(!sessions.length){ c.innerHTML='<div class="empty-state" style="padding:20px"><div class="empty-state-emoji" style="font-size:28px">📅</div><div class="empty-state-title" style="font-size:13px">No sessions yet</div><div class="empty-state-sub" style="font-size:12px">Complete a Speed Booster drill.</div></div>'; return; }
  c.innerHTML='<table class="hist-table"><thead><tr><th>Date</th><th>Unit</th><th>Score</th></tr></thead><tbody>'+sessions.map(s=>{
    const pct=Math.round(s.score/s.total*100), cls=pct>=80?'score-good':pct>=55?'score-ok':'score-low';
    return `<tr><td style="font-size:12px;color:var(--muted)">${s.date}</td><td>U${s.unit} ${unitNames[s.unit]||''}</td><td><span class="score-pill ${cls}">${s.score}/${s.total}</span></td></tr>`;
  }).join('')+'</tbody></table>';
}

// ── QUICK INSIGHT ──
function renderQuickInsight(u){
  const sessions=(u.sessions||[]), mcSessions=(u.mcSessions||[]);
  const c=document.getElementById('home-quick-insight');
  const all=[...sessions.map(s=>({...s,type:'speed'})),...mcSessions.map(s=>({...s,type:'mc'}))];
  if(!all.length) return;
  const last=all[all.length-1], pct=Math.round(last.score/last.total*100);
  let msg,bg,color;
  if(pct>=90){ msg=`🔥 Outstanding! You scored <strong>${last.score}/${last.total}</strong> — top tier performance!`; bg='#f0fdf4'; color='#065f46'; }
  else if(pct>=75){ msg=`✅ Solid session! <strong>${last.score}/${last.total}</strong> — close to mastery, keep the streak going.`; bg='#eff6ff'; color='#1e40af'; }
  else if(pct>=55){ msg=`📈 Good effort! <strong>${last.score}/${last.total}</strong> — review the hint explanations and try again.`; bg='#fffbeb'; color='#92400e'; }
  else { msg=`💪 <strong>${last.score}/${last.total}</strong> — don't give up! Go back over the concept notes and worked examples.`; bg='#fff5f5'; color='#991b1b'; }
  const typeStats=u.mcTypeStats||{};
  const typeInfo=[{key:'findMistake',label:'Find the Mistake'},{key:'tf',label:'True or False'},{key:'radio',label:'Which One is Right'},{key:'fill',label:'Fill the Step'}];
  const weakType=typeInfo.map(t=>{const s=typeStats[t.key]||{a:0,c:0}; return{...t,pct:s.a>0?s.c/s.a:1};}).filter(t=>typeStats[t.key]&&typeStats[t.key].a>0).sort((a,b)=>a.pct-b.pct)[0];
  if(weakType&&weakType.pct<0.65) msg+=` Your weakest question type is <strong>${weakType.label}</strong> (${Math.round(weakType.pct*100)}% accuracy) — practise those more!`;
  c.innerHTML=`<div style="background:${bg};border-radius:10px;padding:16px;font-size:14px;font-weight:600;color:${color};line-height:1.7">${msg}</div>`;
}

// ── SPEED REPORT PAGE ──
function renderReportPage(){
  const u=getUser(); if(!u) return;
  renderUnitCards(u); renderStrengthWeakness(u); renderTrendChart(u); renderTimeStats(u);
  if((u.sessions||[]).length>0) generateAIReport();
}

function renderUnitCards(u){
  const best=u.bestScores||[0,0,0,0,0];
  const units=[{name:'Mental Math',color:'linear-gradient(135deg,#1a56db,#2563eb)',total:20},{name:'Tables',color:'linear-gradient(135deg,#7c3aed,#9333ea)',total:20},{name:'Fractions & %',color:'linear-gradient(135deg,#059669,#10b981)',total:20},{name:'Algebra',color:'linear-gradient(135deg,#dc2626,#ef4444)',total:20},{name:'Mixed',color:'linear-gradient(135deg,#f59e0b,#dc2626)',total:30}];
  document.getElementById('report-unit-cards').innerHTML=units.map((un,i)=>{
    const pct=best[i]>0?Math.round((best[i]/un.total)*100):0;
    const pctColor=pct>=80?'#059669':pct>=60?'#d97706':pct>0?'#dc2626':'#94a3b8';
    return `<div class="unit-detail-card"><div class="udc-num" style="background:${un.color}">${i+1}</div><div class="udc-score">${best[i]>0?best[i]+'/'+un.total:'–'}</div><div class="udc-label">${un.name}</div><div class="udc-bar-outer"><div class="udc-bar-inner" style="width:${pct}%;background:${un.color}"></div></div><div class="udc-pct" style="color:${pctColor}">${pct>0?pct+'%':'Not done'}</div></div>`;
  }).join('');
}

function renderStrengthWeakness(u){
  const best=u.bestScores||[0,0,0,0,0];
  const topics=[{name:'Mental Math',pct:best[0]/20},{name:'Multiplication Tables',pct:best[1]/20},{name:'Fractions & Decimals',pct:best[2]/20},{name:'Algebra',pct:best[3]/20},{name:'Mixed Challenge',pct:best[4]/30}].filter(t=>t.pct>0).sort((a,b)=>b.pct-a.pct);
  const sc=document.getElementById('strength-chips'), wc=document.getElementById('weakness-chips');
  if(!topics.length){ sc.innerHTML='<span class="chip-muted">Complete sessions to see strengths</span>'; wc.innerHTML='<span class="chip-muted">Complete sessions to see weaknesses</span>'; return; }
  sc.innerHTML=topics.filter(t=>t.pct>=0.70).map(t=>`<span class="chip-green">✅ ${t.name} (${Math.round(t.pct*100)}%)</span>`).join('')||'<span class="chip-muted">Keep practising to unlock strengths!</span>';
  wc.innerHTML=topics.filter(t=>t.pct<0.65).map(t=>`<span class="chip-red">⚠️ ${t.name} (${Math.round(t.pct*100)}%)</span>`).join('')||'<span class="chip-green">🎉 No major weaknesses!</span>';
}

function renderTrendChart(u){
  const sessions=(u.sessions||[]).slice(-8);
  const empty=document.getElementById('trend-empty'), chartArea=document.getElementById('trend-chart-area');
  if(!sessions.length){ empty.style.display='block'; chartArea.style.display='none'; return; }
  empty.style.display='none'; chartArea.style.display='block';
  const colors=['#1a56db','#7c3aed','#059669','#dc2626','#d97706'];
  document.getElementById('trend-chart').innerHTML=sessions.map(s=>{
    const pct=s.score/s.total, h=Math.max(6,Math.round(pct*110)), col=colors[(s.unit-1)%5];
    return `<div class="chart-col"><span class="chart-val">${s.score}</span><div class="chart-bar" style="height:${h}px;background:${col}" data-tip="U${s.unit}: ${s.score}/${s.total} (${Math.round(pct*100)}%)"></div></div>`;
  }).join('');
  document.getElementById('trend-labels').innerHTML=sessions.map(s=>`<span class="chart-label">${s.date?s.date.split(' ').slice(0,2).join(' '):'U'+s.unit}</span>`).join('');
}

function renderTimeStats(u){
  const sessions=u.sessions||[];
  document.getElementById('stat-total-sessions').textContent=sessions.length;
  document.getElementById('stat-streak').textContent=u.streak||0;
  const best=u.bestScores||[0,0,0,0,0], totals=[20,20,20,20,30];
  const pcts=best.map((s,i)=>s>0?Math.round(s/totals[i]*100):0).filter(p=>p>0);
  document.getElementById('stat-best-pct').textContent=pcts.length?Math.max(...pcts)+'%':'–';
}

// ── MC REPORT PAGE ──
function renderMCReportPage(){
  const u=getUser(); if(!u) return;
  renderMCUnitCards(u); renderMCTypeBreakdown(u); renderMCRecommendations(u); renderMCTrendChart(u); renderMCStrengthWeakness(u);
  if((u.mcSessions||[]).length>0) generateMCAIReport();
}

function renderMCUnitCards(u){
  const best=u.mcBestScores||[0,0,0,0,0];
  const units=[{name:'Fractions',color:'linear-gradient(135deg,#1a56db,#2563eb)'},{name:'Integers',color:'linear-gradient(135deg,#059669,#10b981)'},{name:'Algebra',color:'linear-gradient(135deg,#dc2626,#ef4444)'},{name:'% & Decimals',color:'linear-gradient(135deg,#d97706,#f59e0b)'},{name:'Grand Challenge',color:'linear-gradient(135deg,#7c3aed,#1a56db)'}];
  document.getElementById('mc-unit-cards').innerHTML=units.map((un,i)=>{
    const pct=best[i]>0?Math.round((best[i]/15)*100):0;
    const pctColor=pct>=80?'#059669':pct>=60?'#d97706':pct>0?'#dc2626':'#94a3b8';
    return `<div class="unit-detail-card"><div class="udc-num" style="background:${un.color}">${i+1}</div><div class="udc-score">${best[i]>0?best[i]+'/15':'–'}</div><div class="udc-label">${un.name}</div><div class="udc-bar-outer"><div class="udc-bar-inner" style="width:${pct}%;background:${un.color}"></div></div><div class="udc-pct" style="color:${pctColor}">${pct>0?pct+'%':'Not done'}</div></div>`;
  }).join('');
}

function renderMCTypeBreakdown(u){
  const typeStats=u.mcTypeStats||{};
  const c=document.getElementById('mc-type-breakdown');
  const typeInfo=[{key:'findMistake',label:'Find the Mistake',icon:'🔎',color:'#1a56db'},{key:'tf',label:'True or False',icon:'✅',color:'#059669'},{key:'radio',label:'Which One is Right',icon:'🔘',color:'#7c3aed'},{key:'fill',label:'Fill the Step / Fix & Solve',icon:'✏️',color:'#d97706'}];
  const hasData=typeInfo.some(t=>typeStats[t.key]&&typeStats[t.key].a>0);
  if(!hasData){ c.innerHTML='<div class="empty-state" style="padding:20px"><div class="empty-state-emoji" style="font-size:28px">🎯</div><div class="empty-state-title" style="font-size:13px">No data yet</div><div class="empty-state-sub" style="font-size:12px">Submit units to see your breakdown.</div></div>'; return; }
  c.innerHTML=typeInfo.map(t=>{
    const st=typeStats[t.key]||{a:0,c:0}, pct=st.a>0?Math.round((st.c/st.a)*100):0;
    const barColor=pct>=80?'#059669':pct>=60?'#d97706':'#dc2626';
    return `<div class="type-row"><div class="type-badge" style="background:${t.color}20;color:${t.color};font-size:16px">${t.icon}</div><span class="type-label">${t.label}</span><div class="type-bar-outer"><div class="type-bar-inner" style="width:${pct}%;background:${barColor}"></div></div><span class="type-score">${st.a>0?pct+'%':'–'}</span></div>`;
  }).join('');
}

function renderMCRecommendations(u){
  const typeStats=u.mcTypeStats||{};
  const c=document.getElementById('mc-recommendations');
  const typeInfo=[{key:'findMistake',label:'Find the Mistake',tip:'Slow down and check every single step one by one before deciding.'},{key:'tf',label:'True or False',tip:'Always verify by substituting a test value or working the problem yourself.'},{key:'radio',label:'Which One is Right',tip:'Work both solutions yourself independently, then compare to each option.'},{key:'fill',label:'Fill the Step / Fix & Solve',tip:'Write full working on rough paper first, then fill blanks — never guess.'}];
  const ranked=typeInfo.map(t=>{const st=typeStats[t.key]||{a:0,c:0}; return{...t,pct:st.a>0?st.c/st.a:1,attempted:st.a>0};}).filter(t=>t.attempted).sort((a,b)=>a.pct-b.pct);
  if(!ranked.length){ c.innerHTML='<div class="empty-state" style="padding:20px"><div class="empty-state-emoji" style="font-size:28px">💡</div><div class="empty-state-title" style="font-size:13px">Complete some exercises first</div><div class="empty-state-sub" style="font-size:12px">Your recommendations will appear here.</div></div>'; return; }
  c.innerHTML=ranked.map((t,i)=>{
    const bg=i===0?'#fff5f5':i===1?'#fffbeb':'#f0fdf4', border=i===0?'#fecaca':i===1?'#fde68a':'#bbf7d0', label=i===0?'🔴 Focus Here':i===1?'🟡 Needs Practice':'🟢 Looking Good';
    return `<div style="background:${bg};border:1.5px solid ${border};border-radius:10px;padding:12px 14px;margin-bottom:10px"><div style="font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;color:var(--muted)">${label} · ${Math.round(t.pct*100)}% accuracy</div><div style="font-size:14px;font-weight:800;color:var(--text);margin-bottom:6px">${t.label}</div><div style="font-size:13px;font-weight:600;color:var(--muted);line-height:1.6">💡 ${t.tip}</div></div>`;
  }).join('');
}

function renderMCTrendChart(u){
  const sessions=(u.mcSessions||[]).slice(-8);
  const empty=document.getElementById('mc-trend-empty'), chartArea=document.getElementById('mc-trend-chart-area');
  if(!sessions.length){ empty.style.display='block'; chartArea.style.display='none'; return; }
  empty.style.display='none'; chartArea.style.display='block';
  const colors=['#1a56db','#059669','#dc2626','#d97706','#7c3aed'];
  document.getElementById('mc-trend-chart').innerHTML=sessions.map(s=>{
    const pct=s.score/s.total, h=Math.max(6,Math.round(pct*110)), col=colors[(s.unit-1)%5];
    return `<div class="chart-col"><span class="chart-val">${s.score}</span><div class="chart-bar" style="height:${h}px;background:${col}" data-tip="U${s.unit}: ${s.score}/${s.total} (${Math.round(pct*100)}%)"></div></div>`;
  }).join('');
  document.getElementById('mc-trend-labels').innerHTML=sessions.map(s=>`<span class="chart-label">${s.date?s.date.split(' ').slice(0,2).join(' '):'U'+s.unit}</span>`).join('');
}

function renderMCStrengthWeakness(u){
  const best=u.mcBestScores||[0,0,0,0,0];
  const topics=[{name:'Fractions',pct:best[0]/15},{name:'Integers',pct:best[1]/15},{name:'Algebra',pct:best[2]/15},{name:'Percentages & Decimals',pct:best[3]/15},{name:'Grand Challenge',pct:best[4]/15}].filter(t=>t.pct>0).sort((a,b)=>b.pct-a.pct);
  const sc=document.getElementById('mc-strength-chips'), wc=document.getElementById('mc-weakness-chips');
  if(!topics.length){ sc.innerHTML='<span class="chip-muted">Complete sessions to see strengths</span>'; wc.innerHTML='<span class="chip-muted">Complete sessions to see weaknesses</span>'; return; }
  sc.innerHTML=topics.filter(t=>t.pct>=0.70).map(t=>`<span class="chip-purple">✅ ${t.name} (${Math.round(t.pct*100)}%)</span>`).join('')||'<span class="chip-muted">Keep practising!</span>';
  wc.innerHTML=topics.filter(t=>t.pct<0.65).map(t=>`<span class="chip-red">⚠️ ${t.name} (${Math.round(t.pct*100)}%)</span>`).join('')||'<span class="chip-green">🎉 No major weaknesses!</span>';
}

// ── AI REPORTS — backend proxy; API key never touches the browser ──
let aiReportRunning=false;
async function generateAIReport(){
  if(aiReportRunning) return;
  const u=getUser(); if(!u) return;
  const el=document.getElementById('ai-report-content'), btn=document.getElementById('refresh-ai-btn');
  if(!(u.sessions||[]).length){ el.innerHTML='<div class="empty-state"><div class="empty-state-emoji">🧠</div><div class="empty-state-title">No data yet</div><div class="empty-state-sub">Complete Speed Booster sessions first.</div></div>'; return; }
  aiReportRunning=true;
  if(btn){ btn.disabled=true; btn.textContent='⏳ Analysing...'; }
  el.innerHTML='<div style="padding:16px 0"><div class="ai-loading"><div class="ai-dot"></div><div class="ai-dot"></div><div class="ai-dot"></div><span style="margin-left:6px">Analysing your performance patterns...</span></div></div>';
  const data=await apiPost('/api/ai/csb-report');
  if(data&&data.report){
    el.innerHTML=parseAISections(data.report,[
      {key:'📊 Overall Performance Summary',bg:'#eff6ff',border:'#bfdbfe',tc:'#1e40af',cc:'#1e3a8a'},
      {key:"💪 What You're Good At",bg:'#f0fdf4',border:'#bbf7d0',tc:'#065f46',cc:'#14532d'},
      {key:'⚠️ Areas to Focus On',bg:'#fffbeb',border:'#fde68a',tc:'#92400e',cc:'#78350f'},
      {key:'🎯 This Week\'s Action Plan',bg:'#faf5ff',border:'#ddd6fe',tc:'#6b21a8',cc:'#4c1d95'},
    ])+'<div style="text-align:right;font-size:11px;font-weight:700;color:var(--muted);margin-top:8px">Generated: '+new Date().toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit'})+' · '+new Date().toLocaleDateString('en-IN',{day:'numeric',month:'short'})+'</div>';
  } else {
    el.innerHTML='<div class="ai-section-box" style="background:#fff5f5;border-color:#fecaca"><div class="ai-section-title" style="color:#991b1b">⚠️ Could not load AI analysis</div><div class="ai-content" style="color:#7f1d1d">Please check your connection and try again.</div></div>';
  }
  aiReportRunning=false;
  if(btn){ btn.disabled=false; btn.textContent='🧠 Refresh AI Analysis'; }
}

let mcAiRunning=false;
async function generateMCAIReport(){
  if(mcAiRunning) return;
  const u=getUser(); if(!u) return;
  const el=document.getElementById('mc-ai-report-content'), btn=document.getElementById('refresh-mc-ai-btn');
  if(!(u.mcSessions||[]).length){ el.innerHTML='<div class="empty-state"><div class="empty-state-emoji">🔍</div><div class="empty-state-title">No data yet</div><div class="empty-state-sub">Complete MC sessions first.</div></div>'; return; }
  mcAiRunning=true;
  if(btn){ btn.disabled=true; btn.textContent='⏳ Analysing...'; }
  el.innerHTML='<div style="padding:16px 0"><div class="ai-loading"><div class="ai-dot"></div><div class="ai-dot"></div><div class="ai-dot"></div><span style="margin-left:6px">Analysing your mistake patterns...</span></div></div>';
  const data=await apiPost('/api/ai/mc-report');
  if(data&&data.report){
    el.innerHTML=parseAISections(data.report,[
      {key:'🔍 Error Pattern Summary',bg:'#f5f3ff',border:'#ddd6fe',tc:'#6b21a8',cc:'#4c1d95'},
      {key:'💪 What You Understand Well',bg:'#f0fdf4',border:'#bbf7d0',tc:'#065f46',cc:'#14532d'},
      {key:'⚠️ Recurring Mistake Types',bg:'#fffbeb',border:'#fde68a',tc:'#92400e',cc:'#78350f'},
      {key:'🎯 Targeted Practice Plan',bg:'#eff6ff',border:'#bfdbfe',tc:'#1e40af',cc:'#1e3a8a'},
    ])+'<div style="text-align:right;font-size:11px;font-weight:700;color:var(--muted);margin-top:8px">Generated: '+new Date().toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit'})+' · '+new Date().toLocaleDateString('en-IN',{day:'numeric',month:'short'})+'</div>';
  } else {
    el.innerHTML='<div class="ai-section-box" style="background:#fff5f5;border-color:#fecaca"><div class="ai-section-title" style="color:#991b1b">⚠️ Could not load AI analysis</div><div class="ai-content" style="color:#7f1d1d">Please check your connection and try again.</div></div>';
  }
  mcAiRunning=false;
  if(btn){ btn.disabled=false; btn.textContent='🧠 Refresh AI Analysis'; }
}

function parseAISections(text,sections){
  let html='';
  sections.forEach((sec,i)=>{
    const nextKey=sections[i+1]?sections[i+1].key:null;
    let start=text.indexOf(sec.key);
    if(start===-1) return;
    start+=sec.key.length;
    const end=nextKey?text.indexOf(nextKey):text.length;
    if(end<=start) return;
    const content=text.slice(start,end).trim().replace(/\n\n/g,'</p><p>').replace(/\n/g,'<br>');
    html+=`<div class="ai-section-box" style="background:${sec.bg};border-color:${sec.border}"><div class="ai-section-title" style="color:${sec.tc}">${sec.key}</div><div class="ai-content" style="color:${sec.cc}"><p>${content}</p></div></div>`;
  });
  if(!html) html='<div class="ai-section-box" style="background:#f8faff;border-color:#e2e8f0"><div class="ai-content" style="color:var(--text)">'+text.replace(/\n/g,'<br>')+'</div></div>';
  return html;
}

// ── HISTORY ──
function renderHistory(){
  const u=getUser();
  const sessions=(u?.sessions||[]).slice().reverse();
  const c=document.getElementById('history-content'), countEl=document.getElementById('history-count');
  if(countEl) countEl.textContent=sessions.length+' session'+(sessions.length!==1?'s':'');
  if(!sessions.length){ c.innerHTML='<div class="empty-state"><div class="empty-state-emoji">📅</div><div class="empty-state-title">No sessions yet</div><div class="empty-state-sub">Complete Speed Booster drills and check your answers.</div></div>'; return; }
  const unitNames=['','Mental Math','Multiplication Tables','Fractions & %','Algebra','Mixed Challenge'];
  const unitColors=['','#1a56db','#7c3aed','#059669','#dc2626','#d97706'];
  c.innerHTML='<div style="overflow-x:auto"><table class="hist-table" style="min-width:500px"><thead><tr><th>#</th><th>Date</th><th>Unit</th><th>Score</th><th>%</th><th>Mood</th></tr></thead><tbody>'+sessions.map((s,i)=>{
    const pct=Math.round(s.score/s.total*100), cls=pct>=80?'score-good':pct>=55?'score-ok':'score-low', col=unitColors[s.unit]||'#64748b';
    return `<tr><td style="color:var(--muted);font-size:12px">${sessions.length-i}</td><td style="font-size:12px">${s.date||'–'}</td><td><span style="display:inline-flex;align-items:center;gap:6px"><span style="width:8px;height:8px;border-radius:50%;background:${col};flex-shrink:0"></span>Unit ${s.unit} — <span style="color:${col};font-weight:800">${unitNames[s.unit]||''}</span></span></td><td><span class="score-pill ${cls}">${s.score}/${s.total}</span></td><td><span class="score-pill ${cls}">${pct}%</span></td><td style="font-size:14px">${s.mood||'–'}</td></tr>`;
  }).join('')+'</tbody></table></div>';
}

function renderMCHistory(){
  const u=getUser();
  const sessions=(u?.mcSessions||[]).slice().reverse();
  const c=document.getElementById('mc-history-content'), countEl=document.getElementById('mc-history-count');
  if(countEl) countEl.textContent=sessions.length+' session'+(sessions.length!==1?'s':'');
  const unitNames=['','Fractions','Integers','Algebra','% & Decimals','Grand Challenge'];
  const unitColors=['','#1a56db','#059669','#dc2626','#d97706','#7c3aed'];
  if(!sessions.length){ c.innerHTML='<div class="empty-state"><div class="empty-state-emoji">🔍</div><div class="empty-state-title">No MC sessions yet</div><div class="empty-state-sub">Submit a unit in the Mistake Correction workbook.</div></div>'; return; }
  c.innerHTML='<div style="overflow-x:auto"><table class="hist-table" style="min-width:500px"><thead><tr><th>#</th><th>Date</th><th>Unit</th><th>Score</th><th>%</th></tr></thead><tbody>'+sessions.map((s,i)=>{
    const pct=Math.round(s.score/s.total*100), cls=pct>=80?'score-good':pct>=55?'score-ok':'score-low', col=unitColors[s.unit]||'#64748b';
    return `<tr><td style="color:var(--muted);font-size:12px">${sessions.length-i}</td><td style="font-size:12px">${s.date||'–'}</td><td><span style="display:inline-flex;align-items:center;gap:6px"><span style="width:8px;height:8px;border-radius:50%;background:${col};flex-shrink:0"></span>Unit ${s.unit} — <span style="color:${col};font-weight:800">${unitNames[s.unit]||''}</span></span></td><td><span class="score-pill ${cls}">${s.score}/${s.total}</span></td><td><span class="score-pill ${cls}">${pct}%</span></td></tr>`;
  }).join('')+'</tbody></table></div>';
}

// ── TOAST ──
let toastTimer;
function showToast(msg){
  const t=document.getElementById('toast');
  t.textContent=msg; t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer=setTimeout(()=>t.classList.remove('show'),2800);
}

// ── INIT — fetch user from API on every page load ──
window.addEventListener('load', async () => {
  const token = getToken();
  if(!token){ window.location.href='/login'; return; }

  currentUser = await apiGet('/api/user');
  if(!currentUser || currentUser.error){
    clearToken();
    window.location.href='/login';
    return;
  }

  initDashboard();
});
