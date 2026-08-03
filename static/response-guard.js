/* Guard legacy frontend from empty or non-JSON API responses. */
(() => {
  const nativeFetch = window.fetch.bind(window);

  window.fetch = async (...args) => {
    const response = await nativeFetch(...args);
    const request = args[0];
    const url = typeof request === 'string' ? request : request?.url || '';

    if (!url.includes('/api/analyze')) return response;

    const copy = response.clone();
    const text = await copy.text();
    if (text.trim()) return response;

    const status = response.ok ? 502 : response.status;
    const detail = response.ok
      ? 'Сервер анализа вернул пустой ответ. Проверьте состояние backend и повторите запуск.'
      : `Сервер анализа вернул пустой ответ (HTTP ${response.status}).`;

    return new Response(JSON.stringify({ detail }), {
      status,
      statusText: response.statusText || 'Empty API response',
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Cache-Control': 'no-store'
      }
    });
  };
})();
