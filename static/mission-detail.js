const userBox = document.querySelector('#session-user');
const detailBox = document.querySelector('#mission-detail');
const errorBox = document.querySelector('#mission-error');
const guidanceBox = document.querySelector('#mission-guidance');

function stateLabel(state) {
  return ({running: 'Выполняется', degraded: 'Ограниченный результат', blocked: 'Заблокировано', completed: 'Завершено'})[state] || state;
}

function guidance(state) {
  return ({
    running: 'Анализ выполняется. Обновите страницу позже.',
    degraded: 'Получен ограниченный результат. Успешный отчёт не подтверждён.',
    blocked: 'Продолжение заблокировано. Требуется устранить указанную причину.',
    completed: 'Миссия завершена. Допустимый отчёт появится отдельным безопасным действием.',
  })[state] || 'Состояние миссии обновлено.';
}

async function api(path) {
  const response = await fetch(path, {credentials: 'same-origin'});
  if (response.status === 401) {
    window.location.replace('/login');
    throw new Error('unauthenticated');
  }
  return response;
}

async function load() {
  const missionId = decodeURIComponent(window.location.pathname.split('/').filter(Boolean).at(-1) || '');
  const [sessionResponse, missionResponse] = await Promise.all([
    api('/api/auth/me'),
    api(`/api/user/missions/${encodeURIComponent(missionId)}`),
  ]);
  if (!sessionResponse.ok) throw new Error('session_unavailable');
  const user = await sessionResponse.json();
  userBox.textContent = `${user.username} · ${user.role}`;

  if (missionResponse.status === 404) {
    errorBox.textContent = 'Миссия не найдена или недоступна текущему пользователю.';
    errorBox.hidden = false;
    return;
  }
  if (!missionResponse.ok) {
    errorBox.textContent = `Не удалось загрузить миссию (${missionResponse.status}).`;
    errorBox.hidden = false;
    return;
  }

  const mission = await missionResponse.json();
  document.querySelector('#mission-title').textContent = mission.title;
  document.querySelector('#mission-target').textContent = mission.target_ref;
  document.querySelector('#mission-id').textContent = mission.id;
  document.querySelector('#mission-created').textContent = new Date(mission.created_at).toLocaleString();
  document.querySelector('#mission-updated').textContent = new Date(mission.updated_at).toLocaleString();
  const state = document.querySelector('#mission-state');
  state.className = `state state-${mission.state}`;
  state.textContent = stateLabel(mission.state);
  guidanceBox.textContent = guidance(mission.state);
  detailBox.hidden = false;
  guidanceBox.hidden = false;
}

load().catch(() => {});
