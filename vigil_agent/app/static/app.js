// ============================================================
// Vigil Summit — Landing Page JS
// Submit do formulário + animação de estrelas
// ============================================================

// ── Stars Canvas Animation ─────────────────────────────────
const canvas = document.getElementById('stars-canvas');
const ctx = canvas.getContext('2d');

let stars = [];

function resizeCanvas() {
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
}

function createStars() {
  stars = [];
  const count = Math.floor((canvas.width * canvas.height) / 6000);
  for (let i = 0; i < count; i++) {
    stars.push({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      r: Math.random() * 1.4 + 0.2,
      alpha: Math.random() * 0.7 + 0.1,
      speed: Math.random() * 0.003 + 0.001,
      phase: Math.random() * Math.PI * 2,
      // Occasional blue/purple tint
      hue: Math.random() > 0.85 ? (Math.random() > 0.5 ? '130,180,255' : '180,130,255') : '200,220,255',
    });
  }
}

function drawStars(timestamp) {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  for (const s of stars) {
    const twinkle = s.alpha + Math.sin(timestamp * s.speed + s.phase) * 0.25;
    ctx.beginPath();
    ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(${s.hue}, ${Math.max(0, Math.min(1, twinkle))})`;
    ctx.fill();
  }
  requestAnimationFrame(drawStars);
}

resizeCanvas();
createStars();
requestAnimationFrame(drawStars);

window.addEventListener('resize', () => {
  resizeCanvas();
  createStars();
});


// ── Feature Cards Scroll Animation ────────────────────────
const observer = new IntersectionObserver(
  (entries) => {
    entries.forEach((e) => {
      if (e.isIntersecting) {
        const delay = parseInt(e.target.dataset.delay || '0');
        setTimeout(() => {
          e.target.style.opacity = '1';
          e.target.style.transform = 'translateY(0)';
        }, delay);
        observer.unobserve(e.target);
      }
    });
  },
  { threshold: 0.15 }
);

document.querySelectorAll('.feature-card').forEach((card) => {
  card.style.opacity = '0';
  card.style.transform = 'translateY(24px)';
  card.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
  observer.observe(card);
});


// ── Companion Toggle ───────────────────────────────────────
document.getElementById('companion-no')?.addEventListener('click', function() {
  this.classList.add('active');
  document.getElementById('companion-yes').classList.remove('active');
  document.getElementById('with_companion').value = 'false';
});

document.getElementById('companion-yes')?.addEventListener('click', function() {
  this.classList.add('active');
  document.getElementById('companion-no').classList.remove('active');
  document.getElementById('with_companion').value = 'true';
});


// ── Form Validation ────────────────────────────────────────
function setFieldError(fieldId, errorId, message) {
  const field = document.getElementById(fieldId);
  const errorEl = document.getElementById(errorId);
  field.classList.add('field-invalid');
  if (errorEl) errorEl.textContent = message;
}

function clearFieldError(fieldId, errorId) {
  const field = document.getElementById(fieldId);
  const errorEl = document.getElementById(errorId);
  field.classList.remove('field-invalid');
  if (errorEl) errorEl.textContent = '';
}

function validateForm(data) {
  let valid = true;

  // Nome
  clearFieldError('name', 'name-error');
  if (!data.name || data.name.trim().length < 2) {
    setFieldError('name', 'name-error', 'Por favor, informe seu nome completo.');
    valid = false;
  }

  // Email
  clearFieldError('email', 'email-error');
  if (!data.email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email)) {
    setFieldError('email', 'email-error', 'Informe um email corporativo válido.');
    valid = false;
  }

  // Phone
  clearFieldError('phone', 'phone-error');
  const phoneDigits = (data.phone || '').replace(/\D/g, '');
  if (phoneDigits.length < 10) {
    setFieldError('phone', 'phone-error', 'Informe o WhatsApp com DDD (ex.: 11 99999-9999).');
    valid = false;
  }

  // Role
  clearFieldError('role', 'role-error');
  if (!data.role || data.role.trim().length < 2) {
    setFieldError('role', 'role-error', 'Informe seu cargo ou função.');
    valid = false;
  }

  // Company
  clearFieldError('company', 'company-error');
  if (!data.company || data.company.trim().length < 2) {
    setFieldError('company', 'company-error', 'Informe o nome da sua empresa.');
    valid = false;
  }

  // LGPD
  const lgpd = document.getElementById('lgpd_consent');
  const lgpdError = document.getElementById('lgpd-error');
  if (!lgpd.checked) {
    if (lgpdError) lgpdError.textContent = 'O aceite da LGPD é obrigatório para participar.';
    valid = false;
  } else {
    if (lgpdError) lgpdError.textContent = '';
  }

  return valid;
}


// ── Form Submit ────────────────────────────────────────────
const form = document.getElementById('registration-form');
const submitBtn = document.getElementById('submit-btn');
const submitText = submitBtn?.querySelector('.submit-text');
const submitArrow = submitBtn?.querySelector('.submit-arrow');
const submitLoader = submitBtn?.querySelector('.submit-loader');

function setLoading(loading) {
  submitBtn.disabled = loading;
  submitText.hidden = loading;
  submitArrow.hidden = loading;
  submitLoader.hidden = !loading;
}

function showSuccess() {
  form.hidden = true;
  document.getElementById('success-state').hidden = false;
}

function showError(title, message) {
  form.hidden = true;
  const errorState = document.getElementById('error-state');
  errorState.hidden = false;
  document.getElementById('error-title').textContent = title;
  document.getElementById('error-message').textContent = message;
}

window.resetForm = function() {
  form.hidden = false;
  document.getElementById('error-state').hidden = true;
  document.getElementById('success-state').hidden = true;
};

form?.addEventListener('submit', async (e) => {
  e.preventDefault();

  const payload = {
    name: document.getElementById('name').value.trim(),
    email: document.getElementById('email').value.trim().toLowerCase(),
    phone: document.getElementById('phone').value.trim(),
    role: document.getElementById('role').value.trim(),
    company: document.getElementById('company').value.trim(),
    with_companion: document.getElementById('with_companion').value === 'true',
    lgpd_consent: document.getElementById('lgpd_consent').checked,
  };

  if (!validateForm(payload)) return;
  setLoading(true);

  try {
    const res = await fetch('/api/v1/leads/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (res.ok) {
      showSuccess();
      return;
    }

    const err = await res.json().catch(() => ({}));
    if (res.status === 409) {
      showError('Email já cadastrado', err.detail || 'Esse email já está inscrito no Vigil Summit.');
    } else if (res.status === 422) {
      showError('Dados inválidos', 'Verifique os campos e tente novamente.');
    } else {
      showError('Erro no servidor', err.detail || 'Tente novamente em alguns instantes.');
    }
  } catch (err) {
    showError('Sem conexão', 'Verifique sua internet e tente novamente.');
  } finally {
    setLoading(false);
  }
});

// Clear error on input
['name', 'email', 'phone', 'role', 'company'].forEach((id) => {
  document.getElementById(id)?.addEventListener('input', () => {
    clearFieldError(id, `${id}-error`);
  });
});
