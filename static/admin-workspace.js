const adminBox = document.querySelector('#session-admin');
const usersBox = document.querySelector('#admin-users');
const missionsBox = document.querySelector('#admin-missions');
const auditBox = document.querySelector('#admin-audit');

function cookie(name) {
  return document.cookie.split('; ').find((item) => item.startsWith(`${name}=`))?.split('=').slice(1).join('=') || '';
}

async function api(path, options = {}) {
  const response = await fetch(path, {credentials: 'same-origin', ...options});
  if (response.status === 401) {
    window.location.replace('/login');
    throw new Error('unauthenticated');
  }
  if (response.status === 403 && !options.allowPolicyError) {
    document.body.replaceChildren(Object.assign(document.createElement('main'), {
      className: 'auth-card',
      textContent: 'Административный доступ запрещён для текущей роли.',
    }));
    throw new Error('role_forbidden');
  }
  return response;
}

function card(titleText, lines) {
  const node = document.createElement('article');
  node.className = 'mission-card';
  const title = document.createElement('h3');
  title.textContent = titleText;
  node.append(title);
  for (const line of lines) {
    const p = document.createElement('p');
    p.textContent = line;
    node.append(p);
  }
  return node;
}

async function loadSession() {
  const response = await api('/api/auth/me');
  if (!response.ok) throw new Error('session_unavailable');
  const user = await response.json();
  if (user.role !== 'admin') throw new Error('role_forbidden');
  adminBox.textContent = `${user.username} · admin`;
}

async function changeUserState(user) {
  const reason = window.prompt(`Причина: ${user.is_active ? 'блокировка' : 'разблокировка'} ${user.username}`)?.trim();
  if (!reason) return;
  const csrf = decodeURIComponent(cookie('aimeton_csrf'));
  const response = await api(`/api/auth/admin/users/${user.id}/state`, {
    method: 'PATCH',
    allowPolicyError: true,
    headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
    body: JSON.stringify({active: !user.is_active, reason}),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    window.alert(payload?.detail?.reason || `Операция отклонена (${response.status})`);
    return;
  }
  await Promise.all([loadUsers(), loadAudit()]);
}

async function loadUsers() {
  usersBox.textContent = 'Загрузка…';
  const response = await api('/api/auth/admin/users');
  if (!response.ok) {
    usersBox.textContent = `Не удалось загрузить пользователей (${response.status}).`;
    return;
  }
  const users = await response.json();
  usersBox.replaceChildren(...users.map((user) => {
    const node = card(user.username, [
      `ID: ${user.id}`,
      `Роль: ${user.role}`,
      `Состояние: ${user.is_active ? 'активен' : 'заблокирован'}`,
    ]);
    const button = document.createElement('button');
    button.className = 'secondary';
    button.textContent = user.is_active ? 'Заблокировать' : 'Разблокировать';
    button.addEventListener('click', () => changeUserState(user));
    node.append(button);
    return node;
  }));
}

async function loadMissions() {
  missionsBox.textContent = 'Загрузка…';
  const response = await api('/api/admin/missions');
  if (!response.ok) {
    missionsBox.textContent = `Не удалось загрузить миссии (${response.status}).`;
    return;
  }
  const missions = await response.json();
  missionsBox.replaceChildren(...missions.map((mission) => card(mission.title, [
    `Mission: ${mission.id}`,
    `Owner: ${mission.owner_id}`,
    `Цель: ${mission.target_ref}`,
    `Состояние: ${mission.state}`,
  ])));
}

async function loadAudit() {
  auditBox.textContent = 'Загрузка…';
  const response = await api('/api/auth/admin/audit-events?limit=100');
  if (!response.ok) {
    auditBox.textContent = `Не удалось загрузить журнал (${response.status}).`;
    return;
  }
  const events = await response.json();
  auditBox.replaceChildren(...events.map((event) => card(event.action, [
    `Event: ${event.id}`,
    `Actor: ${event.actor_id}`,
    `Target: ${event.target_user_id ?? '—'}`,
    `Result: ${event.result}`,
    `Reason: ${event.reason}`,
    `UTC: ${event.created_at}`,
  ])));
}

document.querySelector('#refresh-users').addEventListener('click', loadUsers);
document.querySelector('#refresh-missions').addEventListener('click', loadMissions);
document.querySelector('#refresh-audit').addEventListener('click', loadAudit);
Promise.all([loadSession(), loadUsers(), loadMissions(), loadAudit()]).catch(() => {});
