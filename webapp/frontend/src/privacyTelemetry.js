const storageKey = 'nh-privacy-safe-telemetry';
const allowedEvents = new Set(['zero_result_search', 'citation_click', 'correction_submission', 'answer_abstention', 'verified_research_task']);
const sensitiveKeys = new Set(['query', 'query_text', 'answer', 'source_span', 'email', 'name', 'note']);

export function recordPrivacySafeEvent(event, properties = {}) {
  if (!allowedEvents.has(event)) return;
  try {
    const events = JSON.parse(sessionStorage.getItem(storageKey) || '[]');
    const safeProperties = Object.fromEntries(Object.entries(properties).filter(([key, value]) =>
      !sensitiveKeys.has(key.toLowerCase()) && (value == null || ['string', 'number', 'boolean'].includes(typeof value))));
    events.push({ event, occurred_at: new Date().toISOString(), properties: safeProperties });
    sessionStorage.setItem(storageKey, JSON.stringify(events));
  } catch {
    // Telemetry is optional and must not interrupt research if session storage is unavailable.
  }
}

export function summarizePrivacySafeEvents() {
  try {
    return JSON.parse(sessionStorage.getItem(storageKey) || '[]').reduce((counts, item) => {
      if (allowedEvents.has(item.event)) counts[item.event] = (counts[item.event] || 0) + 1;
      return counts;
    }, {});
  } catch {
    return {};
  }
}
