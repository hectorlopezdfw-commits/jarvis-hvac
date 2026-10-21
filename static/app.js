const appDemo = {
  showLocked(message) {
    const loginForm = document.getElementById('login-form');
    const logoutButton = document.getElementById('logout-btn');
    const dashboard = document.getElementById('dashboard');
    const authMessage = document.getElementById('auth-message');
    loginForm.hidden = false;
    logoutButton.hidden = true;
    dashboard.hidden = true;
    dashboard.innerHTML = '';
    authMessage.textContent = message || 'Lead data stays private until you sign in.';
  },

  showUnlocked() {
    document.getElementById('login-form').hidden = true;
    document.getElementById('logout-btn').hidden = false;
    document.getElementById('dashboard').hidden = false;
    document.getElementById('auth-message').textContent = '';
  },

  async readDetail(response) {
    try {
      const body = await response.json();
      if (typeof body.detail === 'string' && body.detail) {
        return body.detail;
      }
    } catch (error) {
      return 'Authentication required';
    }
    return 'Authentication required';
  },

  async loadDashboard() {
    const response = await fetch('/api/dashboard', {
      headers: { 'Content-Type': 'application/json' },
    });
    if (response.status === 401 || response.status === 503) {
      this.showLocked(await this.readDetail(response));
      return false;
    }
    if (!response.ok) {
      this.showLocked('Unable to load the dashboard.');
      return false;
    }

    const summary = await response.json();
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
    this.showUnlocked();
    return true;
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

  async login(event) {
    event.preventDefault();
    const password = new FormData(event.target).get('password');
    const response = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    });
    if (!response.ok) {
      this.showLocked(await this.readDetail(response));
      return;
    }
    await this.loadDashboard();
  },

  async logout() {
    await fetch('/api/logout', { method: 'POST' });
    const form = document.getElementById('login-form');
    form.reset();
    this.showLocked('Dashboard locked.');
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
  document.getElementById('login-form').addEventListener('submit', appDemo.login.bind(appDemo));
  document.getElementById('logout-btn').addEventListener('click', appDemo.logout.bind(appDemo));
  await appDemo.loadDashboard();
});
