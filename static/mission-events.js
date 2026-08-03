(() => {
  const states = Object.freeze({
    created: {icon: '○', label: 'Создана · запуск не начат'},
    running: {icon: '●', label: 'Выполняется'},
    degraded: {icon: '⚠️', label: 'Ограниченный результат'},
    blocked: {icon: '⛔', label: 'Заблокировано'},
    completed: {icon: '✅', label: 'Завершено'},
  });

  const events = Object.freeze({
    execution_started: {icon: '▶️', label: 'Запуск миссии подтверждён.'},
    planning_started: {icon: '🧭', label: 'Формируется план выполнения.'},
    runtime_step_not_configured: {icon: '⏸️', label: 'Рабочий шаг пока не настроен.'},
    site_research_started: {icon: '🌐', label: 'Исследуется сайт компании.'},
    identity_resolution_started: {icon: '🏢', label: 'Сопоставляется юридическое лицо.'},
    evidence_search_started: {icon: '📚', label: 'Проверяются источники и доказательства.'},
    sufficiency_evaluation_started: {icon: '⚖️', label: 'Оценивается достаточность доказательств.'},
    profile_synthesis_started: {icon: '🤖', label: 'Формируется профиль компании.'},
    report_generation_started: {icon: '📄', label: 'Формируется отчёт.'},
  });

  const heartbeats = Object.freeze({
    fresh: 'Связь с исполнением подтверждена свежим событием.',
    stalled: 'Миссия не обновлялась в установленный срок и считается остановившейся.',
    missing: 'Нет достоверного времени heartbeat; активность не подтверждена.',
    not_applicable: '',
  });

  const reasons = Object.freeze({
    heartbeat_stalled: 'События выполнения перестали обновляться.',
    heartbeat_missing: 'Отсутствует корректная временная метка события.',
    runtime_step_not_configured: 'Рабочий шаг пока не настроен.',
    execution_not_started: 'Исполнение миссии ещё не началось.',
  });

  const nextActions = Object.freeze({
    configure_bounded_runtime_worker: 'Подключить ограниченный рабочий контур выполнения.',
    retry_mission: 'Повторить миссию после устранения причины.',
    review_evidence: 'Проверить собранные доказательства.',
    open_report: 'Открыть доступный отчёт.',
  });

  function state(state) {
    return states[state] || {icon: '•', label: state || 'Состояние неизвестно'};
  }

  function event(summary, stateName) {
    const terminal = state(stateName);
    if (['blocked', 'degraded', 'completed'].includes(stateName)) return terminal;
    return events[summary] || {icon: '•', label: summary || 'Операционное событие подтверждено.'};
  }

  function heartbeat(status) {
    return heartbeats[status] || '';
  }

  function reason(code) {
    return reasons[code] || code || '';
  }

  function nextAction(code) {
    const label = nextActions[code] || code || '';
    return label ? `Следующий шаг: ${label}` : '';
  }

  window.AIMETON_MISSION_UI = Object.freeze({state, event, heartbeat, reason, nextAction});
})();
