(() => {
  const form = document.querySelector('#hunter-settings-form');
  if (!form) return;

  const message = document.querySelector('#hunter-settings-message');
  const updated = document.querySelector('#hunter-settings-updated');
  const refresh = document.querySelector('#refresh-hunter-settings');

  function csrfToken() {
    const prefix = 'aimeton_csrf=';
    const part = document.cookie.split(';').map(value => value.trim()).find(value => value.startsWith(prefix));
    return part ? decodeURIComponent(part.slice(prefix.length)) : '';
  }

  function setMessage(text, kind = '') {
    message.textContent = text;
    message.className = `message ${kind}`.trim();
  }

  function value(id) {
    return Number(document.querySelector(id).value);
  }

  function fill(record) {
    const settings = record.settings || {};
    document.querySelector('#hunter-setting-max-queries').value = settings.max_queries ?? 20;
    document.querySelector('#hunter-setting-results-per-query').value = settings.results_per_query ?? 10;
    document.querySelector('#hunter-setting-max-candidates').value = settings.max_candidates ?? 100;
    document.querySelector('#hunter-setting-output-limit').value = settings.output_limit ?? 25;
    document.querySelector('#hunter-setting-minimum-pre-score').value = settings.minimum_pre_score ?? 35;
    document.querySelector('#hunter-setting-deep-audit-score').value = settings.deep_audit_score ?? 60;
    document.querySelector('#hunter-setting-concurrency').value = settings.concurrency ?? 4;
    document.querySelector('#hunter-setting-provider-strategy').value = settings.provider_strategy || 'fallback_first_nonempty';
    if (record.updated_at) {
      updated.textContent = `Последнее изменение: ${record.updated_at} · admin user ${record.updated_by ?? '—'} · ${record.reason || 'без комментария'}`;
    } else {
      updated.textContent = 'Используется базовый профиль: 20 запросов × 10 результатов, пул 100, выдача 25.';
    }
  }

  async function load() {
    setMessage('Загрузка настроек…');
    try {
      const response = await fetch('/api/admin/hunter-settings', {credentials: 'same-origin'});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      fill(await response.json());
      setMessage('Настройки Hunter загружены.', 'success');
    } catch (error) {
      setMessage(`Не удалось загрузить настройки: ${error.message}`, 'error');
    }
  }

  form.addEventListener('submit', async event => {
    event.preventDefault();
    const submit = form.querySelector('button[type="submit"]');
    submit.disabled = true;
    const payload = {
      settings: {
        max_queries: value('#hunter-setting-max-queries'),
        results_per_query: value('#hunter-setting-results-per-query'),
        max_candidates: value('#hunter-setting-max-candidates'),
        output_limit: value('#hunter-setting-output-limit'),
        minimum_pre_score: value('#hunter-setting-minimum-pre-score'),
        deep_audit_score: value('#hunter-setting-deep-audit-score'),
        concurrency: value('#hunter-setting-concurrency'),
        provider_strategy: 'fallback_first_nonempty',
      },
      reason: document.querySelector('#hunter-setting-reason').value.trim(),
    };
    setMessage('Сохраняем профиль Hunter…');
    try {
      const response = await fetch('/api/admin/hunter-settings', {
        method: 'PUT',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken(),
        },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const reason = typeof data.detail === 'string' ? data.detail : data.detail?.reason;
        throw new Error(reason || `HTTP ${response.status}`);
      }
      fill(data);
      setMessage('Профиль Hunter сохранён и применяется к новым поискам.', 'success');
    } catch (error) {
      setMessage(`Настройки не сохранены: ${error.message}`, 'error');
    } finally {
      submit.disabled = false;
    }
  });

  refresh?.addEventListener('click', load);
  load();
})();
