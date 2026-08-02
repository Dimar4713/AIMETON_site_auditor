const userBox = document.querySelector('#session-user');
const listBox = document.querySelector('#missions');
const form = document.querySelector('#mission-form');
const messageBox = document.querySelector('#mission-message');
const POLL_INTERVAL_MS = 15000;
const LIVE_RECORD_LIMIT = 20;
let pollTimer = null;

function csrfToken() {
  const item = document.cookie.split('; ').find((part) => part.startsWith('aimeton_csrf='));
  return item ? decodeURIComponent(item.split('=').slice(1).join('=')) : '';
}

function typedReason(payload, fallback) {
  const detail = payload && payload.detail;
  if (detail && typeof detail === 'object' && detail.reason) return detail.reason;
  if (typeof detail === 'string') return detail;
  return fallback;
}

async function api(path, options = {}) {
  const response = await fetch(path, {credentials: 'same-origin', ...options});
  if (response.status === 401 || response.status === 403 && path === '/api/auth/me') {
    window.location.replace('/login');
    throw new Error('unauthenticated');
  }
  return response;
}

function stateLabel(state) {
  return ({created: 'Создана · запуск не начат', running: 'Выполняется', degraded: 'Ограниченный результат', blocked: 'Заблокировано', completed: 'Завершено'})[state] || state;
}

function eventLabel(summary) {
  return ({
    execution_started: 'Запуск подтверждён',
    planning_started: 'Формируется план',
    runtime_step_not_configured: 'Рабочий шаг не настроен',
  })[summary] || summary || 'Событие подтверждено';
}

async function latestOperationalEvent(missionId) {
  const response = await api(`/api/user/missions/${encodeURIComponent(missionId)}/records`);
  if (!response.ok) return null;
  const payload = await response.json();
  const evidence = payload.evidence || [];
  return evidence.at(-1) || null;
}

async function renderMissions(items) {
  listBox.replaceChildren();
  if (!items.length) {
    listBox.textContent = 'Миссий пока нет.';
    return;
  }

  const liveEvents = new Map();
  await Promise.all(items.slice(0, LIVE_RECORD_LIMIT).map(async (mission) => {
    try {
      liveEvents.set(mission.id, await latestOperationalEvent(mission.id));
    } catch (_) {
      liveEvents.set(mission.id, null);
    }
  }));

  for (const mission of items) {
    const card = document.createElement('article');
    card.className = 'mission-card';
    const title = document.createElement('h3');
    const detailLink = document.createElement('a');
    detailLink.href = `/workspace/missions/${encodeURIComponent(mission.id)}`;
    detailLink.textContent = mission.title;
    title.append(detailLink);
    const target = document.createElement('p');
    target.textContent = mission.target_ref;
    const state = document.createElement('span');
    state.className = `state state-${mission.state}`;
    state.textContent = stateLabel(mission.state);
    const latest = liveEvents.get(mission.id);
    const live = document.createElement('p');
    live.className = 'message';
    live.textContent = latest
      ? `${eventLabel(latest.data && latest.data.summary)} · ${new Date(latest.created_at).toLocaleString()}`
      : 'Операционные события пока недоступны.';
    const meta = document.createElement('small');
    meta.textContent = `${mission.id} · ${new Date(mission.updated_at).toLocaleString()}`;
    card.append(title, target, state, live, meta);
    listBox.append(card);
  }
}

async function loadSession() {
  const response = await api('/api/auth/me');
  if (!response.ok) throw new Error('session_unavailable');
  const user = await response.json();
  userBox.textContent = `${user.username} · ${user.role}`;
}

async function loadMissions({silent = false} = {}) {
  if (!silent) listBox.textContent = 'Загрузка…';
  const response = await api('/api/user/missions');
  if (!response.ok) {
    if (!silent) listBox.textContent = `Не удалось загрузить миссии (${response.status}).`;
    return;
  }
  await renderMissions(await response.json());
}

function schedulePolling() {
  if (pollTimer !== null) window.clearInterval(pollTimer);
  pollTimer = window.setInterval(() => {
    if (document.visibilityState === 'visible') loadMissions({silent: true}).catch(() => {});
  }, POLL_INTERVAL_MS);
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  messageBox.hidden = true;
  const title = document.querySelector('#mission-title').value.trim();
  const targetRef = document.querySelector('#target-ref').value.trim();
  if (!title || !targetRef) {
    messageBox.textContent = 'Заполните название и цель анализа.';
    messageBox.className = 'message error';
    messageBox.hidden = false;
    return;
  }
  const correlationId = `workspace-${crypto.randomUUID()}`;
  const response = await api('/api/user/missions', {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken()},
    body: JSON.stringify({title, target_ref: targetRef, input_snapshot: {source: 'user-workspace'}, correlation_id: correlationId}),
  });
  if (!response.ok) {
    let payload = null;
    try { payload = await response.json(); } catch (_) {}
    messageBox.textContent = `Запуск не выполнен: ${typedReason(payload, `http_${response.status}`)}`;
    messageBox.className = 'message error';
    messageBox.hidden = false;
    return;
  }
  const mission = await response.json();
  form.reset();
  messageBox.textContent = mission.state === 'blocked'
    ? 'Миссия остановлена честно: рабочий контур пока не настроен.'
    : `Миссия создана: ${stateLabel(mission.state)}.`;
  messageBox.className = mission.state === 'blocked' ? 'message error' : 'message success';
  messageBox.hidden = false;
  await loadMissions();
});

document.querySelector('#refresh').addEventListener('click', () => loadMissions());
document.querySelector('#logout').addEventListener('click', async () => {
  await fetch('/api/auth/logout', {method: 'POST', credentials: 'same-origin', headers: {'X-CSRF-Token': csrfToken()}});
  window.location.replace('/login');
});

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') loadMissions({silent: true}).catch(() => {});
});

Promise.all([loadSession(), loadMissions()]).then(schedulePolling).catch(() => {});
