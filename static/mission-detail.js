const userBox = document.querySelector('#session-user');
const detailBox = document.querySelector('#mission-detail');
const errorBox = document.querySelector('#mission-error');
const guidanceBox = document.querySelector('#mission-guidance');
const evidenceBox = document.querySelector('#mission-evidence');
const reportBox = document.querySelector('#mission-report');
const liveFeedBox = document.querySelector('#mission-live-feed');
const liveNextBox = document.querySelector('#mission-live-next');
const liveUpdatedBox = document.querySelector('#mission-live-updated');
const historyBox = document.querySelector('#mission-history');

function stateLabel(state) {
  return ({created: 'Создана · запуск не начат', running: 'Выполняется', degraded: 'Ограниченный результат', blocked: 'Заблокировано', completed: 'Завершено'})[state] || state;
}

function guidance(state) {
  return ({
    created: 'Миссия сохранена, но execution attempt ещё не создан. Анализ не выполняется.',
    running: 'Анализ выполняется и подтверждён execution-событиями.',
    degraded: 'Получен ограниченный результат. Успешный отчёт не подтверждён.',
    blocked: 'Продолжение заблокировано. Требуется устранить указанную причину.',
    completed: 'Миссия завершена. Ниже доступен owner-scoped результат анализа.',
  })[state] || 'Состояние миссии обновлено.';
}

function eventLabel(summary) {
  return ({
    execution_started: 'Запуск миссии подтверждён.',
    planning_started: 'Формируется план выполнения.',
    site_fetch_started: 'Подключаемся к сайту.',
    site_fetch_completed: 'Сайт получен.',
    analysis_completed: 'Анализ завершён.',
    analysis_failed: 'Анализ остановлен.',
    runtime_step_not_configured: 'Рабочий шаг пока не настроен.',
  })[summary] || summary || 'Операционное событие подтверждено.';
}

function eventIcon(summary, state) {
  if (state === 'blocked') return '⛔';
  if (state === 'degraded') return '⚠️';
  if (state === 'completed') return '✅';
  return ({
    execution_started: '▶️',
    planning_started: '🧭',
    site_fetch_started: '🌐',
    site_fetch_completed: '📥',
    analysis_completed: '✅',
    analysis_failed: '⛔',
    runtime_step_not_configured: '⏸️',
  })[summary] || '•';
}

function heartbeatLabel(payload) {
  return ({
    fresh: 'Связь с исполнением подтверждена свежим событием.',
    stalled: 'Миссия не обновлялась в установленный срок и считается остановившейся.',
    missing: 'Нет достоверного времени heartbeat; активность не подтверждена.',
    not_applicable: 'Heartbeat не требуется для текущего терминального состояния.',
  })[payload.heartbeat_status] || '';
}

function reasonLabel(reason) {
  return ({
    heartbeat_stalled: 'События выполнения перестали обновляться.',
    heartbeat_missing: 'Отсутствует корректная временная метка события.',
    runtime_step_not_configured: 'Рабочий шаг пока не настроен.',
    site_analysis_failed: 'Не удалось получить или обработать целевой сайт.',
    bounded_runtime_failed: 'Рабочий контур завершился внутренней безопасной остановкой.',
  })[reason] || reason || '';
}

function nextActionLabel(nextAction) {
  return ({
    configure_bounded_runtime_worker: 'Следующий шаг: подключить ограниченный рабочий контур выполнения.',
    verify_target_and_retry: 'Следующий шаг: проверить адрес сайта и повторить запуск.',
    inspect_runtime_trace: 'Следующий шаг: проверить технологический trace миссии.',
  })[nextAction] || (nextAction ? `Следующий шаг: ${nextAction}.` : '');
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
    summary.textContent = eventLabel(record.data.summary) || record.data.status || 'Запись подтверждена.';
    const meta = document.createElement('small');
    const level = record.data.level ? ` · ${record.data.level}` : '';
    meta.textContent = `${record.id}${level} · ${new Date(record.created_at).toLocaleString()}`;
    item.append(title, summary, meta);
    evidenceBox.append(item);
  }
}

function renderTerminalHistory(mission, records) {
  historyBox.replaceChildren();
  const terminal = ['blocked', 'degraded', 'completed'].includes(mission.state);
  if (!terminal) {
    historyBox.hidden = true;
    return;
  }

  const events = [...(records.evidence || [])].sort((left, right) => {
    const timeDelta = new Date(left.created_at).getTime() - new Date(right.created_at).getTime();
    if (timeDelta !== 0) return timeDelta;
    return String(left.id).localeCompare(String(right.id));
  });

  if (!events.length) {
    historyBox.textContent = 'История этапов недоступна: терминальное состояние не сопровождается допустимыми операционными событиями.';
    historyBox.hidden = false;
    return;
  }

  const heading = document.createElement('h3');
  heading.textContent = 'История этапов';
  const list = document.createElement('ol');
  list.className = 'mission-list';

  for (const record of events) {
    const data = record.data || {};
    const item = document.createElement('li');
    item.className = 'mission-card';

    const summary = document.createElement('p');
    summary.textContent = `${eventIcon(data.summary, data.state)} ${eventLabel(data.summary)}`;

    const details = document.createElement('p');
    const reason = data.reason_code ? `Причина: ${reasonLabel(data.reason_code)}.` : '';
    const next = nextActionLabel(data.next_action);
    details.textContent = [reason, next].filter(Boolean).join(' ');
    details.hidden = !details.textContent;

    const meta = document.createElement('small');
    meta.textContent = new Date(record.created_at).toLocaleString();
    item.append(summary, details, meta);
    list.append(item);
  }

  historyBox.append(heading, list);
  historyBox.hidden = false;
}

