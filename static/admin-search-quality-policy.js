(() => {
  const anchor = document.querySelector('#search-strategy-form');
  if (!anchor) return;

  const section = document.createElement('section');
  section.className = 'mission-card';
  section.innerHTML = `
    <h3>Пороговая политика качества Search Observer</h3>
    <p class="message">Это административные инварианты promotion gate. Пользователь их не видит: он выбирает только тактику поиска. Изменение этих значений само по себе не включает routing или steering.</p>
    <form id="search-quality-policy-form" class="auth-form">
      <label>Допустимое падение qualified yield, доля
        <input id="search-quality-qualified-drop" type="number" min="0" max="1" step="0.01" required>
      </label>
      <label>Допустимое падение direct/official yield, доля
        <input id="search-quality-direct-drop" type="number" min="0" max="1" step="0.01" required>
      </label>
      <label>Допустимый абсолютный рост waste ratio
        <input id="search-quality-waste-increase" type="number" min="0" max="1" step="0.01" required>
      </label>
      <label>Resource policy
        <input id="search-quality-resource-mode" value="existing_hard_caps" readonly>
      </label>
      <label>Причина изменения
        <input id="search-quality-reason" minlength="1" maxlength="500" value="Настройка административных порогов качества поиска" required>
      </label>
      <button type="submit">Сохранить пороги качества</button>
      <p id="search-quality-message" class="message" aria-live="polite"></p>
      <p id="search-quality-updated" class="message"></p>
    </form>
  `;
  anchor.after(section);

  const form = section.querySelector('#search-quality-policy-form');
  const message = section.querySelector('#search-quality-message');
  const updated = section.querySelector('#search-quality-updated');

  function csrfToken() {
    const prefix = 'aimeton_csrf=';
    const part = document.cookie.split(';').map(v => v.trim()).find(v => v.startsWith(prefix));
    return part ? decodeURIComponent(part.slice(prefix.length)) : '';
  }

  function setMessage(text, kind = '') {
    message.textContent = text;
    message.className = `message ${kind}`.trim();
  }

  function render(record) {
    const policy = record.policy || {};
    section.querySelector('#search-quality-qualified-drop').value = policy.max_qualified_yield_drop_ratio ?? 0;
    section.querySelector('#search-quality-direct-drop').value = policy.max_direct_or_official_yield_drop_ratio ?? 0;
    section.querySelector('#search-quality-waste-increase').value = policy.max_waste_ratio_increase ?? 0;
    section.querySelector('#search-quality-resource-mode').value = policy.resource_policy_mode || 'existing_hard_caps';
    updated.textContent = record.updated_at
      ? `Последнее изменение: ${record.updated_at} · admin user ${record.updated_by ?? '—'} · ${record.reason || ''}`
      : 'Используется консервативная quality-first политика: регрессии качества не допускаются; resource envelope — существующие hard caps.';
  }

  async function load() {
    setMessage('Загрузка порогов качества…');
    try {
      const response = await fetch('/api/admin/search-strategies/quality-policy', {credentials: 'same-origin'});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      render(await response.json());
      setMessage('Пороговая политика загружена.', 'success');
    } catch (error) {
      setMessage(`Не удалось загрузить пороги: ${error.message}`, 'error');
    }
  }

  form.addEventListener('submit', async event => {
    event.preventDefault();
    const submit = form.querySelector('button[type="submit"]');
    submit.disabled = true;
    setMessage('Сохраняем пороги качества…');
    const payload = {
      policy: {
        max_qualified_yield_drop_ratio: Number(section.querySelector('#search-quality-qualified-drop').value),
        max_direct_or_official_yield_drop_ratio: Number(section.querySelector('#search-quality-direct-drop').value),
        max_waste_ratio_increase: Number(section.querySelector('#search-quality-waste-increase').value),
        resource_policy_mode: section.querySelector('#search-quality-resource-mode').value,
      },
      reason: section.querySelector('#search-quality-reason').value.trim(),
    };
    try {
      const response = await fetch('/api/admin/search-strategies/quality-policy', {
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
      setMessage('Пороги сохранены. Это admin-policy; пользовательские режимы поиска не изменены.', 'success');
    } catch (error) {
      setMessage(`Пороги не сохранены: ${error.message}`, 'error');
    } finally {
      submit.disabled = false;
    }
  });

  load();
})();
