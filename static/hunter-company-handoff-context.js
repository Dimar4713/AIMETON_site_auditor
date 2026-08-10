(() => {
  const CONTEXT_ID = 'hunterCompanyHandoffContext';
  const LEAD_FIT_LABELS = {
    commercial_candidate: 'Коммерческий кандидат',
    unknown_candidate: 'Коммерческий статус не подтверждён',
    institutional_candidate: 'Институциональная организация',
  };

  function safeHost(value) {
    try {
      const url = new URL(String(value || ''));
      if (!['http:', 'https:'].includes(url.protocol)) return '';
      return url.hostname.toLowerCase().replace(/^www\./, '');
    } catch {
      return '';
    }
  }

  function contextNode() {
    let node = document.querySelector(`#${CONTEXT_ID}`);
    if (node) return node;
    const form = document.querySelector('#companyIntelligenceForm');
    if (!form) return null;
    node = document.createElement('aside');
    node.id = CONTEXT_ID;
    node.className = 'service-summary__item';
    node.setAttribute('aria-label', 'Выбранный кандидат');
    node.hidden = true;
    form.before(node);
    return node;
  }

  function clearContext() {
    const node = contextNode();
    if (!node) return;
    node.hidden = true;
    node.replaceChildren();
    const form = document.querySelector('#companyIntelligenceForm');
    if (form) {
      delete form.dataset.hunterLeadFit;
      delete form.dataset.hunterLeadFitReason;
    }
  }

  function renderContext() {
    const node = contextNode();
    if (!node) return;
    const form = document.querySelector('#companyIntelligenceForm');
    const name = document.querySelector('#companyName')?.value.trim() || '';
    const url = document.querySelector('#companyUrl')?.value.trim() || '';
    const region = document.querySelector('#companyRegion')?.value.trim() || '';
    const host = safeHost(url);
    const leadFit = form?.dataset.hunterLeadFit || '';
    const leadFitReason = form?.dataset.hunterLeadFitReason || '';

    const heading = document.createElement('strong');
    heading.textContent = 'Выбранный кандидат';

    const identity = document.createElement('div');
    identity.textContent = host ? `Компания по сайту ${host}` : (name || 'Компания не определена');

    const meta = document.createElement('div');
    meta.className = 'service-summary__meta';
    const parts = [];
    if (host) parts.push(`Сайт: ${host}`);
    if (region) parts.push(`Регион: ${region}`);
    if (LEAD_FIT_LABELS[leadFit]) parts.push(`Hunter: ${LEAD_FIT_LABELS[leadFit]}`);
    parts.push('Из поиска клиентов');
    meta.textContent = parts.join(' · ');

    node.replaceChildren(heading, identity, meta);
    if (leadFitReason) {
      const fitReason = document.createElement('div');
      fitReason.className = 'service-summary__meta';
      fitReason.textContent = `Основание приоритета: ${leadFitReason}`;
      node.append(fitReason);
    }
    if (name && host && name.toLowerCase() !== host.toLowerCase()) {
      const sourceName = document.createElement('div');
      sourceName.className = 'service-summary__meta';
      sourceName.textContent = `Название из поисковой выдачи: ${name}`;
      node.append(sourceName);
    }
    node.hidden = false;
  }

  document.addEventListener('click', event => {
    if (event.target.closest('.hunter-candidate-action')) {
      queueMicrotask(renderContext);
      return;
    }
    const card = event.target.closest('[data-service-card="company-intelligence"]');
    if (card) clearContext();
  });

  const status = document.querySelector('#companyIntelligenceStatus');
  if (status) {
    const observer = new MutationObserver(() => {
      if (status.textContent.trim() !== 'Профиль компании подготовлен.') return;
      const host = safeHost(document.querySelector('#companyUrl')?.value);
      if (host) status.textContent = `Профиль подготовлен для ${host}.`;
    });
    observer.observe(status, {childList: true, characterData: true, subtree: true});
  }
})();