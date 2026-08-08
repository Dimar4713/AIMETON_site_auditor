(() => {
  'use strict';

  const form = document.querySelector('#temporary-access-form');
  const list = document.querySelector('#temporary-access-list');
  const message = document.querySelector('#temporary-access-message');
  const issuedBox = document.querySelector('#temporary-access-issued');
  const issuedLink = document.querySelector('#temporary-access-issued-link');
  const copyButton = document.querySelector('#temporary-access-copy');
  const refreshButton = document.querySelector('#refresh-temporary-access');
  if (!form || !list || !message || !issuedBox || !issuedLink || !copyButton || !refreshButton) return;

  function cookie(name) {
    return document.cookie.split('; ').find((item) => item.startsWith(`${name}=`))?.split('=').slice(1).join('=') || '';
  }

  async function api(path, options = {}) {
    return fetch(path, {credentials: 'same-origin', ...options});
  }

  function formatUtc(value) {
    if (!value) return '—';
    const date = new Date(value);
    return Number.isFinite(date.getTime()) ? date.toLocaleString('ru-RU') : value;
  }

  function card(item) {
    const node = document.createElement('article');
    node.className = 'mission-card';
    const title = document.createElement('h3');
    title.textContent = item.label || `Доступ #${item.id}`;
    const lines = [
      `ID: ${item.id}`,
      `Пользователь ID: ${item.subject_user_id}`,
      `Назначение: ${item.purpose}`,
      `Действует до: ${formatUtc(item.expires_at)}`,
      `Использовано: ${item.uses_count}/${item.max_uses}`,
      `Состояние: ${item.revoked_at ? 'отозван' : 'активен'}`,
    ];
    node.append(title);
    lines.forEach((text) => {
      const p = document.createElement('p');
      p.textContent = text;
      node.append(p);
    });
    if (!item.revoked_at) {
      const revoke = document.createElement('button');
      revoke.type = 'button';
      revoke.className = 'secondary';
      revoke.textContent = 'Отозвать доступ';
      revoke.addEventListener('click', () => revokeAccess(item.id));
      node.append(revoke);
    }
    return node;
  }

  async function loadAccess() {
    list.textContent = 'Загрузка…';
    const response = await api('/api/auth/admin/temporary-access-tokens');
    if (!response.ok) {
      list.textContent = `Не удалось загрузить временные доступы (${response.status}).`;
      return;
    }
    const items = await response.json();
    if (!items.length) {
      list.textContent = 'Временные доступы ещё не выдавались.';
      return;
    }
    list.replaceChildren(...items.map(card));
  }

  async function issueAccess(event) {
    event.preventDefault();
    issuedBox.hidden = true;
    issuedLink.value = '';
    message.textContent = 'Создание ссылки…';
    const csrf = decodeURIComponent(cookie('aimeton_csrf'));
    const payload = {
      subject_user_id: Number(document.querySelector('#temporary-access-user-id').value),
      label: document.querySelector('#temporary-access-label').value.trim(),
      purpose: document.querySelector('#temporary-access-purpose').value,
      ttl_minutes: Number(document.querySelector('#temporary-access-ttl').value),
      max_uses: Number(document.querySelector('#temporary-access-max-uses').value),
      reason: document.querySelector('#temporary-access-reason').value.trim(),
    };
    const response = await api('/api/auth/admin/temporary-access-tokens', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      message.textContent = body?.detail?.reason || `Создание отклонено (${response.status}).`;
      return;
    }
    const issued = await response.json();
    const link = `${window.location.origin}/${issued.magic_link_fragment}`;
    issuedLink.value = link;
    issuedBox.hidden = false;
    message.textContent = 'Ссылка создана. Она показана только сейчас — скопируйте и передайте адресату.';
    await loadAccess();
  }

  async function revokeAccess(id) {
    const reason = window.prompt('Причина отзыва временного доступа')?.trim();
    if (!reason) return;
    const csrf = decodeURIComponent(cookie('aimeton_csrf'));
    const response = await api(`/api/auth/admin/temporary-access-tokens/${id}/revoke`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
      body: JSON.stringify({reason}),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      window.alert(body?.detail?.reason || `Отзыв отклонён (${response.status}).`);
      return;
    }
    issuedBox.hidden = true;
    issuedLink.value = '';
    await loadAccess();
  }

  async function copyIssuedLink() {
    const value = issuedLink.value;
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      copyButton.textContent = 'Скопировано ✓';
      window.setTimeout(() => { copyButton.textContent = 'Копировать ссылку'; }, 1600);
    } catch (_error) {
      issuedLink.select();
      message.textContent = 'Автокопирование недоступно — ссылка выделена, скопируйте её вручную.';
    }
  }

  form.addEventListener('submit', issueAccess);
  refreshButton.addEventListener('click', loadAccess);
  copyButton.addEventListener('click', copyIssuedLink);
  loadAccess().catch(() => { list.textContent = 'Не удалось загрузить временные доступы.'; });
})();
