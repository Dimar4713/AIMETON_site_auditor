/* ── State ── */
let analysis = null;

/* ── DOM refs ── */
const f           = document.querySelector('#form');
const statusEl    = document.querySelector('#status');
const resultEl    = document.querySelector('#result');
const chatEl      = document.querySelector('#chat');
const analyzeBtn  = document.querySelector('#analyzeBtn');
const messages    = document.querySelector('#messages');
const historyEl   = document.querySelector('#history');
const historyList = document.querySelector('#historyList');

/* ── Marked config ── */
marked.setOptions({ breaks: true, gfm: true });

/* ── Helpers ── */
function esc(v) {
  return String(v ?? '').replace(/[&<>'"]/g, c =>
    ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[c]));
}

function setStatus(msg, loading) {
  statusEl.innerHTML = loading
    ? `<span class="spinner"></span>${esc(msg)}`
    : esc(msg);
}

/* ── History (localStorage) ── */
const HIST_KEY = 'aimeton_history';

function getHistory() {
  try { return JSON.parse(localStorage.getItem(HIST_KEY) || '[]'); }
  catch { return []; }
}

function saveToHistory(data) {
  let h = getHistory();
  // replace if same URL already exists
  h = h.filter(x => x.url !== data.url);
  h.unshift({ saved_at: new Date().toISOString(), ...data });
  if (h.length > 30) h.length = 30;
  localStorage.setItem(HIST_KEY, JSON.stringify(h));
  renderHistory();
}

function renderHistory() {
  const h = getHistory();
  if (!h.length) { historyEl.classList.add('hidden'); return; }
  historyEl.classList.remove('hidden');
  historyList.innerHTML = h.map((item, i) => {
    const score = item.commercial_opportunity?.score ?? '?';
    const date  = new Date(item.saved_at).toLocaleString('ru', { day:'2-digit', month:'2-digit', year:'2-digit', hour:'2-digit', minute:'2-digit' });
    return `
      <div class="history-item">
        <div class="history-item-info">
          <strong>${esc(item.company_name || item.url)}</strong>
          <span class="history-url">${esc(item.url)}</span>
          <span class="history-date">${date}</span>
        </div>
        <div class="history-item-actions">
          <span class="tag">${esc(score)}/100</span>
          <button class="btn-ghost btn-sm" onclick="loadFromHistory(${i})">Открыть</button>
          <button class="btn-ghost btn-sm btn-danger" onclick="deleteHistory(${i})" title="Удалить">✕</button>
        </div>
      </div>`;
  }).join('');
}

