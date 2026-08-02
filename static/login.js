const form = document.querySelector('#login-form');
const errorBox = document.querySelector('#login-error');

function reasonOf(payload, fallback) {
  const detail = payload && payload.detail;
  if (detail && typeof detail === 'object' && detail.reason) return detail.reason;
  return fallback;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  errorBox.hidden = true;
  const username = document.querySelector('#username').value.trim();
  const password = document.querySelector('#password').value;
  if (!username || !password) {
    errorBox.textContent = 'Заполните имя пользователя и пароль.';
    errorBox.hidden = false;
    return;
  }
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({username, password}),
  });
  if (response.ok) {
    window.location.assign('/workspace');
    return;
  }
  let payload = null;
  try { payload = await response.json(); } catch (_) {}
  const reason = reasonOf(payload, 'login_failed');
  errorBox.textContent = reason === 'unauthenticated'
    ? 'Неверное имя пользователя или пароль.'
    : `Вход не выполнен: ${reason}`;
  errorBox.hidden = false;
});
