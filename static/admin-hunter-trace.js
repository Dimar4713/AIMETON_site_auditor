(() => {
  const grid = document.querySelector('.workspace-grid');
  if (!grid) return;

  const panel = document.createElement('section');
  panel.className = 'panel';
  panel.setAttribute('aria-labelledby', 'hunter-trace-title');
  panel.innerHTML = `
    <div class="panel-title">
      <h2 id="hunter-trace-title">Детальные поисковые трассы</h2>
      <button id="refresh-hunter-traces" class="secondary" type="button">Обновить</button>
    </div>
    <p class="message">Последние 7 суток. Видны безопасные этапы цепочки данных, query text, provider-состояния и счётчики. Secrets и raw provider payload не выводятся.</p>
    <div id="hunter-trace-recent" class="mission-list" aria-live="polite"></div>
  `;
  grid.append(panel);

  const recentBox = panel.querySelector('#hunter-trace-recent');

  function card(title, lines = []) {
    const node = document.createElement('article');
    node.className = 'mission-card';
    const h = document.createElement('h3');
    h.textContent = title;
    node.append(h);
    for (const text of lines) {
      const p = document.createElement('p');
      p.textContent = text;
      node.append(p);
    }
    return node;
  }

  async function getJson(path) {
    const response = await fetch(path, {credentials: 'same-origin'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  function metadataLines(metadata) {
    const lines = [];
    if (metadata?.query_text) lines.push(`Запрос: ${metadata.query_text}`);
    if (metadata?.original_region) lines.push(`Исходный регион: ${metadata.original_region}`);
    if (Array.isArray(metadata?.original_industries) && metadata.original_industries.length) {
      lines.push(`Исходная отрасль: ${metadata.original_industries.join(', ')}`);
    }
    if (metadata?.normalized_region) lines.push(`Нормализованный регион: ${metadata.normalized_region}`);
    if (Array.isArray(metadata?.normalized_industries) && metadata.normalized_industries.length) {
      lines.push(`Нормализованная отрасль: ${metadata.normalized_industries.join(', ')}`);
    }
    if (Array.isArray(metadata?.query_variants) && metadata.query_variants.length) {
      lines.push(`Варианты: ${metadata.query_variants.join(' | ')}`);
    }
    if (metadata?.query_intelligence) lines.push(`Query Intelligence: ${metadata.query_intelligence}`);
    return lines;
  }

  function closeOtherTimelines(activeHost) {
    recentBox.querySelectorAll('.hunter-trace-inline[data-open="true"]').forEach(host => {
      if (host === activeHost) return;
      host.replaceChildren();
      host.hidden = true;
      host.dataset.open = 'false';
      const button = host.parentElement?.querySelector('.hunter-trace-toggle');
      if (button) button.textContent = 'Открыть timeline';
    });
  }

  async function showTimeline(missionId, attemptId, host, button) {
    if (host.dataset.open === 'true') {
      host.replaceChildren();
      host.hidden = true;
      host.dataset.open = 'false';
      button.textContent = 'Открыть timeline';
      return;
    }

    closeOtherTimelines(host);
    host.hidden = false;
    host.dataset.open = 'loading';
    host.textContent = 'Загрузка timeline…';
    button.disabled = true;
    button.textContent = 'Загрузка…';
    host.scrollIntoView({behavior: 'smooth', block: 'nearest'});

    const base = `/api/admin/missions/${encodeURIComponent(missionId)}/trace/attempts/${encodeURIComponent(attemptId)}`;
    try {
      const events = await getJson(base);
      const nodes = events.map(event => {
        const lines = [
          `#${event.sequence} · ${event.component}/${event.operation} · ${event.state}`,
          `Причина: ${event.reason_code || '—'}`,
          `UTC: ${event.created_at}`,
        ];
        if (event.provider) lines.push(`Provider: ${event.provider}`);
        if (event.duration_ms != null) lines.push(`Latency: ${event.duration_ms} ms`);
        const counters = Object.entries(event.counters || {}).map(([key, value]) => `${key}=${value}`).join(', ');
        if (counters) lines.push(`Счётчики: ${counters}`);
        lines.push(...metadataLines(event.metadata || {}));
        return card(event.summary || event.operation, lines);
      });
      const heading = document.createElement('h3');
      heading.textContent = `Timeline · ${missionId}`;
      const download = document.createElement('a');
      download.className = 'secondary button-link';
      download.href = `${base}/bundle.jsonl`;
      download.textContent = 'Скачать JSONL трассу';
      host.replaceChildren(heading, download, ...nodes);
      host.dataset.open = 'true';
      button.textContent = 'Закрыть timeline';
      host.scrollIntoView({behavior: 'smooth', block: 'start'});
    } catch (error) {
      host.textContent = `Timeline недоступен: ${error.message}`;
      host.dataset.open = 'error';
      button.textContent = 'Повторить открытие';
      host.scrollIntoView({behavior: 'smooth', block: 'nearest'});
    } finally {
      button.disabled = false;
    }
  }

  async function loadRecent() {
    recentBox.textContent = 'Загрузка поисковых трасс…';
    try {
      const attempts = await getJson('/api/admin/missions/trace/recent-attempts?hours=168&limit=100');
      if (!attempts.length) {
        recentBox.textContent = 'За последние 7 суток trace-attempts не найдены.';
        return;
      }
      recentBox.replaceChildren(...attempts.map(item => {
        const node = card(item.mission_id, [
          `Attempt: ${item.attempt_id}`,
          `Событий: ${item.event_count}`,
          `Компоненты: ${(item.components || []).join(', ') || '—'}`,
          `Состояние: ${item.terminal_state || 'нет terminal state'}`,
          `Начало UTC: ${item.started_at}`,
          `Обновлено UTC: ${item.updated_at}`,
        ]);
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'secondary hunter-trace-toggle';
        button.textContent = 'Открыть timeline';

        const inlineTimeline = document.createElement('div');
        inlineTimeline.className = 'mission-list hunter-trace-inline';
        inlineTimeline.hidden = true;
        inlineTimeline.dataset.open = 'false';

        button.addEventListener('click', () => showTimeline(item.mission_id, item.attempt_id, inlineTimeline, button));
        node.append(button, inlineTimeline);
        return node;
      }));
    } catch (error) {
      recentBox.textContent = `Не удалось загрузить трассы: ${error.message}`;
    }
  }

  panel.querySelector('#refresh-hunter-traces').addEventListener('click', loadRecent);
  loadRecent();
})();
