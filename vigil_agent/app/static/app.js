// ============================================================
// Vigil Summit — Landing Page JS
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


// ── Spots Counter ──────────────────────────────────────────
let spotsData = null;

async function loadSpots() {
  try {
    const res = await fetch('/api/v1/leads/spots');
    if (!res.ok) return;
    spotsData = await res.json();
    renderSpots(spotsData);
  } catch (_) {
    // silently fail — spots counter is non-critical
  }
}

function renderSpots(data) {
  const { capacity, remaining, registered } = data;
  const pct = Math.min(100, (registered / capacity) * 100);
  const urgency = remaining <= 20 ? 'urgent' : remaining <= 50 ? 'warning' : '';

  // Hero
  const heroSpotsText = document.getElementById('hero-spots-text');
  const heroStatVagas = document.getElementById('hero-stat-vagas');
  if (heroSpotsText) heroSpotsText.textContent = `${remaining} Vagas Restantes`;
  if (heroStatVagas) {
    heroStatVagas.textContent = remaining;
    if (urgency === 'urgent') heroStatVagas.style.color = '#ef4444';
    else if (urgency === 'warning') heroStatVagas.style.color = '#f59e0b';
  }

  // Bar
  const fill = document.getElementById('spots-bar-fill');
  const remainingLabel = document.getElementById('spots-remaining-label');
  const totalLabel = document.getElementById('spots-total-label');

  if (fill) {
    fill.style.width = `${pct}%`;
    fill.className = `spots-bar-fill ${urgency}`;
  }
  if (remainingLabel) {
    if (remaining === 0) {
      remainingLabel.textContent = 'Inscrições encerradas';
      remainingLabel.style.color = '#ef4444';
    } else {
      remainingLabel.textContent = `${remaining} vaga${remaining === 1 ? '' : 's'} restante${remaining === 1 ? '' : 's'}`;
      if (urgency === 'urgent') remainingLabel.style.color = '#ef4444';
      else if (urgency === 'warning') remainingLabel.style.color = '#f59e0b';
    }
  }
  if (totalLabel) {
    totalLabel.textContent = `${registered} de ${capacity} inscritos`;
  }

  // Disable submit if full
  const submitBtn = document.getElementById('submit-btn');
  if (submitBtn && remaining === 0) {
    submitBtn.disabled = true;
    const st = submitBtn.querySelector('.submit-text');
    if (st) st.textContent = 'Vagas Esgotadas';
  }
}

loadSpots();
setInterval(loadSpots, 30000);


// ── LinkedIn / Manual Toggle ───────────────────────────────
// LinkedIn: user fills only Name, Email, WhatsApp + LinkedIn username
// Manual: user fills all fields (Name, Email, WhatsApp, Role, Company, Size, Sector)
let profileMode = 'linkedin';

const linkedinYesBtn = document.getElementById('linkedin-yes-btn');
const linkedinNoBtn = document.getElementById('linkedin-no-btn');
const linkedinSection = document.getElementById('linkedin-section');
const manualSection = document.getElementById('manual-section');

function setProfileMode(mode) {
  profileMode = mode;
  if (mode === 'linkedin') {
    linkedinYesBtn.classList.add('active');
    linkedinNoBtn.classList.remove('active');
    linkedinSection.hidden = false;
    manualSection.hidden = true;
  } else {
    linkedinNoBtn.classList.add('active');
    linkedinYesBtn.classList.remove('active');
    linkedinSection.hidden = true;
    manualSection.hidden = false;
  }
}

linkedinYesBtn?.addEventListener('click', () => setProfileMode('linkedin'));
linkedinNoBtn?.addEventListener('click', () => setProfileMode('manual'));


// ── Companion Toggle ───────────────────────────────────────
const companionSection = document.getElementById('companion-section');

