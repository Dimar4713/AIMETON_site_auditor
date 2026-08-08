(() => {
  const root = document.querySelector('#businessAuditWorkspace');
  if (!root) return;

  const state = {
    mission: null,
    runtimeState: null,
    events: [],
    result: null,
    updatedAt: null,
  };

  const asArray = value => Array.isArray(value) ? value : [];
  const asText = value => value == null ? '' : String(value);
  const esc = value => asText(value).replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));

  function safeHref(value) {
    try {
      const url = new URL(asText(value));
      return ['http:', 'https:'].includes(url.protocol) ? url.href : '#';
    } catch {
      return '#';
    }
  }

  function lastEvent() {
    return state.events.length ? state.events[state.events.length - 1] : null;
  }

  function renderTimeline() {
    if (!state.events.length) {
      return '<p class="baw-empty">Ожидаем первое подтверждённое событие миссии.</p>';
    }
    return `<ol class="baw-timeline">${state.events.slice(-8).map(event => `
      <li class="baw-event">
        <span class="baw-event__icon" aria-hidden="true">${esc(event.icon || '•')}</span>
        <div>
          <strong>${esc(event.message || event.phase || event.event_code || 'Событие миссии')}</strong>
          ${event.detail ? `<p>${esc(event.detail)}</p>` : ''}
          ${event.next_action ? `<p class="baw-muted">Далее: ${esc(event.next_action)}</p>` : ''}
          ${event.timestamp ? `<time>${esc(new Date(event.timestamp).toLocaleTimeString('ru-RU'))}</time>` : ''}
        </div>
      </li>`).join('')}</ol>`;
  }

  function renderFacts(result) {
    const facts = asArray(result.company_facts);
    if (!facts.length) return '';
    return `<section class="baw-section">
      <div class="baw-section__head"><h3>Подтверждённые факты</h3><span>${facts.length}</span></div>
      <div class="baw-facts">${facts.map(item => `
        <article class="baw-fact">
          <strong>${esc(item.field)}</strong>
          <p>${esc(item.value)}</p>
          <small>${item.confidence ? `Уверенность: ${esc(item.confidence)}` : ''}${item.period ? ` · ${esc(item.period)}` : ''}</small>
        </article>`).join('')}</div>
    </section>`;
  }

  function renderOpportunity(result) {
    const opportunity = result.commercial_opportunity || {};
    if (!Object.keys(opportunity).length) return '';
    return `<section class="baw-section baw-opportunity">
      <div class="baw-section__head">
        <h3>Ключевая коммерческая возможность</h3>
        ${opportunity.score != null ? `<span class="baw-score">${esc(opportunity.score)}/100</span>` : ''}
      </div>
      ${opportunity.opportunity_type ? `<h4>${esc(opportunity.opportunity_type)}</h4>` : ''}
      ${opportunity.problem_hypothesis ? `<p><strong>Проблема:</strong> ${esc(opportunity.problem_hypothesis)}</p>` : ''}
      ${opportunity.recommended_solution ? `<p><strong>Решение:</strong> ${esc(opportunity.recommended_solution)}</p>` : ''}
      ${opportunity.expected_value ? `<p><strong>Ожидаемая ценность:</strong> ${esc(opportunity.expected_value)}</p>` : ''}
      ${opportunity.qualification ? `<span class="baw-chip">${esc(opportunity.qualification)}</span>` : ''}
    </section>`;
  }

  function renderAgents(result) {
    const agents = asArray(result.agents);
    if (!agents.length) return '';
    return `<section class="baw-section">
      <div class="baw-section__head"><h3>AI-возможности</h3><span>${agents.length}</span></div>
      <div class="baw-grid">${agents.map(agent => `
        <article class="baw-card">
          ${agent.priority ? `<span class="baw-chip">${esc(agent.priority)}</span>` : ''}
          ${agent.name ? `<h4>${esc(agent.name)}</h4>` : ''}
          ${agent.purpose ? `<p>${esc(agent.purpose)}</p>` : ''}
          ${agent.benefit ? `<p class="baw-value"><strong>Польза:</strong> ${esc(agent.benefit)}</p>` : ''}
        </article>`).join('')}</div>
    </section>`;
  }

  function renderZones(result) {
    const zones = asArray(result.business_machine_4x4);
    if (!zones.length) return '';
    return `<section class="baw-section">
      <div class="baw-section__head"><h3>Анализ бизнеса по 16 зонам</h3><span>${zones.length}</span></div>
      <div class="baw-grid">${zones.map(zone => `
        <article class="baw-card">
          <div class="baw-card__meta">${esc(zone.code)}${zone.status ? ` · ${esc(zone.status)}` : ''}</div>
          ${zone.vertex ? `<h4>${esc(zone.vertex)}</h4>` : ''}
          ${zone.finding ? `<p>${esc(zone.finding)}</p>` : ''}
          ${zone.sales_relevance ? `<p class="baw-value"><strong>Значение:</strong> ${esc(zone.sales_relevance)}</p>` : ''}
        </article>`).join('')}</div>
    </section>`;
  }

  function renderAction(result) {
    const action = result.action_package || {};
    if (!Object.keys(action).length) return '';
    const scenario = asArray(action.demo_scenario);
    return `<section class="baw-section baw-next">
      <p class="baw-kicker">Следующий практический шаг</p>
      ${action.next_action ? `<h3>${esc(action.next_action)}</h3>` : '<h3>Перейти от анализа к пилоту</h3>'}
      ${action.contact_reason ? `<p>${esc(action.contact_reason)}</p>` : ''}
      ${action.decision_maker_hypothesis ? `<p><strong>Кому:</strong> ${esc(action.decision_maker_hypothesis)}</p>` : ''}
      ${scenario.length ? `<ol>${scenario.map(step => `<li>${esc(step)}</li>`).join('')}</ol>` : ''}
      ${action.first_message ? `<details><summary>Первое сообщение</summary><blockquote>${esc(action.first_message)}</blockquote></details>` : ''}
    </section>`;
  }

  function renderEvidence(result) {
    const sources = asArray(result.sources);
    const facts = asArray(result.company_facts);
    const assumptions = asArray(result.risks_and_assumptions);
    if (!sources.length && !facts.length && !assumptions.length) return '';
    return `<section class="baw-section">
      <details class="baw-details">
        <summary>Почему AIMETON так решил? · ${facts.length} фактов · ${sources.length} источников</summary>
        ${sources.length ? `<div class="baw-sources">${sources.map(source => `
          <article>
            <strong>${esc(source.title || source.id)}</strong>
            ${source.url ? `<a href="${esc(safeHref(source.url))}" target="_blank" rel="noopener">${esc(source.url)}</a>` : ''}
            ${source.evidence_quote ? `<p>${esc(source.evidence_quote)}</p>` : ''}
            ${source.evidence_level ? `<small>Уровень evidence: ${esc(source.evidence_level)}</small>` : ''}
          </article>`).join('')}</div>` : ''}
        ${assumptions.length ? `<div class="baw-assumptions"><h4>Ограничения и предположения</h4><ul>${assumptions.map(item => `<li>${esc(item)}</li>`).join('')}</ul></div>` : ''}
      </details>
    </section>`;
  }

  function renderQuality(result) {
    const readiness = result.readiness || {};
    if (!Object.keys(readiness).length) return '';
    const blockers = asArray(readiness.release_blockers);
    return `<section class="baw-section">
      <details class="baw-details">
        <summary>Качество и достоверность анализа</summary>
        <div class="baw-quality">
          ${readiness.profile_completeness != null ? `<p><strong>Полнота профиля:</strong> ${esc(Math.round(Number(readiness.profile_completeness) * 100))}%</p>` : ''}
          ${readiness.evidence_quality != null ? `<p><strong>Качество evidence:</strong> ${esc(Math.round(Number(readiness.evidence_quality) * 100))}%</p>` : ''}
          ${readiness.identity_state ? `<p><strong>Identity:</strong> ${esc(readiness.identity_state)}</p>` : ''}
          ${readiness.sufficiency_level ? `<p><strong>Достаточность:</strong> ${esc(readiness.sufficiency_level)}</p>` : ''}
          ${readiness.analysis_state ? `<p><strong>Состояние анализа:</strong> ${esc(readiness.analysis_state)}</p>` : ''}
          ${blockers.length ? `<p><strong>Блокеры выпуска:</strong> ${esc(blockers.join(', '))}</p>` : ''}
        </div>
      </details>
    </section>`;
  }

  function renderResult(result) {
    if (!result) return '';
    return `<div class="baw-result">
      <section class="baw-hero">
        <p class="baw-kicker">Результат исследования</p>
        <div class="baw-hero__row">
          <div>
            <h2>${esc(result.company_name || 'Компания')}</h2>
            ${result.url ? `<a href="${esc(safeHref(result.url))}" target="_blank" rel="noopener">${esc(result.url)}</a>` : ''}
          </div>
        </div>
        ${result.business_summary ? `<p class="baw-summary">${esc(result.business_summary)}</p>` : ''}
      </section>
      ${renderOpportunity(result)}
      ${renderAgents(result)}
      ${renderZones(result)}
      ${renderAction(result)}
      ${renderFacts(result)}
      ${renderEvidence(result)}
      ${renderQuality(result)}
      <section class="baw-section baw-continue">
        <h3>Продолжить работу с результатом</h3>
        <p>Чат и экспорт Markdown, Word и PDF доступны ниже в существующем интерфейсе AIMETON.</p>
      </section>
    </div>`;
  }

  function renderWorkspace() {
    const latest = lastEvent();
    const mission = state.mission || {};
    const running = !state.result;
    root.innerHTML = `
      <div class="baw-shell">
        <section class="baw-runtime ${running ? '' : 'baw-runtime--done'}">
          <div class="baw-runtime__head">
            <div>
              <p class="baw-kicker">AIMETON · живая миссия</p>
              <h2>${running ? 'Исследование бизнеса выполняется' : 'Исследование завершено'}</h2>
              <p class="baw-muted">${mission.mission_id ? `Миссия ${esc(mission.mission_id)}` : 'Миссия создаётся'}</p>
            </div>
            <span class="baw-state">${esc(state.runtimeState || 'queued')}</span>
          </div>
          ${latest ? `<div class="baw-current"><span>${esc(latest.icon || '●')}</span><div><strong>${esc(latest.message || 'Выполняется')}</strong>${latest.detail ? `<p>${esc(latest.detail)}</p>` : ''}${latest.next_action ? `<p class="baw-muted">Далее: ${esc(latest.next_action)}</p>` : ''}</div></div>` : ''}
          ${running ? renderTimeline() : ''}
        </section>
        ${renderResult(state.result)}
      </div>`;
  }

  window.addEventListener('aimeton:analysis-started', event => {
    state.mission = event.detail?.mission || null;
    state.runtimeState = state.mission?.state || 'queued';
    state.events = [];
    state.result = null;
    state.updatedAt = null;
    root.hidden = false;
    renderWorkspace();
  });

  window.addEventListener('aimeton:analysis-update', event => {
    state.mission = event.detail?.mission || state.mission;
    state.runtimeState = event.detail?.state || state.runtimeState;
    state.events = asArray(event.detail?.events);
    state.updatedAt = event.detail?.updated_at || null;
    root.hidden = false;
    renderWorkspace();
  });

  window.addEventListener('aimeton:analysis-complete', event => {
    state.mission = event.detail?.mission || state.mission;
    state.runtimeState = event.detail?.state || state.runtimeState;
    state.result = event.detail?.result || null;
    state.updatedAt = event.detail?.updated_at || null;
    root.hidden = false;
    renderWorkspace();
  });
})();
