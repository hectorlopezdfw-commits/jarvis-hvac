const appDemo = {
  async loadDashboard() {
    const summary = await this.fetchJson('/api/dashboard');
    const container = document.getElementById('dashboard');
    const cards = [
      { label: 'Total leads', value: summary.total_leads },
      { label: 'Booked', value: summary.booked_leads },
      { label: 'Emergency', value: summary.emergency_leads },
      { label: 'Avg priority', value: summary.avg_priority },
      { label: 'Open leads', value: summary.open_leads },
    ];

    container.innerHTML = cards
      .map((card) => `
        <div class="metric">
          <span class="label">${card.label}</span>
          <span class="value">${card.value}</span>
        </div>
      `)
      .join('');
  },

  async fetchJson(url, options = {}) {
    const response = await fetch(url, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(error || 'Request failed');
    }

    return response.json();
  },

  async qualifyLead(payload) {
    const result = await this.fetchJson('/api/ai/qualify', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    document.getElementById('response-output').textContent = JSON.stringify(result, null, 2);
  },

  async submitLead(event) {
    event.preventDefault();
    const form = new FormData(event.target);
    const payload = Object.fromEntries(form.entries());
    payload.emergency = payload.emergency === 'true';

    try {
      const result = await this.fetchJson('/api/leads', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      document.getElementById('response-output').textContent = JSON.stringify(result, null, 2);
      await this.loadDashboard();
      await this.qualifyLead(payload);
    } catch (error) {
      document.getElementById('response-output').textContent = `Error: ${error.message}`;
    }
  },
};

document.addEventListener('DOMContentLoaded', async () => {
  const form = document.getElementById('lead-form');
  form.addEventListener('submit', appDemo.submitLead.bind(appDemo));
  await appDemo.loadDashboard();
});
