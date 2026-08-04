(() => {
  const labels = {
    legal_name:'Юридическое название', brand_name:'Бренд', inn:'ИНН', ogrn:'ОГРН', registration_status:'Статус регистрации', address:'Адрес', phones:'Телефоны', emails:'Электронная почта', website:'Сайт', social_accounts:'Социальные сети', headcount:'Численность сотрудников', revenue:'Выручка', profit:'Прибыль', assets:'Активы', taxes:'Налоги', founders:'Учредители', executives:'Руководители', beneficial_owners:'Конечные владельцы', affiliates:'Связанные компании', geography:'География работы', products:'Продукты и услуги', customers:'Клиенты', suppliers:'Поставщики',
    schema_validated:'Данные собраны и прошли техническую проверку', preliminary_hypothesis:'Предварительная гипотеза', unresolved:'Компания пока не идентифицирована однозначно', partially_verified:'Проверено частично', not_searched:'Поиск ещё не выполнялся', unknown:'Не определено', active:'Работает', degraded:'Работает с ограничениями',
    preliminary_result:'Результат предварительный', identity_unresolved:'Юридическая идентификация компании не завершена', sufficiency_below_l4:'Недостаточно подтверждённых данных для окончательного вывода', mandatory_verticals_incomplete:'Не все обязательные направления исследования проверены', provider_state_unknown:'Статус части источников не подтверждён', budget_unknown:'Бюджет решения не оценён', human_review_and_signed_report_required:'Нужна экспертная проверка перед передачей клиенту', legacy_result_without_release_state:'Результат создан старым контуром анализа'
  };
  const tr = value => labels[String(value || '').trim()] || String(value || '').replaceAll('_',' ');

  function humanize() {
    const root = document.querySelector('#resultInner');
    if (!root) return;
    const panel = [...root.querySelectorAll('.panel')].find(node => node.textContent.includes('Состояние допустимости результата'));
    if (panel && panel.dataset.humanized !== 'true') {
      const text = panel.textContent || '';
      const pct = name => text.match(new RegExp(name + ':\\s*(\\d+)%'))?.[1] || '0';
      const priority = text.match(/Коммерческий приоритет:\s*([^·\n]+)/)?.[1]?.trim() || '—';
      const raw = [...panel.querySelectorAll('p')].find(p => p.textContent.includes('Блокеры:'))?.textContent.split('Блокеры:')[1] || '';
      const blockers = raw.split(',').map(x => x.trim()).filter(Boolean).map(tr);
      panel.innerHTML = `<h3>Насколько можно доверять результату</h3><p><strong>${text.includes('Выпуск клиенту: разрешён') ? 'Отчёт готов к передаче клиенту.' : 'Это предварительный рабочий результат.'}</strong></p><div class="human-readiness-grid"><div><span>Полнота сведений</span><strong>${pct('Полнота профиля')}%</strong></div><div><span>Подтверждённость источниками</span><strong>${pct('Качество evidence')}%</strong></div><div><span>Коммерческий потенциал</span><strong>${priority}</strong></div></div>${blockers.length ? `<div class="human-next-check"><strong>Что ещё требуется проверить</strong><ul>${blockers.map(x => `<li>${x}</li>`).join('')}</ul></div>` : ''}<details class="technical-details"><summary>Технические сведения для эксперта</summary><pre>${text.replace('Состояние допустимости результата','').trim()}</pre></details>`;
      panel.dataset.humanized = 'true';
    }
    root.querySelectorAll('.data-table tbody tr td:first-child, .card h3').forEach(node => { const key=node.textContent.trim(); if(labels[key]) node.textContent=labels[key]; });
  }

  const style=document.createElement('style');
  style.textContent='.human-readiness-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:16px 0}.human-readiness-grid>div{padding:12px;border:1px solid #e4e8f2;border-radius:12px;background:#f8f9ff}.human-readiness-grid span{display:block;color:#68708a;font-size:12px;margin-bottom:5px}.human-readiness-grid strong{font-size:18px}.human-next-check{margin-top:14px;padding:14px;border-left:4px solid #e0a100;background:#fff8db;border-radius:10px}.human-next-check ul{margin:8px 0 0;padding-left:20px}.technical-details{margin-top:14px;color:#68708a}.technical-details summary{cursor:pointer;font-size:13px}.technical-details pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace;background:#f4f6fb;padding:12px;border-radius:10px}@media(max-width:640px){.human-readiness-grid{grid-template-columns:1fr}.technical-details{display:none}}';
  document.head.appendChild(style);
  new MutationObserver(humanize).observe(document.querySelector('#result') || document.body,{childList:true,subtree:true});
  humanize();
})();