function renderLiveFeed(mission, records) {
  const events = records.evidence || [];
  const latest = events.at(-1);
  const heartbeat = heartbeatLabel(records);
  if (!latest) {
    liveFeedBox.textContent = mission.state === 'created'
      ? 'Запуск ещё не подтверждён операционными событиями.'
      : heartbeat || 'Операционные события пока недоступны.';
    const reason = reasonLabel(records.runtime_reason);
    liveNextBox.textContent = reason ? `Причина: ${reason}` : '';
    liveNextBox.hidden = !reason;
    liveUpdatedBox.textContent = `Состояние: ${stateLabel(mission.state)}`;
    return;
  }

  const data = latest.data || {};
  liveFeedBox.textContent = [stateLabel(mission.state), eventLabel(data.summary), heartbeat].filter(Boolean).join(' · ');
  const nextText = nextActionLabel(data.next_action);
  const typedReason = records.runtime_reason || data.reason_code;
  if (typedReason || nextText) {
    const reason = typedReason ? `Причина: ${reasonLabel(typedReason)}.` : '';
    liveNextBox.textContent = [reason, nextText].filter(Boolean).join(' ');
    liveNextBox.hidden = false;
  } else {
    liveNextBox.hidden = true;
  }
  const updatedAt = records.last_event_at || latest.created_at;
  liveUpdatedBox.textContent = `Последнее обновление: ${new Date(updatedAt).toLocaleString()}`;
}

function renderDaDataRegistryMirror(card, report) {
  const providerState = report.readiness?.provider_states?.dadata;
  const facts = (Array.isArray(report.company_facts) ? report.company_facts : [])
    .filter((fact) => String(fact.note || '').startsWith('DaData registry mirror'));
  const notes = (Array.isArray(report.risks_and_assumptions) ? report.risks_and_assumptions : [])
    .filter((note) => String(note).startsWith('DaData registry mirror'));

  if (!providerState && !facts.length && !notes.length) return;

  const heading = document.createElement('h4');
  heading.textContent = 'DaData · зеркало реестров';
  const state = document.createElement('p');
  state.textContent = `Состояние: ${providerState || 'unknown'} · не является официальной верификацией ФНС.`;
  card.append(heading, state);

  if (facts.length) {
    const list = document.createElement('ul');
    for (const fact of facts) {
      const item = document.createElement('li');
      item.textContent = `${fact.field}: ${fact.value}`;
      list.append(item);
    }
    card.append(list);
  }

  for (const note of notes.slice(0, 3)) {
    const line = document.createElement('small');
    line.textContent = note;
    card.append(line);
  }
}

async function renderReport(missionId, payload) {
  const reportMeta = payload.report_metadata;
  if (!reportMeta || payload.report_reason) {
    reportBox.textContent = `Отчёт недоступен: ${payload.report_reason || 'report_not_available'}.`;
    return;
  }

  const response = await api(`/api/user/missions/${encodeURIComponent(missionId)}/report`);
  if (!response.ok) {
    reportBox.textContent = `Отчёт недоступен (${response.status}).`;
    return;
  }
  const report = await response.json();
  reportBox.replaceChildren();

  const card = document.createElement('article');
  card.className = 'mission-card';
  const title = document.createElement('h3');
  title.textContent = report.company_name || 'Результат анализа';
  const summary = document.createElement('p');
  summary.textContent = report.business_summary || 'Краткое описание не сформировано.';
  card.append(title, summary);

  const opportunity = report.commercial_opportunity;
  if (opportunity) {
    const line = document.createElement('p');
    line.textContent = `Возможность: ${opportunity.recommended_solution || opportunity.opportunity_type || '—'} · оценка ${opportunity.score ?? '—'}/100 · ${opportunity.qualification || ''}`;
    card.append(line);
  }

  const sourceLine = document.createElement('p');
  sourceLine.textContent = `Подтверждённых/собранных источников: ${Array.isArray(report.sources) ? report.sources.length : 0}`;
  card.append(sourceLine);

  renderDaDataRegistryMirror(card, report);

  const agents = Array.isArray(report.agents) ? report.agents : [];
  if (agents.length) {
    const heading = document.createElement('h4');
    heading.textContent = 'Рекомендуемые AI-агенты';
    const list = document.createElement('ul');
    for (const agent of agents) {
      const item = document.createElement('li');
      item.textContent = `${agent.name}: ${agent.purpose} — ${agent.benefit}`;
      list.append(item);
    }
    card.append(heading, list);
  }

  reportBox.append(card);
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
    liveFeedBox.textContent = 'Данные недоступны.';
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
    renderLiveFeed(mission, records);
    renderTerminalHistory(mission, records);
    renderEvidence(records.evidence || []);
    await renderReport(missionId, records);
  } else {
    liveFeedBox.textContent = 'Ход миссии недоступен.';
    evidenceBox.textContent = 'Evidence/УДП недоступны.';
    reportBox.textContent = 'Метаданные отчёта недоступны.';
  }
}

load().catch(() => {});
