const adminBox = document.querySelector('#session-admin');
const usersBox = document.querySelector('#admin-users');
const missionsBox = document.querySelector('#admin-missions');

async function api(path) {
  const response = await fetch(path, {credentials: 'same-origin'});
  if (response.status === 401) {
    window.location.replace('/login');
    throw new Error('unauthenticated');
  }
  if (response.status === 403) {
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

async function loadUsers() {
  usersBox.textContent = 'Загрузка…';
  const response = await api('/api/auth/admin/users');
  if (!response.ok) {
    usersBox.textContent = `Не удалось загрузить пользователей (${response.status}).`;
    return;
  }
  const users = await response.json();
  usersBox.replaceChildren(...users.map((user) => card(user.username, [
    `ID: ${user.id}`,
    `Роль: ${user.role}`,
    `Состояние: ${user.is_active ? 'активен' : 'заблокирован'}`,
  ])));
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

document.querySelector('#refresh-users').addEventListener('click', loadUsers);
document.querySelector('#refresh-missions').addEventListener('click', loadMissions);
Promise.all([loadSession(), loadUsers(), loadMissions()]).catch(() => {});
