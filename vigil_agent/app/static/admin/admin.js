// ============================================================
// Vigil Admin — Dashboard JS
// JWT auth + calls para /api/v1/admin/*
// ============================================================

const TOKEN_KEY = 'vigil_admin_token';
const USER_KEY = 'vigil_admin_user';

// ── Auth helpers ───────────────────────────────────────────
function getToken() { return localStorage.getItem(TOKEN_KEY); }

function authHeaders() {
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${getToken()}`,
  };
}

function logout() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  window.location.href = '/admin/login.html';
}

// Verifica auth no load
(function checkAuth() {
  if (!getToken()) {
    window.location.href = '/admin/login.html';
    return;
  }
  const user = localStorage.getItem(USER_KEY) || 'admin';
  document.getElementById('admin-username').textContent = user;
})();


// ── API helpers ────────────────────────────────────────────
async function api(method, path, body = null) {
  const res = await fetch(`/api/v1${path}`, {
    method,
    headers: authHeaders(),
    body: body ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401) { logout(); return null; }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Erro ${res.status}`);
  }
  return res.status === 204 ? null : res.json();
}


// ── Toast ──────────────────────────────────────────────────
let toastTimer;
function showToast(message, type = 'success') {
  const el = document.getElementById('toast');
  el.textContent = message;
  el.className = `toast ${type}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.classList.add('hidden'); }, 3500);
}


// ── Panel Navigation ───────────────────────────────────────
function showPanel(name) {
  document.querySelectorAll('.content-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById(`panel-${name}`).classList.add('active');
  document.querySelector(`[data-panel="${name}"]`).classList.add('active');

  // Lazy load panel data
  if (name === 'overview') loadOverview();
  if (name === 'event') loadEvent();
  if (name === 'templates') loadTemplates();
  if (name === 'leads') loadLeads();
  if (name === 'scheduler') refreshScheduler();
}


// ── Overview ───────────────────────────────────────────────
async function loadOverview() {
  try {
    const [leads, event, sched] = await Promise.all([
      api('GET', '/admin/leads'),
      api('GET', '/admin/event'),
      api('GET', '/admin/scheduler/status'),
    ]);

    if (!leads) return;

    document.getElementById('stat-total').textContent = leads.length;
    document.getElementById('stat-confirmed').textContent =
      leads.filter(l => ['confirmed', 'attended'].includes(l.status)).length;
    document.getElementById('stat-attended').textContent =
      leads.filter(l => l.attended === true).length;
    document.getElementById('stat-meetings').textContent =
      leads.filter(l => l.status === 'meeting_booked').length;

    if (event) {
      const statusMap = { ACTIVE: '🟢 Ativo', ENDED: '🔴 Encerrado', DRAFT: '🟡 Rascunho', active: '🟢 Ativo', ended: '🔴 Encerrado', draft: '🟡 Rascunho' };
      document.getElementById('event-status-summary').innerHTML = `
        <strong>${event.name}</strong><br>
        ${statusMap[event.status] || event.status} &nbsp;·&nbsp;
        ${event.event_date ? `📅 ${event.event_date}` : 'Data não definida'} &nbsp;·&nbsp;
        ${event.location || 'Local a definir'}
      `;
    }

    const nextRun = sched?.post_event_next_run;
    document.getElementById('countdown-display').textContent = nextRun
      ? new Date(nextRun).toLocaleString('pt-BR')
      : 'Sem job agendado';

    if (nextRun) startCountdown(new Date(nextRun), 'countdown-timer');
  } catch (e) {
    console.error(e);
  }
}

function startCountdown(targetDate, elId) {
  const el = document.getElementById(elId);
  if (!el) return;
  const update = () => {
    const diff = targetDate - new Date();
    if (diff <= 0) { el.textContent = '⚡ Disparando...'; return; }
    const m = Math.floor(diff / 60000);
    const s = Math.floor((diff % 60000) / 1000);
    el.textContent = `${m}m ${s}s restantes`;
    setTimeout(update, 1000);
  };
  update();
}


// ── Event ──────────────────────────────────────────────────
async function loadEvent() {
  try {
    const event = await api('GET', '/admin/event');
    if (!event) return;

    document.getElementById('ev-name').value = event.name || '';
    document.getElementById('ev-status').value = event.status;
    document.getElementById('ev-date').value = event.event_date || '';
    document.getElementById('ev-time').value = event.event_time || '';
    document.getElementById('ev-location').value = event.location || '';
    document.getElementById('ev-speakers').value = (event.speakers || []).join('\n');
    document.getElementById('ev-delay').value = event.post_event_delay_minutes || 3;
    document.getElementById('delay-label').textContent = event.post_event_delay_minutes || 3;
    const infoEl = document.getElementById('delay-label-info');
    if (infoEl) infoEl.textContent = event.post_event_delay_minutes || 3;
  } catch (e) {
    showToast(`Erro ao carregar evento: ${e.message}`, 'error');
  }
}

document.getElementById('ev-delay')?.addEventListener('input', function () {
  document.getElementById('delay-label').textContent = this.value;
  const infoEl = document.getElementById('delay-label-info');
  if (infoEl) infoEl.textContent = this.value;
});

async function saveEvent() {
  try {
    const speakers = document.getElementById('ev-speakers').value
      .split('\n')
      .map(s => s.trim())
      .filter(Boolean);

    await api('PUT', '/admin/event', {
      name: document.getElementById('ev-name').value.trim(),
      event_date: document.getElementById('ev-date').value || null,
      event_time: document.getElementById('ev-time').value || null,
      location: document.getElementById('ev-location').value.trim() || null,
      speakers,
      post_event_delay_minutes: parseInt(document.getElementById('ev-delay').value) || 3,
    });

    showToast('✅ Evento atualizado com sucesso!');
  } catch (e) {
    showToast(`Erro: ${e.message}`, 'error');
  }
}

async function endEventNow() {
  const delay = document.getElementById('ev-delay')?.value || '3';
  const confirmed = confirm(
    `⚠️ VOCÊ ESTÁ PRESTES A ENCERRAR O EVENTO.\n\n` +
    `O que acontecerá ao confirmar:\n` +
    `• O evento será marcado como ENCERRADO no sistema.\n` +
    `• Após ${delay} minuto(s), emails e WhatsApp de follow-up serão enviados para TODOS os participantes inscritos.\n\n` +
    `❌ Esta ação não pode ser desfeita. Deseja continuar?`
  );
  if (!confirmed) return;
  try {
    const result = await api('POST', '/admin/event/end');
    const when = result?.post_event_scheduled_at
      ? new Date(result.post_event_scheduled_at).toLocaleString('pt-BR')
      : '?';
    showToast(`✅ Evento encerrado! Follow-up agendado para: ${when}`);
    loadEvent();
    refreshScheduler();
  } catch (e) {
    showToast(`Erro: ${e.message}`, 'error');
  }
}

async function scheduleEnd() {
  const val = document.getElementById('schedule-end-at').value;
  if (!val) { showToast('Selecione uma data e horário.', 'error'); return; }
  try {
    await api('PUT', '/admin/event/schedule-end', {
      scheduled_end_at: new Date(val).toISOString(),
    });
    showToast('✅ Encerramento agendado!');
  } catch (e) {
    showToast(`Erro: ${e.message}`, 'error');
  }
}


// ── Templates ──────────────────────────────────────────────
let allTemplates = [];

async function loadTemplates() {
  try {
    allTemplates = await api('GET', '/admin/templates') || [];
    renderTemplates(allTemplates);
  } catch (e) {
    showToast(`Erro: ${e.message}`, 'error');
  }
}

function renderTemplates(templates) {
  const listEl = document.getElementById('templates-list');
  if (!templates.length) {
    listEl.innerHTML = '<p style="color:var(--text-muted);font-size:0.88rem">Nenhum template criado.</p>';
    return;
  }

  const phaseTag = { pre_event: 'tag-pre', post_event: 'tag-post', confirmation: 'tag-confirm', reply: 'tag-pre', post_event_attended: 'tag-post', post_event_no_show: 'tag-pre' };
  const phaseLabel = { pre_event: 'Pré-evento', post_event: 'Pós-evento', confirmation: 'Confirmação', reply: 'Reply', post_event_attended: 'Pós — Presente', post_event_no_show: 'Pós — Ausente' };
  const channelTag = { email: 'tag-email', whatsapp: 'tag-whatsapp', both: 'tag-both' };
  const channelLabel = { email: 'Email', whatsapp: 'WhatsApp', both: 'Email+WA' };

  listEl.innerHTML = templates.map(t => `
    <div class="template-item">
      <div class="template-info">
        <div class="template-name">${t.name}</div>
        <div class="template-meta">
          <span class="tag ${phaseTag[t.phase]}">${phaseLabel[t.phase]}</span>
          <span class="tag ${channelTag[t.channel]}">${channelLabel[t.channel]}</span>
          ${!t.is_active ? '<span class="tag tag-inactive">Inativo</span>' : ''}
        </div>
      </div>
      <div class="template-actions">
        <button class="btn-icon" onclick="editTemplate(${t.id})" title="Editar">✏️</button>
        <button class="btn-icon" onclick="deleteTemplate(${t.id})" title="Excluir" style="color:#f87171">🗑️</button>
      </div>
    </div>
  `).join('');
}

function openTemplateModal(tpl = null) {
  document.getElementById('modal-title').textContent = tpl ? 'Editar Template' : 'Novo Template';
  document.getElementById('tpl-id').value = tpl?.id || '';
  document.getElementById('tpl-name').value = tpl?.name || '';
  document.getElementById('tpl-phase').value = tpl?.phase || 'confirmation';
  document.getElementById('tpl-channel').value = tpl?.channel || 'both';
  document.getElementById('tpl-order').value = tpl?.sequence_order || 1;
  document.getElementById('tpl-subject').value = tpl?.subject || '';
  document.getElementById('tpl-body').value = tpl?.body || '';
  document.getElementById('tpl-active').checked = tpl?.is_active !== false;
  document.getElementById('template-modal').classList.remove('hidden');
}

function closeTemplateModal() {
  document.getElementById('template-modal').classList.add('hidden');
}

function editTemplate(id) {
  const tpl = allTemplates.find(t => t.id === id);
  if (tpl) openTemplateModal(tpl);
}

async function saveTemplate() {
  const id = document.getElementById('tpl-id').value;
  const payload = {
    name: document.getElementById('tpl-name').value.trim(),
    phase: document.getElementById('tpl-phase').value,
    channel: document.getElementById('tpl-channel').value,
    sequence_order: parseInt(document.getElementById('tpl-order').value) || 1,
    subject: document.getElementById('tpl-subject').value.trim() || null,
    body: document.getElementById('tpl-body').value.trim(),
    is_active: document.getElementById('tpl-active').checked,
  };

  try {
    if (id) {
      await api('PUT', `/admin/templates/${id}`, payload);
      showToast('✅ Template atualizado!');
    } else {
      await api('POST', '/admin/templates', payload);
      showToast('✅ Template criado!');
    }
    closeTemplateModal();
    loadTemplates();
  } catch (e) {
    showToast(`Erro: ${e.message}`, 'error');
  }
}

async function deleteTemplate(id) {
  if (!confirm('Excluir este template? Essa ação não pode ser desfeita.')) return;
  try {
    await api('DELETE', `/admin/templates/${id}`);
    showToast('Template removido.');
    loadTemplates();
  } catch (e) {
    showToast(`Erro: ${e.message}`, 'error');
  }
}


// ── Leads ──────────────────────────────────────────────────
let allLeads = [];

let currentFilter = 'all';

const CONFIRMED_STATUSES = new Set(['confirmed', 'attended', 'followed_up', 'meeting_booked']);

async function loadLeads() {
  try {
    allLeads = await api('GET', '/admin/leads') || [];
    renderLeads(allLeads);
  } catch (e) {
    showToast(`Erro: ${e.message}`, 'error');
  }
}

function filterLeads(status, btn) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  currentFilter = status;

  let filtered;
  if (status === 'all') filtered = allLeads;

  else if (status === 'enriched') filtered = allLeads.filter(l => l.status === 'enriched');
  else if (status === 'confirmed') filtered = allLeads.filter(l => CONFIRMED_STATUSES.has(l.status));
  else filtered = allLeads.filter(l => l.status === status || l.funnel_phase === status);

  renderLeads(filtered);
}

function renderLeads(leads) {
  const tbody = document.getElementById('leads-tbody');
  const thead = document.getElementById('leads-thead');
  const isMeeting = currentFilter === 'meeting_booked';

  // Cabeçalho dinâmico
  if (isMeeting) {
    thead.innerHTML = `<tr>
      <th>NOME</th><th>EMAIL</th><th>EMPRESA</th><th>CARGO</th><th>STATUS</th><th>AGENDADA PARA</th><th>INSCRITO EM</th>
    </tr>`;
  } else {
    thead.innerHTML = `<tr>
      <th>NOME</th><th>EMAIL</th><th>EMPRESA</th><th>CARGO</th><th>STATUS</th><th>ACOMP.</th><th>INSCRITO EM</th>
    </tr>`;
  }

  if (!leads.length) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--text-muted)">Nenhum participante encontrado.</td></tr>`;
    return;
  }

  tbody.innerHTML = leads.map(l => {
    const col6 = isMeeting
      ? escapeHtml(l.last_contacted_at ? new Date(l.last_contacted_at).toLocaleString('pt-BR') : '—')
      : (l.with_companion ? '✅' : '—');
    return `<tr>
      <td class="lead-name">${escapeHtml(l.name)}</td>
      <td>${escapeHtml(l.email)}</td>
      <td>${escapeHtml(l.company || '—')}</td>
      <td>${escapeHtml(l.role || '—')}</td>
      <td><span class="status-badge status-${l.status}">${l.status.replace(/_/g, ' ')}</span></td>
      <td style="text-align:center">${col6}</td>
      <td>${new Date(l.created_at).toLocaleDateString('pt-BR')}</td>
    </tr>`;
  }).join('');
}