function loadFromHistory(i) {
  analysis = getHistory()[i];
  render();
  setStatus('Загружено из истории: ' + analysis.company_name);
  resultEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function deleteHistory(i) {
  const h = getHistory();
  h.splice(i, 1);
  localStorage.setItem(HIST_KEY, JSON.stringify(h));
  renderHistory();
}

document.querySelector('#clearHistoryBtn').onclick = () => {
  if (confirm('Очистить всю историю?')) {
    localStorage.removeItem(HIST_KEY);
    renderHistory();
  }
};

/* ── PDF export ── */
function exportPDF() {
  const btn = document.querySelector('#exportBtn');
  btn.disabled = true;
  btn.textContent = '⏳ Формирую PDF…';

  const name = (analysis?.company_name || 'report')
    .replace(/[^а-яёa-z0-9\s_-]/gi, '').trim().replace(/\s+/g, '_') || 'report';

  // Build a temporary container: analysis + chat (if any)
  const container = document.createElement('div');
  container.style.cssText = 'font-family:Inter,system-ui,sans-serif;color:#152033;padding:4px';

  // 1. Main report
  const reportClone = document.querySelector('#resultInner').cloneNode(true);
  container.appendChild(reportClone);

  // 2. Chat dialog (only if messages exist)
  const msgNodes = document.querySelectorAll('#messages .msg:not(.thinking)');
  if (msgNodes.length) {
    const sep = document.createElement('div');
    sep.style.cssText = 'margin:24px 0 12px;border-top:2px solid #dce3ee;padding-top:16px';
    sep.innerHTML = '<h2 style="margin:0 0 12px;font-size:16px;color:#152033">Диалог с консультантом</h2>';
    container.appendChild(sep);

    msgNodes.forEach(node => {
      const clone = node.cloneNode(true);
      // Flatten bubble styles for PDF readability
      clone.style.cssText = [
        'margin:8px 0',
        'padding:10px 14px',
        'border-radius:10px',
        'font-size:13px',
        'line-height:1.6',
        node.classList.contains('user')
          ? 'background:#e9eaff;text-align:right'
          : 'background:#f0f3f8'
      ].join(';');
      container.appendChild(clone);
    });
  }

  // The container MUST be rendered inside the real document in normal flow:
  //  - position:fixed/absolute -> html2pdf 0.10.1 produces a 0-height (blank) canvas.
  //  - detached element + windowWidth override -> html2canvas mismatches the real
  //    viewport width and clips content on the left (worse the wider the window).
  // So we attach it in-flow, scroll to top, and let html2canvas use real coords.
  // A full-screen overlay hides the brief on-page flash.
  container.style.cssText +=
    // 718px = A4 width (210mm=794px) minus the 10mm PDF margins on each side:
    // html2pdf does NOT shrink content to fit inside margins — it shifts it,
    // so a 794px-wide container gets its right edge pushed off the page.
    ';width:718px;max-width:718px;background:white;padding:20px;box-sizing:border-box;margin:0;';

  // В PDF сетка карточек — одноколоночная: html2pdf при переносе двигает
  // каждую карточку отдельно, и в 2-колоночной сетке появляются "дырки".
  const pdfStyle = document.createElement('style');
  pdfStyle.textContent =
    '.pdf-export-container .grid{display:block !important}' +
    '.pdf-export-container .grid > *{margin-bottom:12px}';
  container.classList.add('pdf-export-container');
  container.appendChild(pdfStyle);

  const overlay = document.createElement('div');
  overlay.style.cssText =
    'position:fixed;inset:0;z-index:99999;background:#f4f6fb;' +
    'display:flex;align-items:center;justify-content:center;' +
    'font:600 16px Inter,system-ui,sans-serif;color:#5b61e6;';
  overlay.textContent = '⏳ Формирую PDF…';

  document.body.appendChild(container);
  document.body.appendChild(overlay);
  const prevScroll = window.scrollY;
  window.scrollTo(0, 0);

  const cleanup = () => {
    container.remove();
    overlay.remove();
    window.scrollTo(0, prevScroll);
    btn.disabled = false;
    btn.innerHTML = '⬇ Скачать PDF';
  };

  try {
  html2pdf()
    .set({
      margin: [10, 10, 10, 10],
      filename: `AIMETON_${name}.pdf`,
      image: { type: 'jpeg', quality: 0.95 },
      html2canvas: { scale: 2, useCORS: true, logging: false },
      jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
      // Не разрывать карточки/панели между страницами PDF
      pagebreak: { mode: ['css', 'legacy'], avoid: ['.card', '.panel', '.company-card', '.export-row'] }
    })
    .from(container)
    .save()
    .finally(cleanup);
  } catch (err) {
    // Синхронная ошибка (например, html2pdf не загрузился) — убрать оверлей
    cleanup();
    alert('Не удалось сформировать PDF: ' + (err && err.message ? err.message : err));
  }
}

/* ── Analyze form ── */
f.onsubmit = async (e) => {
  e.preventDefault();
  analyzeBtn.disabled = true;
  setStatus('Исследуем экономические сигналы…', true);
  resultEl.classList.add('hidden');
  chatEl.classList.add('hidden');

  try {
    const r = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: document.querySelector('#url').value })
    });
    if (!r.ok) throw new Error((await r.json()).detail || 'Ошибка сервера');
    analysis = await r.json();
    render();
    saveToHistory(analysis);
    setStatus('Коммерческая возможность подготовлена');
  } catch (err) {
    setStatus('Ошибка: ' + err.message);
  } finally {
    analyzeBtn.disabled = false;
  }
};

