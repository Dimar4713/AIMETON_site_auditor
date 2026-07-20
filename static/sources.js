(() => {
  const esc = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[char]));

  function currentAnalysis() {
    try {
      const history = JSON.parse(localStorage.getItem('aimeton_history') || '[]');
      const visibleUrl = document.querySelector('#resultInner .company-url')?.textContent?.trim();
      return history.find((item) => item.url === visibleUrl) || history[0] || null;
    } catch {
      return null;
    }
  }

  function renderSources() {
    const root = document.querySelector('#resultInner');
    if (!root || root.querySelector('[data-aimeton-sources]')) return;
    const data = currentAnalysis();
    const sources = Array.isArray(data?.sources) ? data.sources : [];
    if (!sources.length) return;

    const signalRefs = new Map();
    (data.economic_signals || []).forEach((signal) => {
      (signal.source_ids || []).forEach((id) => {
        if (!signalRefs.has(id)) signalRefs.set(id, []);
        signalRefs.get(id).push(signal.signal);
      });
    });

    const section = document.createElement('section');
    section.className = 'panel';
    section.dataset.aimetonSources = 'true';
    section.innerHTML = `
      <h3>Источники и доказательства</h3>
      <p><small>Ссылки предназначены для ручного фактчекинга. Цитата должна дословно присутствовать в указанном источнике на дату проверки.</small></p>
      <ol>
        ${sources.map((source) => {
          const refs = signalRefs.get(source.id) || [];
          const checked = source.accessed_at
            ? new Date(source.accessed_at).toLocaleString('ru-RU')
            : 'не указана';
          return `<li style="margin-bottom:16px;overflow-wrap:anywhere">
            <strong>[${esc(source.id)}] ${esc(source.title)}</strong><br>
            <a href="${esc(source.url)}" target="_blank" rel="noopener noreferrer">${esc(source.url)}</a><br>
            <small>Проверено: ${esc(checked)} · Тип: ${esc(source.source_type || 'не указан')}</small>
            <blockquote style="margin:8px 0">${esc(source.evidence_quote || 'Цитата не указана')}</blockquote>
            ${refs.length ? `<small><strong>Подтверждает сигналы:</strong> ${refs.map(esc).join('; ')}</small>` : ''}
          </li>`;
        }).join('')}
      </ol>`;
    root.appendChild(section);

    const cards = root.querySelectorAll('.grid .card');
    (data.economic_signals || []).forEach((signal, index) => {
      const card = cards[index];
      if (!card || !signal.source_ids?.length || card.querySelector('.source-refs')) return;
      const refs = document.createElement('p');
      refs.className = 'source-refs';
      refs.innerHTML = `<strong>Источники:</strong> ${signal.source_ids.map((id) => `[${esc(id)}]`).join(', ')}`;
      card.appendChild(refs);
    });
  }

  const observer = new MutationObserver(renderSources);
  observer.observe(document.querySelector('#result'), { childList: true, subtree: true });
  document.addEventListener('DOMContentLoaded', renderSources);
})();
