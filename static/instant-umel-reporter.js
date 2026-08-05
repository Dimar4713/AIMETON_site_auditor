(() => {
  const form = document.querySelector('#form');
  const statusNode = document.querySelector('#status');
  if (!form || !statusNode) return;

  form.addEventListener('submit', () => {
    const startedAt = performance.now();
    statusNode.innerHTML = `
      <div class="mission-reporter mission-reporter--optimistic" data-state="queued" role="status" aria-live="assertive" data-umel-event="mission.received" data-rendered-at-ms="${Math.round(startedAt)}">
        <div class="mission-reporter__head">
          <div>
            <div class="mission-reporter__title">Живой репортаж миссии</div>
            <div class="mission-reporter__meta">Миссия создаётся · прошло 0 сек.</div>
          </div>
          <span class="mission-reporter__state">В очереди</span>
        </div>
        <ol class="mission-reporter__events">
          <li class="mission-event" data-event-code="mission.received">
            <span aria-hidden="true">🧭</span>
            <div>
              <div class="mission-event__message">Задача принята. Создаём миссию.</div>
              <div class="mission-event__next">Далее: зарегистрировать mission_id и начать подключение к сайту.</div>
            </div>
          </li>
        </ol>
      </div>`;
  }, true);
})();
