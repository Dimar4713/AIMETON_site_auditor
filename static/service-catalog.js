(() => {
  const cards = [...document.querySelectorAll('[data-service-card]')];
  const panels = [...document.querySelectorAll('[data-service-panel]')];

  function selectService(name) {
    cards.forEach(card => card.setAttribute('aria-pressed', String(card.dataset.serviceCard === name)));
    panels.forEach(panel => { panel.hidden = panel.dataset.servicePanel !== name; });
    const active = panels.find(panel => panel.dataset.servicePanel === name);
    active?.scrollIntoView({behavior: 'smooth', block: 'nearest'});
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
      appendItem(list, 'Результат поиска', `Обнаружено компаний: ${data.discovered ?? 0}`, `Регион: ${data.region || region}`);
      (data.candidates || []).slice(0, 10).forEach(candidate => {
        appendItem(list, candidate.company_name || candidate.url, candidate.recommended_solution || candidate.business_summary || 'Кандидат для дальнейшего анализа', `Приоритет: ${candidate.final_score ?? candidate.preliminary_score ?? '—'} · ${candidate.qualification || 'не определена'}`);
      });
      output.hidden = false;
      setStatus(status, 'Список кандидатов подготовлен.', 'success');
    } catch (error) {
      setStatus(status, `Поиск не выполнен: ${error.message}`, 'error');
    } finally {
      button.disabled = false;
    }
  });

  selectService('site-audit');
})();
