// DEMO WALKTHROUGH
const STEP_DURATION = 3800;
let currentStep = 0;
let progressTimer = null;
let demoStarted = false;

function setStep(idx) {
  clearInterval(progressTimer);
  currentStep = idx;
  document.querySelectorAll('.step-btn').forEach(function(btn, i) {
    btn.classList.toggle('active', i === idx);
  });
  document.querySelectorAll('.mockup').forEach(function(m, i) {
    m.classList.toggle('active', i === idx);
  });
  document.querySelectorAll('.step-prog-fill').forEach(function(f) {
    f.style.width = '0%';
  });
  runProgress();
}

function runProgress() {
  var fill = document.getElementById('fill-' + currentStep);
  if (!fill) return;
  var elapsed = 0;
  var tick = 40;
  progressTimer = setInterval(function() {
    elapsed += tick;
    fill.style.width = Math.min((elapsed / STEP_DURATION) * 100, 100) + '%';
    if (elapsed >= STEP_DURATION) {
      clearInterval(progressTimer);
      setStep((currentStep + 1) % 5);
    }
  }, tick);
}

var demoEl = document.getElementById('demo');
if (demoEl && 'IntersectionObserver' in window) {
  new IntersectionObserver(function(entries) {
    if (entries[0].isIntersecting && !demoStarted) {
      demoStarted = true;
      runProgress();
    }
  }, { threshold: 0.25 }).observe(demoEl);
} else if (demoEl) {
  demoStarted = true;
  runProgress();
}

// FAQ ACCORDION
function toggleFaq(btn) {
  var item = btn.closest('.faq-item');
  var isOpen = item.classList.contains('open');
  document.querySelectorAll('.faq-item.open').forEach(function(el) {
    el.classList.remove('open');
  });
  if (!isOpen) item.classList.add('open');
}

// SCROLL REVEAL
(function() {
  if (!('IntersectionObserver' in window)) {
    document.querySelectorAll('.reveal').forEach(function(el) {
      el.classList.add('in');
    });
    return;
  }
  var io = new IntersectionObserver(function(entries) {
    entries.forEach(function(e) {
      if (e.isIntersecting) {
        e.target.classList.add('in');
        io.unobserve(e.target);
      }
    });
  }, { threshold: 0.08, rootMargin: '0px 0px -30px 0px' });
  document.querySelectorAll('.reveal').forEach(function(el) {
    io.observe(el);
  });
})();
