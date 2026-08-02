const userBox = document.querySelector('#session-user');
const detailBox = document.querySelector('#mission-detail');
const errorBox = document.querySelector('#mission-error');
const guidanceBox = document.querySelector('#mission-guidance');
const evidenceBox = document.querySelector('#mission-evidence');
const reportBox = document.querySelector('#mission-report');

function stateLabel(state) {
  return ({created: 'Создана · запуск не начат', running: 'Выполняется', degraded: 'Ограниченный результат', blocked: 'Заблокировано', completed: 'Завершено'})[state] || state;
}

function guidance(state) {
  return ({
    created: 'Миссия сохранена, но execution attempt ещё не создан. Анализ не выполняется.',
    running: 'Анализ выполняется и подтверждён execution-событиями.',
    degraded: 'Получен ограниченный результат. Успешный отчёт не подтверждён.',
    blocked: 'Продолжение заблокировано. Требуется устранить указанную причину.',
    completed: 'Миссия завершена. Доступность отчёта определяется отдельным release-контрактом.',
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

function renderEvidence(records) {
  evidenceBox.replaceChildren();
  if (!records.length) {
    evidenceBox.textContent = 'Допустимые evidence/УДП записи пока отсутствуют.';
    return;
  }
  for (const record of records) {
    const item = document.createElement('article');
    item.className = 'mission-card';
    const title = document.createElement('h3');
    title.textContent = record.kind === 'sufficiency' ? 'УДП' : 'Шаг анализа';
    const summary = document.createElement('p');
    summary.textContent = record.data.summary || record.data.status || 'Запись подтверждена.';
    const meta = document.createElement('small');
    const level = record.data.level ? ` · ${record.data.level}` : '';
    meta.textContent = `${record.id}${level} · ${new Date(record.created_at).toLocaleString()}`;
    item.append(title, summary, meta);
    evidenceBox.append(item);
  }
}

function renderReport(payload) {
  const report = payload.report_metadata;
  if (!report || payload.report_reason) {
    reportBox.textContent = `Отчёт недоступен: ${payload.report_reason || 'report_not_available'}.`;
    return;
  }
  reportBox.textContent = `Отчёт ${report.data.report_id || report.id} доступен (${report.data.format || report.data.content_type || 'metadata'}).`;
}

async function load() {
  const missionId = decodeURIComponent(window.location.pathname.split('/').filter(Boolean).at(-1) || '');
  const [sessionResponse, missionResponse, recordsResponse] = await Promise.all([
    api('/api/auth/me'),
    api(`/api/user/missions/${encodeURIComponent(missionId)}`),
    api(`/api/user/missions/${encodeURIComponent(missionId)}/records`),
  ]);
  if (!sessionResponse.ok) throw new Error('session_unavailable');
  const user = await sessionResponse.json();
  userBox.textContent = `${user.username} · ${user.role}`;

  if (missionResponse.status === 404) {
    errorBox.textContent = 'Миссия не найдена или недоступна текущему пользователю.';
    errorBox.hidden = false;
    evidenceBox.textContent = 'Данные недоступны.';
    reportBox.textContent = 'Данные недоступны.';
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

  if (recordsResponse.ok) {
    const records = await recordsResponse.json();
    renderEvidence(records.evidence || []);
    renderReport(records);
  } else {
    evidenceBox.textContent = 'Evidence/УДП недоступны.';
    reportBox.textContent = 'Метаданные отчёта недоступны.';
  }
}

load().catch(() => {});