/* ── Render results ── */
function render() {
  const o = analysis.commercial_opportunity;
  const p = analysis.action_package;

  const score = Number(o.score) || 0;
  const scoreClass = score >= 70 ? 'high' : score >= 40 ? 'mid' : 'low';

  resultEl.innerHTML = `
    <div class="export-row">
      <button class="btn-export" id="exportBtn" onclick="exportPDF()">
        ⬇ Скачать PDF
      </button>
    </div>

    <div id="resultInner">
      <!-- Company card -->
      <div class="company-card">
        <div class="company-card-body">
          <h2>${esc(analysis.company_name)}</h2>
          <a class="company-url" href="${esc(analysis.url)}" target="_blank" rel="noopener">${esc(analysis.url)}</a>
          <p class="company-summary">${esc(analysis.business_summary)}</p>
        </div>
        <div class="company-card-score">
          <div class="score-circle ${scoreClass}">${esc(o.score)}</div>
          <div class="score-label">${esc(o.qualification)}</div>
        </div>
      </div>

      <!-- Commercial opportunity -->
      <section class="panel">
        <h3>Коммерческая возможность — ${esc(o.opportunity_type)}</h3>
        <p><strong>Гипотеза проблемы</strong><br>${esc(o.problem_hypothesis)}</p>
        <p><strong>Рекомендуемое решение</strong><br>${esc(o.recommended_solution)}</p>
        <p><strong>Ожидаемая ценность</strong><br>${esc(o.expected_value)}</p>
      </section>

      <!-- Economic signals -->
      <h3>Экономические сигналы</h3>
      <div class="grid">
        ${analysis.economic_signals.map(s => `
          <article class="card">
            <span class="tag">Уверенность: ${esc(s.confidence)}</span>
            <h3>${esc(s.signal)}</h3>
            <p><strong>Основание</strong><br>${esc(s.evidence)}</p>
            <p><strong>Возможный эффект</strong><br>${esc(s.business_effect)}</p>
          </article>`).join('')}
      </div>

      <!-- AI agents -->
      <h3>Подходящие AI-инструменты</h3>
      <div class="grid">
        ${analysis.agents.map(a => `
          <article class="card">
            <span class="tag">${esc(a.priority)}</span>
            <h3>${esc(a.name)}</h3>
            <p>${esc(a.purpose)}</p>
            <strong>Польза</strong>
            <p>${esc(a.benefit)}</p>
          </article>`).join('')}
      </div>

      <!-- Action package -->
      <section class="panel">
        <h3>Пакет действия</h3>
        <p><strong>Предполагаемый ЛПР</strong><br>${esc(p.decision_maker_hypothesis)}</p>
        <p><strong>Основание для контакта</strong><br>${esc(p.contact_reason)}</p>
        <p><strong>Демонстрационный сценарий</strong></p>
        <ol>${p.demo_scenario.map(x => `<li>${esc(x)}</li>`).join('')}</ol>
        <p><strong>Первое сообщение</strong></p>
        <blockquote>${esc(p.first_message)}</blockquote>
        <p><strong>Следующий шаг</strong><br>${esc(p.next_action)}</p>
      </section>

      <!-- Assumptions -->
      <h3>Ограничения и предположения</h3>
      <ul>${analysis.risks_and_assumptions.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
    </div>
  `;

  resultEl.classList.remove('hidden');
  chatEl.classList.remove('hidden');
}

/* ── Chat ── */
function addMessage(text, role) {
  const d = document.createElement('div');
  d.className = 'msg ' + role;
  if (role === 'assistant') {
    d.innerHTML = marked.parse(text);
  } else {
    d.textContent = text;
  }
  messages.append(d);
  messages.scrollTop = messages.scrollHeight;
  return d;
}

document.querySelector('#chatForm').onsubmit = async (e) => {
  e.preventDefault();
  const q       = document.querySelector('#question');
  const chatBtn = document.querySelector('#chatBtn');
  const text    = q.value.trim();
  if (!text) return;
  q.value = '';
  chatBtn.disabled = true;

  addMessage(text, 'user');

  const thinking = document.createElement('div');
  thinking.className = 'msg assistant thinking';
  thinking.innerHTML = '<span class="spinner"></span> Формирую ответ…';
  messages.append(thinking);
  messages.scrollTop = messages.scrollHeight;

  try {
    const r = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ analysis, messages: [{ role: 'user', content: text }] })
    });
    const data = await r.json();
    thinking.remove();
    addMessage(data.reply, 'assistant');
  } catch (err) {
    thinking.remove();
    addMessage('Ошибка: ' + err.message, 'assistant');
  } finally {
    chatBtn.disabled = false;
    q.focus();
  }
};

/* ── Init ── */
renderHistory();