document.getElementById('companion-no')?.addEventListener('click', function () {
  this.classList.add('active');
  document.getElementById('companion-yes').classList.remove('active');
  document.getElementById('with_companion').value = 'false';
  if (companionSection) companionSection.hidden = true;
  // Limpa erros ao esconder
  clearFieldError('companion_email', 'companion-email-error');
  clearFieldError('companion_relationship', 'companion-relationship-error');
});

document.getElementById('companion-yes')?.addEventListener('click', function () {
  this.classList.add('active');
  document.getElementById('companion-no').classList.remove('active');
  document.getElementById('with_companion').value = 'true';
  if (companionSection) companionSection.hidden = false;
});


// ── Field Error Helpers ────────────────────────────────────
function setFieldError(fieldId, errorId, message) {
  const field = document.getElementById(fieldId);
  const errorEl = document.getElementById(errorId);
  if (field) field.classList.add('field-invalid');
  if (errorEl) errorEl.textContent = message;
}

function clearFieldError(fieldId, errorId) {
  const field = document.getElementById(fieldId);
  const errorEl = document.getElementById(errorId);
  if (field) field.classList.remove('field-invalid');
  if (errorEl) errorEl.textContent = '';
}


// ── Form Validation ────────────────────────────────────────
function validateForm() {
  let valid = true;

  // Nome — sempre obrigatório
  clearFieldError('name', 'name-error');
  const name = document.getElementById('name').value.trim();
  if (!name || name.length < 2) {
    setFieldError('name', 'name-error', 'Por favor, informe seu nome completo.');
    valid = false;
  }

  // Email — sempre obrigatório
  clearFieldError('email', 'email-error');
  const email = document.getElementById('email').value.trim();
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    setFieldError('email', 'email-error', 'Informe um email válido.');
    valid = false;
  }

  // WhatsApp — sempre obrigatório
  clearFieldError('phone', 'phone-error');
  const phone = document.getElementById('phone').value.trim();
  const phoneDigits = phone.replace(/\D/g, '');
  if (phoneDigits.length < 10) {
    setFieldError('phone', 'phone-error', 'Informe o WhatsApp com DDD (ex.: 11 99999-9999).');
    valid = false;
  }

  if (profileMode === 'linkedin') {
    // Modo LinkedIn: somente username obrigatório
    clearFieldError('linkedin_username', 'linkedin-error');
    const username = (document.getElementById('linkedin_username')?.value || '').trim();
    if (!username || username.length < 2) {
      setFieldError('linkedin_username', 'linkedin-error', 'Informe seu usuário do LinkedIn.');
      valid = false;
    }
  } else {
    // Modo manual: Cargo e Empresa também obrigatórios
    clearFieldError('role', 'role-error');
    const role = (document.getElementById('role')?.value || '').trim();
    if (!role || role.length < 2) {
      setFieldError('role', 'role-error', 'Informe seu cargo ou função.');
      valid = false;
    }

    clearFieldError('company', 'company-error');
    const company = (document.getElementById('company')?.value || '').trim();
    if (!company || company.length < 2) {
      setFieldError('company', 'company-error', 'Informe o nome da sua empresa.');
      valid = false;
    }
  }

  // LGPD — sempre obrigatório
  const lgpd = document.getElementById('lgpd_consent');
  const lgpdError = document.getElementById('lgpd-error');
  if (!lgpd.checked) {
    if (lgpdError) lgpdError.textContent = 'O aceite da LGPD é obrigatório para participar.';
    valid = false;
  } else {
    if (lgpdError) lgpdError.textContent = '';
  }

  // Acompanhante — campos obrigatórios quando "Sim" for selecionado
  const withCompanion = document.getElementById('with_companion').value === 'true';
  if (withCompanion) {
    clearFieldError('companion_email', 'companion-email-error');
    const companionEmail = (document.getElementById('companion_email')?.value || '').trim();
    if (!companionEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(companionEmail)) {
      setFieldError('companion_email', 'companion-email-error', 'Informe um email válido para o acompanhante.');
      valid = false;
    }

    clearFieldError('companion_relationship', 'companion-relationship-error');
    const companionRel = document.getElementById('companion_relationship')?.value || '';
    if (!companionRel) {
      setFieldError('companion_relationship', 'companion-relationship-error', 'Selecione o tipo de relação com o acompanhante.');
      valid = false;
    }
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
  if (submitText) submitText.hidden = loading;
  if (submitArrow) submitArrow.hidden = loading;
  if (submitLoader) submitLoader.hidden = !loading;
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

window.resetForm = function () {
  form.hidden = false;
  document.getElementById('error-state').hidden = true;
  document.getElementById('success-state').hidden = true;
};

form?.addEventListener('submit', async (e) => {
  e.preventDefault();

  if (!validateForm()) return;

  // Verifica vagas localmente antes de bater na API
  if (spotsData && spotsData.remaining === 0) {
    showError('Vagas Esgotadas', 'Todas as 120 vagas do Vigil Summit foram preenchidas.');
    return;
  }

  // Monta payload conforme o modo ativo
  const withCompanion = document.getElementById('with_companion').value === 'true';
  const payload = {
    name: document.getElementById('name').value.trim(),
    email: document.getElementById('email').value.trim().toLowerCase(),
    phone: document.getElementById('phone').value.trim(),
    with_companion: withCompanion,
    lgpd_consent: document.getElementById('lgpd_consent').checked,
  };

  if (withCompanion) {
    payload.companion_email = (document.getElementById('companion_email')?.value || '').trim().toLowerCase();
    payload.companion_relationship = document.getElementById('companion_relationship')?.value || null;
  }

  if (profileMode === 'linkedin') {
    // Modo LinkedIn: envia somente a URL; o agente busca role, company, sector
    const username = (document.getElementById('linkedin_username')?.value || '').trim();
    if (username) payload.linkedin_url = `https://www.linkedin.com/in/${username}`;
  } else {
    // Modo manual: envia todos os campos profissionais
    payload.role = (document.getElementById('role')?.value || '').trim() || null;
    payload.company = (document.getElementById('company')?.value || '').trim() || null;
    const companySize = document.getElementById('company_size')?.value;
    const sector = document.getElementById('sector')?.value;
    if (companySize) payload.company_size = companySize;
    if (sector) payload.sector = sector;
  }

  setLoading(true);

  try {
    const res = await fetch('/api/v1/leads/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (res.ok) {
      showSuccess();
      loadSpots();
      return;
    }

    const err = await res.json().catch(() => ({}));
    if (res.status === 409) {
      showError('Email já cadastrado', err.detail || 'Esse email já está inscrito no Vigil Summit.');
    } else if (res.status === 422) {
      const detail = typeof err.detail === 'string' ? err.detail : '';
      if (detail.toLowerCase().includes('capacidade') || detail.toLowerCase().includes('encerradas')) {
        showError('Vagas Esgotadas', detail);
      } else {
        showError('Dados inválidos', 'Verifique os campos e tente novamente.');
      }
    } else {
      showError('Erro no servidor', err.detail || 'Tente novamente em alguns instantes.');
    }
  } catch (_) {
    showError('Sem conexão', 'Verifique sua internet e tente novamente.');
  } finally {
    setLoading(false);
  }
});


// ── Clear errors on typing ─────────────────────────────────
['name', 'email', 'phone'].forEach((id) => {
  document.getElementById(id)?.addEventListener('input', () => {
    clearFieldError(id, `${id}-error`);
  });
});

document.getElementById('linkedin_username')?.addEventListener('input', () => {
  clearFieldError('linkedin_username', 'linkedin-error');
});

document.getElementById('role')?.addEventListener('input', () => {
  clearFieldError('role', 'role-error');
});

document.getElementById('company')?.addEventListener('input', () => {
  clearFieldError('company', 'company-error');
});

document.getElementById('companion_email')?.addEventListener('input', () => {
  clearFieldError('companion_email', 'companion-email-error');
});

document.getElementById('companion_relationship')?.addEventListener('change', () => {
  clearFieldError('companion_relationship', 'companion-relationship-error');
});
