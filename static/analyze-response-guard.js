/* Robust /api/analyze response handling.
 * Loaded after app.js and replaces only the analyze form handler.
 */
(() => {
  const form = document.querySelector('#form');
  const button = document.querySelector('#analyzeBtn');
  const urlInput = document.querySelector('#url');
  if (!form || !button || !urlInput) return;

  function responseError(response, payload, rawText) {
    const requestId = response.headers.get('x-request-id') || response.headers.get('x-correlation-id');
    const suffix = requestId ? ` · request ${requestId}` : '';
    const detail = payload?.detail || payload?.message;
    if (detail) return new Error(`${detail}${suffix}`);
    if (response.status === 502) return new Error(`Шлюз не получил корректный ответ от сервиса (HTTP 502)${suffix}`);
    if (response.status === 503) return new Error(`Сервис временно недоступен (HTTP 503)${suffix}`);
    if (response.status === 504) return new Error(`Анализ превысил время ожидания шлюза (HTTP 504)${suffix}`);
    if (response.status === 401 || response.status === 403) return new Error(`Сессия недействительна или недостаточно прав (HTTP ${response.status})${suffix}`);
    const compact = String(rawText || '').trim().replace(/\s+/g, ' ').slice(0, 180);
    return new Error(`${compact || `Сервер вернул пустой ответ (HTTP ${response.status})`}${suffix}`);
  }

  form.onsubmit = async (event) => {
    event.preventDefault();
    button.disabled = true;
    setStatus('Исследуем экономические сигналы…', true);
    resultEl.classList.add('hidden');
    chatEl.classList.add('hidden');

    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 180000);

    try {
      const response = await fetch('/api/analyze', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        credentials: 'same-origin',
        signal: controller.signal,
        body: JSON.stringify({ url: urlInput.value.trim() })
      });

      const rawText = await response.text();
      let payload = null;
      if (rawText.trim()) {
        try {
          payload = JSON.parse(rawText);
        } catch {
          if (response.ok) {
            throw new Error(`Сервис вернул повреждённый JSON (HTTP ${response.status})`);
          }
        }
      }

      if (!response.ok) throw responseError(response, payload, rawText);
      if (!payload || typeof payload !== 'object') {
        throw new Error(`Сервис завершил запрос без результата (HTTP ${response.status}). Повторите попытку; если ошибка повторится, нужен просмотр server logs.`);
      }

      analysis = payload;
      activeAnalysisId = ensureAnalysisId(analysis);
      setChatSession([]);
      renderChatSession();
      render();
      saveToHistory(analysis);
      setStatus('Коммерческая возможность подготовлена');
    } catch (error) {
      const message = error?.name === 'AbortError'
        ? 'Анализ не завершился за 3 минуты. Запрос остановлен; проверьте состояние mission/runtime и server logs.'
        : (error?.message || String(error));
      setStatus('Ошибка: ' + message);
    } finally {
      window.clearTimeout(timeout);
      button.disabled = false;
    }
  };

  const humanReport = document.createElement('script');
  humanReport.src = '/static/human-report.js?v=20260804a';
  humanReport.defer = true;
  document.head.appendChild(humanReport);
})();
