(() => {
  const form = document.querySelector('#search-strategy-form');
  if (!form) return;

  const message = document.querySelector('#search-strategy-message');
  const updated = document.querySelector('#search-strategy-updated');
  const refresh = document.querySelector('#refresh-search-strategies');
  const tariffsNode = document.querySelector('#search-tariff-profiles');
  const catalogNode = document.querySelector('#search-strategy-catalog');
  const activeTariff = document.querySelector('#search-active-tariff');
  const defaultStrategy = document.querySelector('#search-default-strategy');
  const emergencyStrategy = document.querySelector('#search-emergency-strategy');
  const providersSelect = document.querySelector('#search-enabled-providers');

  let state = null;
  let catalog = [];

  function csrfToken() {
    const prefix = 'aimeton_csrf=';
    const part = document.cookie.split(';').map(v => v.trim()).find(v => v.startsWith(prefix));
    return part ? decodeURIComponent(part.slice(prefix.length)) : '';
  }

  function setMessage(text, kind = '') {
    message.textContent = text;
    message.className = `message ${kind}`.trim();
  }

  function implementedStrategies() {
    return catalog.filter(item => item.implemented);
  }

  function strategyOptions(selected, includeEmpty = false) {
    const options = [];
    if (includeEmpty) options.push('<option value="">Нет</option>');
    implementedStrategies().forEach(item => {
      const isSelected = item.id === selected ? ' selected' : '';
      options.push(`<option value="${item.id}"${isSelected}>${item.label}</option>`);
    });
    return options.join('');
  }

  function selectedValues(select) {
    return [...select.selectedOptions].map(option => option.value);
  }

  function tariffCard(profile) {
    const article = document.createElement('article');
    article.className = 'mission-card';
    article.dataset.tariff = profile.id;
    article.innerHTML = `
      <h3>${profile.label} <small>(${profile.id})</small></h3>
      <label>Включён<input data-field="enabled" type="checkbox" ${profile.enabled ? 'checked' : ''}></label>
      <label>Стратегия<select data-field="strategy">${strategyOptions(profile.strategy)}</select></label>
      <label>Порядок providers<input data-field="provider_order" value="${profile.provider_order.join(',')}"></label>
      <label>Платные providers<select data-field="paid_policy">
        <option value="inherit" ${profile.paid_policy === 'inherit' ? 'selected' : ''}>Наследовать</option>
        <option value="deny" ${profile.paid_policy === 'deny' ? 'selected' : ''}>Запретить</option>
        <option value="allow_with_budget" ${profile.paid_policy === 'allow_with_budget' ? 'selected' : ''}>Разрешить с бюджетом</option>
      </select></label>
      <label>Платный fan-out<select data-field="paid_fanout_policy">
        <option value="inherit" ${profile.paid_fanout_policy === 'inherit' ? 'selected' : ''}>Наследовать</option>
        <option value="deny" ${profile.paid_fanout_policy === 'deny' ? 'selected' : ''}>Запретить</option>
        <option value="allow_with_budget" ${profile.paid_fanout_policy === 'allow_with_budget' ? 'selected' : ''}>Разрешить с бюджетом</option>
      </select></label>
      <label>Budget RUB<input data-field="max_cost_rub" type="number" min="0" step="0.01" value="${profile.max_cost_rub}"></label>
      <label>Budget USD<input data-field="max_cost_usd" type="number" min="0" step="0.0001" value="${profile.max_cost_usd}"></label>
      <label>Целевых уникальных результатов на query<input data-field="target_results" type="number" min="1" max="100" value="${profile.target_results}"></label>
      <label>Максимум providers на query<input data-field="max_providers_per_query" type="number" min="1" max="3" value="${profile.max_providers_per_query}"></label>
      <label>Максимум query-вариантов<input data-field="max_queries" type="number" min="1" max="100" value="${profile.max_queries}"></label>
      <label>Результатов с provider на query<input data-field="results_per_query" type="number" min="1" max="30" value="${profile.results_per_query}"></label>
      <label>Candidate pool<input data-field="max_candidates" type="number" min="1" max="500" value="${profile.max_candidates}"></label>
      <label>Output limit<input data-field="output_limit" type="number" min="1" max="100" value="${profile.output_limit}"></label>
      <label>Minimum pre-score<input data-field="minimum_pre_score" type="number" min="0" max="100" value="${profile.minimum_pre_score}"></label>
      <label>Deep audit from<input data-field="deep_audit_score" type="number" min="0" max="100" value="${profile.deep_audit_score}"></label>
      <label>Concurrency<input data-field="concurrency" type="number" min="1" max="12" value="${profile.concurrency}"></label>
    `;
    return article;
  }

  function renderCatalog() {
    catalogNode.replaceChildren();
    catalog.forEach(item => {
      const card = document.createElement('article');
      card.className = 'mission-card';
      card.innerHTML = `<strong>${item.label}</strong><div>${item.description}</div><div class="message">${item.id} · охват: ${item.coverage} · стоимость: ${item.cost_profile} · ${item.implemented ? 'реализовано' : 'planned'}</div>`;
      catalogNode.append(card);
    });
  }

  function render(record) {
    state = record.settings;
    const global = state.global_settings;
    const profiles = Object.values(state.tariffs);

    activeTariff.innerHTML = profiles.map(p => `<option value="${p.id}" ${p.id === global.active_tariff ? 'selected' : ''}>${p.label}</option>`).join('');
    defaultStrategy.innerHTML = strategyOptions(global.default_strategy);
    emergencyStrategy.innerHTML = strategyOptions(global.emergency_strategy_override || '', true);
    document.querySelector('#search-paid-policy').value = global.paid_policy;
    document.querySelector('#search-paid-fanout-policy').value = global.paid_fanout_policy;
    document.querySelector('#search-hard-rub').value = global.hard_max_cost_rub;
    document.querySelector('#search-hard-usd').value = global.hard_max_cost_usd;
    [...providersSelect.options].forEach(option => { option.selected = global.enabled_providers.includes(option.value); });

    tariffsNode.replaceChildren(...profiles.map(tariffCard));
    updated.textContent = record.updated_at
      ? `Последнее изменение: ${record.updated_at} · admin user ${record.updated_by ?? '—'} · ${record.reason || ''}`
      : 'Используются безопасные базовые тарифные профили; цены к ним не привязаны.';
  }

  function numberField(card, name) {
    return Number(card.querySelector(`[data-field="${name}"]`).value);
  }

  function collectTariffs() {
    const tariffs = {};
    tariffsNode.querySelectorAll('[data-tariff]').forEach(card => {
      const old = state.tariffs[card.dataset.tariff];
      const order = card.querySelector('[data-field="provider_order"]').value.split(',').map(v => v.trim()).filter(Boolean);
      tariffs[old.id] = {
        id: old.id,
        label: old.label,
        enabled: card.querySelector('[data-field="enabled"]').checked,
        strategy: card.querySelector('[data-field="strategy"]').value,
        provider_order: order,
        paid_policy: card.querySelector('[data-field="paid_policy"]').value,
        paid_fanout_policy: card.querySelector('[data-field="paid_fanout_policy"]').value,
        max_cost_rub: numberField(card, 'max_cost_rub'),
        max_cost_usd: numberField(card, 'max_cost_usd'),
        target_results: numberField(card, 'target_results'),
        max_providers_per_query: numberField(card, 'max_providers_per_query'),
        max_queries: numberField(card, 'max_queries'),
        results_per_query: numberField(card, 'results_per_query'),
        max_candidates: numberField(card, 'max_candidates'),
        output_limit: numberField(card, 'output_limit'),
        minimum_pre_score: numberField(card, 'minimum_pre_score'),
        deep_audit_score: numberField(card, 'deep_audit_score'),
        concurrency: numberField(card, 'concurrency'),
      };
    });
    return tariffs;
  }

  async function load() {
    setMessage('Загрузка стратегий…');
    try {
      const response = await fetch('/api/admin/search-strategies', {credentials: 'same-origin'});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      catalog = data.catalog || [];
      renderCatalog();
      render(data.record);
      setMessage('Стратегии и тарифные профили загружены.', 'success');
    } catch (error) {
      setMessage(`Не удалось загрузить стратегии: ${error.message}`, 'error');
    }
  }

  form.addEventListener('submit', async event => {
    event.preventDefault();
    const submit = form.querySelector('button[type="submit"]');
    submit.disabled = true;
    setMessage('Сохраняем стратегию…');
    const payload = {
      settings: {
        global_settings: {
          active_tariff: activeTariff.value,
          default_strategy: defaultStrategy.value,
          enabled_providers: selectedValues(providersSelect),
          canonical_provider_order: state.global_settings.canonical_provider_order,
          paid_policy: document.querySelector('#search-paid-policy').value,
          paid_fanout_policy: document.querySelector('#search-paid-fanout-policy').value,
          hard_max_cost_rub: Number(document.querySelector('#search-hard-rub').value || 0),
          hard_max_cost_usd: Number(document.querySelector('#search-hard-usd').value || 0),
          emergency_strategy_override: emergencyStrategy.value || null,
        },
        tariffs: collectTariffs(),
      },
      reason: document.querySelector('#search-strategy-reason').value.trim(),
    };

    try {
      const response = await fetch('/api/admin/search-strategies', {
        method: 'PUT',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken()},
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const reason = typeof data.detail === 'string' ? data.detail : data.detail?.reason;
        throw new Error(reason || `HTTP ${response.status}`);
      }
      render(data);
      setMessage('Стратегии сохранены. Новые Hunter-миссии используют активный тарифный профиль.', 'success');
      document.querySelector('#refresh-hunter-settings')?.click();
    } catch (error) {
      setMessage(`Стратегии не сохранены: ${error.message}`, 'error');
    } finally {
      submit.disabled = false;
    }
  });

  refresh?.addEventListener('click', load);
  load();
})();
