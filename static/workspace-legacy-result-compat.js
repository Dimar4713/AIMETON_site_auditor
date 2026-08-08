(() => {
  window.addEventListener('aimeton:analysis-complete', event => {
    if (!event.detail?.result) return;
    document.querySelector('#resultInner')?.setAttribute('hidden', '');
  });
})();
