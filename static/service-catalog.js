(() => {
  const cards = [...document.querySelectorAll('[data-service-card]')];
  const panels = [...document.querySelectorAll('[data-service-panel]')];

  const SUPPORTING_HOSTS = new Set([
    'prodoctorov.ru', '32top.ru', 'zoon.ru', 'flamp.ru', 'otzovik.com', 'irecommend.ru',
    'rusprofile.ru', 'checko.ru', 'list-org.com', 'audit-it.ru', 'companies.rbc.ru',
    'spark-interfax.ru', 'sbis.ru', 'kp.ru', 'rbc.ru', 'tass.ru', 'ria.ru',
    'vedomosti.ru', 'kommersant.ru', 'interfax.ru',
  ]);
  const SUPPORTING_TITLE_MARKERS = [
    'рейтинг', 'лучшие', 'отзывы', 'каталог', 'список', 'обзор', 'топ ',
    'новости', 'рейтинг клиник', 'рейтинг стоматолог', 'врачи', 'про докторов',
  ];

  function clearSelection() {
    cards.forEach(card => card.setAttribute('aria-pressed', 'false'));
    panels.forEach(panel => { panel.hidden = true; });
  }

  function selectService(name) {
    cards.forEach(card => card.setAttribute('aria-pressed', String(card.dataset.serviceCard === name)));
    panels.forEach(panel => { panel.hidden = panel.dataset.servicePanel !== name; });
    const active = panels.find(panel => panel.dataset.servicePanel === name);
    active?.scrollIntoView({behavior: 'smooth', block: 'start'});
    active?.querySelector('input')?.focus({preventScroll: true});
  }

  cards.forEach(card => {
    if (!card.disabled) card.addEventListener('click', () => selectService(card.dataset.serviceCard));
  });

  function setStatus(node, message, kind = '') {
    node.textContent = message;
    node.className = `service-status ${kind}`.trim();
  }

  async function postJson(path, payload) {
    const response = await fetch(path, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = typeof data.detail === 'string' ? data.detail : data.detail?.reason;
      throw new Error(detail || `HTTP ${response.status}`);
    }
    return data;
  }

  function safeHttpUrl(value) {
    if (!value) return '';
    try {
      const url = new URL(String(value));
      return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
    } catch {
      return '';
    }
  }

  function hostOf(value) {
    try {
      return new URL(value).hostname.toLowerCase().replace(/^www\./, '');
    } catch {
      return '';
    }
  }

  function isSupportingHost(host) {
    return [...SUPPORTING_HOSTS].some(known => host === known || host.endsWith(`.${known}`));
  }

  function classifyCandidate(candidate) {
    const url = safeHttpUrl(candidate.url || candidate.official_url || candidate.website);
    const host = hostOf(url);
    const sourceText = `${candidate.source_title || ''} ${candidate.source_snippet || ''}`.toLowerCase();
    if (isSupportingHost(host) || SUPPORTING_TITLE_MARKERS.some(marker => sourceText.includes(marker))) {
      return {kind: 'supporting', label: 'Источник для проверки'};
    }
    if (candidate.deep_analysis_performed === true) {
      return {kind: 'company', label: 'Компания-кандидат'};
    }
    return {kind: 'observation', label: 'Наблюдение'};
  }

  function priorityLabel(score, qualification) {
    if (score == null) return qualification || 'Недостаточно данных';
    if (score >= 70) return 'Высокий приоритет';
    if (score >= 55) return 'Перспективный';
    return qualification === 'Недостаточно данных' ? qualification : 'Наблюдение';
  }

  function appendItem(container, title, text, meta = '') {
    const item = document.createElement('article');
    item.className = 'service-summary__item';
    const heading = document.createElement('strong');
    heading.textContent = title;
    const body = document.createElement('div');
    body.textContent = text || 'Нет данных';
    item.append(heading, body);
    if (meta) {
      const small = document.createElement('div');
      small.className = 'service-summary__meta';
      small.textContent = meta;
      item.append(small);
    }
    container.append(item);
  }

  function appendGroup(container, title, description, kind) {
    const section = document.createElement('section');
    section.className = `hunter-group hunter-group--${kind}`;
    const heading = document.createElement('h3');
    heading.textContent = title;
    const note = document.createElement('p');
    note.className = 'hunter-group__note';
    note.textContent = description;
    const list = document.createElement('div');
    list.className = 'hunter-group__list';
    section.append(heading, note, list);
    container.append(section);
    return list;
  }

  function handoffCandidate(candidate, fallbackRegion) {
    const name = String(candidate.company_name || '').trim();
    const url = safeHttpUrl(candidate.url || candidate.official_url || candidate.website);
    const region = String(candidate.region || fallbackRegion || '').trim();
    document.querySelector('#companyName').value = name;
    document.querySelector('#companyUrl').value = url;
    document.querySelector('#companyRegion').value = region;
    selectService('company-intelligence');
    const status = document.querySelector('#companyIntelligenceStatus');
    setStatus(status, 'Данные кандидата перенесены. Проверьте их и явно запустите исследование.', 'success');
    document.querySelector('#companyName').focus({preventScroll: true});
  }

  function appendCandidate(container, candidate, fallbackRegion) {
    const classification = classifyCandidate(candidate);
    const item = document.createElement('article');
    item.className = `service-summary__item service-summary__candidate service-summary__candidate--${classification.kind}`;
    const name = String(candidate.company_name || candidate.url || 'Результат без названия').trim();
    const url = safeHttpUrl(candidate.url || candidate.official_url || candidate.website);
    const region = String(candidate.region || fallbackRegion || '').trim();
    const summary = candidate.recommended_solution || candidate.business_summary || '';
    const score = candidate.final_score ?? candidate.preliminary_score;
    const qualification = candidate.qualification || 'не определена';
    const nameOnly = !url && !summary && score == null;

    const top = document.createElement('div');
    top.className = 'service-summary__candidate-top';
    const heading = document.createElement('strong');
    heading.textContent = name;
    const badge = document.createElement('span');
    badge.className = `service-summary__kind service-summary__kind--${classification.kind}`;
    badge.textContent = classification.label;
    top.append(heading, badge);
    item.append(top);

    if (summary) {
      const body = document.createElement('div');
      body.className = 'service-summary__description';
      body.textContent = summary;
      item.append(body);
    }

    if (url) {
      const link = document.createElement('a');
      link.href = url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = url;
      link.className = 'service-summary__url';
      item.append(link);
    }

    const meta = document.createElement('div');
    meta.className = 'service-summary__meta';
    const humanPriority = priorityLabel(score, qualification);
    meta.textContent = `${region ? `Регион: ${region} · ` : ''}${humanPriority}${score == null ? '' : ` · балл ${score}/100`}${nameOnly ? ' · Недостаточно данных' : ''}`;
    item.append(meta);

    if (classification.kind === 'company') {
      const action = document.createElement('button');
      action.type = 'button';
      action.className = 'btn-ghost hunter-candidate-action';
      action.textContent = 'Исследовать компанию';
      action.addEventListener('click', () => handoffCandidate(candidate, fallbackRegion));
      item.append(action);
    }
    container.append(item);
  }

  function renderHunterCandidates(container, candidates, fallbackRegion) {
    const groups = {company: [], supporting: [], observation: []};
    candidates.forEach(candidate => {
      const classification = classifyCandidate(candidate);
      groups[classification.kind].push(candidate);
    });

    if (groups.company.length) {
      const list = appendGroup(container, 'Компании-кандидаты', 'Наиболее пригодные для следующего шага: сайт был глубоко обработан.', 'company');
      groups.company.forEach(candidate => appendCandidate(list, candidate, fallbackRegion));
    }
    if (groups.supporting.length) {
      const details = document.createElement('details');
      details.className = 'hunter-supporting-details';
      const summary = document.createElement('summary');
      summary.textContent = `Источники для дополнительной проверки (${groups.supporting.length})`;
      const list = document.createElement('div');
      list.className = 'hunter-group__list';
      groups.supporting.forEach(candidate => appendCandidate(list, candidate, fallbackRegion));
      details.append(summary, list);
      container.append(details);
    }
    if (groups.observation.length) {
      const details = document.createElement('details');
      details.className = 'hunter-supporting-details';
      const summary = document.createElement('summary');
      summary.textContent = `Наблюдение (${groups.observation.length})`;
      const list = document.createElement('div');
      list.className = 'hunter-group__list';
      groups.observation.forEach(candidate => appendCandidate(list, candidate, fallbackRegion));
      details.append(summary, list);
      container.append(details);
    }
  }

  const companyForm = document.querySelector('#companyIntelligenceForm');
  companyForm?.addEventListener('submit', async event => {
    event.preventDefault();
    const status = document.querySelector('#companyIntelligenceStatus');
    const output = document.querySelector('#companyIntelligenceOutput');
    const list = output.querySelector('.service-summary');
    const button = companyForm.querySelector('button');
    button.disabled = true;
    output.hidden = true;
    list.replaceChildren();
    setStatus(status, 'Исследуем компанию и открытые источники…');
    try {
      const companyName = document.querySelector('#companyName').value.trim();
      const url = document.querySelector('#companyUrl').value.trim();
      const region = document.querySelector('#companyRegion').value.trim();
      const payload = {company_name: companyName};
      if (url) payload.url = url;
      if (region) payload.region = region;
      const data = await postJson('/api/company-intelligence', payload);
      appendItem(list, data.company_name || companyName, data.recommended_solution || 'Исследование завершено', `Статус: ${data.status || 'partial'} · коммерческий балл: ${data.commercial_score ?? '—'}`);
      (data.scent_summary || []).slice(0, 6).forEach((item, index) => appendItem(list, `Сигнал ${index + 1}`, item));
      appendItem(list, 'Источники', `Найдено: ${(data.sources || []).length}`);
      output.hidden = false;
      setStatus(status, 'Профиль компании подготовлен.', 'success');
    } catch (error) {
      setStatus(status, `Исследование не выполнено: ${error.message}`, 'error');
    } finally {
      button.disabled = false;
    }
  });

  const huntForm = document.querySelector('#hunterForm');
  huntForm?.addEventListener('submit', async event => {
    event.preventDefault();
    const status = document.querySelector('#hunterStatus');
    const output = document.querySelector('#hunterOutput');
    const list = output.querySelector('.service-summary');
    const button = huntForm.querySelector('button');
    button.disabled = true;
    output.hidden = true;
    list.replaceChildren();
    setStatus(status, 'Ищем и ранжируем компании…');
    try {
      const region = document.querySelector('#hunterRegion').value.trim();
      const industry = document.querySelector('#hunterIndustry').value.trim();
      const payload = {
        region,
        industries: industry ? [industry] : [],
        max_queries: 6,
        results_per_query: 5,
        max_candidates: 30,
        output_limit: 10,
        concurrency: 2,
      };
      const data = await postJson('/api/hunt', payload);
      appendItem(list, 'Результат поиска', `Обнаружено источников-кандидатов: ${data.discovered ?? 0}`, `Регион: ${data.region || region} · балл выше = ближе к профилю потенциального клиента`);
      renderHunterCandidates(list, (data.candidates || []).slice(0, 10), data.region || region);
      output.hidden = false;
      setStatus(status, 'Список кандидатов подготовлен.', 'success');
    } catch (error) {
      setStatus(status, `Поиск не выполнен: ${error.message}`, 'error');
    } finally {
      button.disabled = false;
    }
  });

  clearSelection();
})();