function escapeHtml(str) {
  return String(str || '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}


// ── Scheduler ──────────────────────────────────────────────
async function refreshScheduler() {
  try {
    const data = await api('GET', '/admin/scheduler/status');
    const el = document.getElementById('scheduler-next-run');
    if (!data) return;
    el.textContent = data.post_event_next_run
      ? new Date(data.post_event_next_run).toLocaleString('pt-BR')
      : 'Sem job agendado';
    if (data.post_event_next_run) startCountdown(new Date(data.post_event_next_run), 'countdown-timer');
  } catch (e) {
    console.error(e);
  }
}

async function triggerIn(minutes) {
  const label = minutes <= 1 ? '1 minuto' : `${minutes} minutos`;
  const confirmed = confirm(
    `🧪 SIMULAÇÃO DE FOLLOW-UP PÓS-EVENTO\n\n` +
    `Os emails e mensagens de follow-up serão enviados para todos os participantes em ${label}.\n\n` +
    `✅ O status do evento NÃO será alterado.\n` +
    `✅ Nenhuma configuração será modificada.\n\n` +
    `Confirma o disparo de teste?`
  );
  if (!confirmed) return;
  try {
    const result = await api('POST', '/admin/scheduler/trigger-test', { delay_minutes: minutes });
    const when = result?.scheduled_at
      ? new Date(result.scheduled_at).toLocaleString('pt-BR')
      : '?';
    showToast(`✅ Disparo de teste agendado para: ${when}`);
    refreshScheduler();
  } catch (e) {
    showToast(`Erro: ${e.message}`, 'error');
  }
}


// ── Init ───────────────────────────────────────────────────
loadOverview();
