(() => {
  const ui = window.AIMETON_MISSION_UI;
  if (!ui) throw new Error('mission_event_registry_unavailable');

  window.stateLabel = (stateName) => ui.state(stateName).label;
  window.eventLabel = (summary) => ui.event(summary).label;
  window.eventIcon = (summary, stateName) => ui.event(summary, stateName).icon;
  window.heartbeatLabel = (payload) => ui.heartbeat(payload && payload.heartbeat_status);
  window.reasonLabel = (reasonCode) => ui.reason(reasonCode);
  window.nextActionLabel = (nextAction) => ui.nextAction(nextAction);
})();
