/**
 * Singularity App Frontend Logic
 * Universal AI Gateway & Hub Client
 */

// Global State
const state = {
  currentTab: 'control',
  services: [],
  limits: {},
  models: [],
  activeCookieProvider: 'chatgpt',
  cookiesData: {},
  selectedModel: 'gpt-5-6-mini',
  chatMessages: [],
  isStreaming: false,
  tunnel: { status: 'offline', public_url: null, has_authtoken: false },
};

// ===================================================================
// Custom Toast Notification System (NO DEFAULT GOOGLE POPUPS)
// ===================================================================
function showToast(message, type = 'info', duration = 3500) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;

  const iconSvg = {
    success: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>',
    error: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>',
    info: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#d97757" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>',
  }[type] || '';

  toast.innerHTML = `
    ${iconSvg}
    <div class="toast-message">${escapeHtml(message)}</div>
    <button class="toast-close" title="Close">&times;</button>
  `;

  toast.querySelector('.toast-close').addEventListener('click', () => {
    toast.remove();
  });

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(-10px)';
    setTimeout(() => toast.remove(), 250);
  }, duration);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// ===================================================================
// Theme Toggle
// ===================================================================
function initTheme() {
  const themeToggle = document.getElementById('theme-checkbox');
  const saved = localStorage.getItem('singularity_theme') || 'dark';

  document.documentElement.setAttribute('data-theme', saved);
  themeToggle.checked = saved === 'dark';

  themeToggle.addEventListener('change', () => {
    const nextTheme = themeToggle.checked ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', nextTheme);
    localStorage.setItem('singularity_theme', nextTheme);
  });
}

// ===================================================================
// Device Simulation Toggle
// ===================================================================
async function initSimulationToggle() {
  const simToggle = document.getElementById('simulation-checkbox');
  if (!simToggle) return;

  try {
    const res = await fetch('/api/simulation');
    if (res.ok) {
      const data = await res.json();
      simToggle.checked = !!data.enabled;
    }
  } catch (e) {
    console.warn('Could not fetch simulation status:', e);
  }

  simToggle.addEventListener('change', async () => {
    try {
      const res = await fetch('/api/simulation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: simToggle.checked }),
      });
      if (res.ok) {
        const data = await res.json();
        showToast(
          data.enabled
            ? '⚡ Device Simulation Mode Enabled: Offline AI streaming verified without local daemons.'
            : '🔌 Device Simulation Mode Disabled: Connecting to live provider backends.',
          'info'
        );
        fetchServices();
      }
    } catch (e) {
      showToast('Failed to update simulation mode: ' + e.message, 'error');
    }
  });
}

// ===================================================================
// Navigation Tabs
// ===================================================================
function initNavigation() {
  const tabs = document.querySelectorAll('.nav-item');
  const sidebar = document.querySelector('.sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  const mobileToggle = document.getElementById('mobile-nav-toggle');

  const closeSidebar = () => {
    if (sidebar) sidebar.classList.remove('open');
    if (overlay) overlay.classList.remove('active');
  };

  const toggleSidebar = () => {
    if (sidebar) {
      const isOpen = sidebar.classList.toggle('open');
      if (overlay) overlay.classList.toggle('active', isOpen);
    }
  };

  if (mobileToggle) {
    mobileToggle.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      toggleSidebar();
    });
  }

  if (overlay) {
    ['click', 'touchstart', 'pointerdown'].forEach(evt => {
      overlay.addEventListener(evt, (e) => {
        e.preventDefault();
        e.stopPropagation();
        closeSidebar();
      }, { passive: false });
    });
  }

  // Also catch any click outside the sidebar when open on mobile
  document.addEventListener('click', (e) => {
    if (sidebar && sidebar.classList.contains('open')) {
      if (!sidebar.contains(e.target) && !mobileToggle?.contains(e.target)) {
        closeSidebar();
      }
    }
  });

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.tab;
      switchTab(target);
      if (window.innerWidth <= 1024) {
        closeSidebar();
      }
    });
  });
}

function switchTab(tabId) {
  state.currentTab = tabId;

  document.querySelectorAll('.nav-item').forEach(item => {
    item.classList.toggle('active', item.dataset.tab === tabId);
  });

  document.querySelectorAll('.tab-pane').forEach(pane => {
    pane.classList.toggle('active', pane.id === `pane-${tabId}`);
  });

  const heading = document.getElementById('page-heading');
  const subheading = document.getElementById('page-subheading');

  const titles = {
    control: {
      h: 'Control Center',
      sub: '',
    },
    limits: {
      h: 'Limits & Quotas',
      sub: 'Live feature quotas, rolling windows, and remaining queries by provider.',
    },
    models: {
      h: 'Available Models',
      sub: '',
    },
    cookies: {
      h: 'Cookie Stacker & Accounts',
      sub: '',
    },
    playground: {
      h: 'Interactive Playground',
      sub: 'Direct workbench to test streaming chat completions and reasoning traces across any provider.',
    },
    tunnel: {
      h: 'Singularity-Access',
      sub: '',
    },
  }[tabId] || { h: 'Singularity', sub: '' };

  heading.textContent = titles.h;
  subheading.textContent = titles.sub;
  subheading.style.display = titles.sub ? 'block' : 'none';

  if (tabId === 'limits') renderLimits();
  if (tabId === 'models') renderModels();
  if (tabId === 'cookies') loadCookiesTab();
  if (tabId === 'tunnel') loadTunnelTab();
}

// ===================================================================
// Control Center & Telemetry
// ===================================================================
async function fetchServices() {
  try {
    const res = await fetch('/api/services');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.services = data.services || [];
    renderServices();
    updateSidebarStatus(data.hub);
  } catch (err) {
    console.error('Error fetching services:', err);
    document.getElementById('hub-dot').className = 'status-dot offline';
    document.getElementById('hub-status-text').textContent = 'Gateway Offline';
  }
}

function renderServices() {
  const container = document.getElementById('providers-container');
  if (!container) return;

  const onlineCount = state.services.filter(s => s.running).length;
  document.getElementById('nav-active-count').textContent = `${onlineCount}/6 Active`;

  container.innerHTML = state.services.map(srv => {
    const isOnline = srv.running;
    const badgeClass = isOnline ? 'online' : 'offline';
    const badgeText = isOnline ? 'RUNNING' : 'STOPPED';

    const providerIcons = {
      gemini: '/static/icons/gemini.svg',
      chatgpt: '/static/icons/chatgpt.svg',
      claude: '/static/icons/claude.svg',
      kimi: '/static/icons/kimi.svg',
      glm: '/static/icons/glm.svg',
      grok: '/static/icons/grok.svg',
    };
    const iconUrl = providerIcons[srv.id] || '/logo.svg';

    return `
      <div class="provider-card" data-provider="${srv.id}">
        <div class="provider-card-top">
          <div class="provider-identity">
            <div class="provider-badge-icon">
              <img src="${iconUrl}" alt="${escapeHtml(srv.name)}" />
            </div>
            <div>
              <div class="provider-name">${escapeHtml(srv.name)}</div>
              <div class="provider-company">${escapeHtml(srv.badge)}</div>
            </div>
          </div>
          <span class="provider-status-badge ${badgeClass}">${badgeText}</span>
        </div>

        <div class="provider-stats-row">
          <div class="stat-box">
            <span class="stat-label">Port</span>
            <span class="stat-value">:${srv.port}</span>
          </div>
          <div class="stat-box">
            <span class="stat-label">PID</span>
            <span class="stat-value">${srv.pid || '—'}</span>
          </div>
          <div class="stat-box">
            <span class="stat-label">Latency</span>
            <span class="stat-value">${srv.latency_ms !== null ? srv.latency_ms + 'ms' : 'Offline'}</span>
          </div>
        </div>

        <div class="provider-card-actions">
          ${
            isOnline
              ? `
                <button class="btn btn-secondary btn-sm" onclick="restartService('${srv.id}')">Restart</button>
                <button class="btn btn-danger btn-sm" onclick="stopService('${srv.id}')">Stop</button>
              `
              : `
                <button class="btn btn-primary btn-sm" onclick="startService('${srv.id}')">Start</button>
              `
          }
        </div>
      </div>
    `;
  }).join('');
}

function updateSidebarStatus(hub) {
  const dot = document.getElementById('hub-dot');
  const text = document.getElementById('hub-status-text');
  if (hub && hub.running) {
    dot.className = 'status-dot';
    text.textContent = 'Gateway Online';
  } else {
    dot.className = 'status-dot offline';
    text.textContent = 'Gateway Offline';
  }
}

async function startService(id) {
  try {
    showToast(`Starting ${id}...`, 'info');
    const res = await fetch(`/api/services/${id}/start`, { method: 'POST' });
    const data = await res.json();
    if (data.status === 'ok') {
      showToast(data.message, 'success');
    } else {
      showToast(data.message || 'Failed to start', 'error');
    }
    await fetchServices();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function stopService(id) {
  try {
    showToast(`Stopping ${id}...`, 'info');
    const res = await fetch(`/api/services/${id}/stop`, { method: 'POST' });
    const data = await res.json();
    if (data.status === 'ok') {
      showToast(data.message, 'success');
    } else {
      showToast(data.message || 'Failed to stop', 'error');
    }
    await fetchServices();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function restartService(id) {
  try {
    showToast(`Restarting ${id}...`, 'info');
    const res = await fetch(`/api/services/${id}/restart`, { method: 'POST' });
    const data = await res.json();
    if (data.status === 'ok') {
      showToast(data.message || `Restarted ${id}`, 'success');
    } else {
      showToast(data.message || `Could not restart ${id}`, 'warning');
    }
    await fetchServices();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function startAllServices() {
  try {
    showToast('Starting all 6 providers...', 'info');
    const res = await fetch('/api/services/start_all', { method: 'POST' });
    const data = await res.json();
    showToast('Start command dispatched to all providers.', 'success');
    setTimeout(fetchServices, 1500);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function stopAllServices() {
  try {
    showToast('Stopping all 6 providers...', 'info');
    const res = await fetch('/api/services/stop_all', { method: 'POST' });
    const data = await res.json();
    showToast('Stop command dispatched to all providers.', 'success');
    setTimeout(fetchServices, 1500);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// ===================================================================
// Limits & Quotas Section
// ===================================================================
async function fetchLimits() {
  try {
    const res = await fetch('/api/limits');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.limits = await res.json();
    if (state.currentTab === 'limits') {
      renderLimits();
    }
  } catch (err) {
    console.error('Error fetching limits:', err);
  }
}

function renderLimits() {
  const container = document.getElementById('limits-container');
  if (!container) return;

  const chatgpt = state.limits.chatgpt || {};
  const grok = state.limits.grok || {};
  const kimi = state.limits.kimi || {};
  const claude = state.limits.claude || {};
  const gemini = state.limits.gemini || {};
  const glm = state.limits.glm || {};

  // ChatGPT Accounts Table
  const chatgptRows = (chatgpt.accounts || []).map(acc => {
    return `
      <tr>
        <td style="font-weight: 600; font-family: var(--font-mono);">${escapeHtml(acc.email || 'Account')}</td>
        <td><span class="brand-badge">${escapeHtml(acc.type || 'FREE')}</span></td>
        <td><strong>${acc.image_quota !== undefined ? acc.image_quota : '—'}</strong></td>
        <td>${acc.reason_remaining !== undefined ? acc.reason_remaining : '—'}</td>
        <td>${acc.deep_research !== undefined ? acc.deep_research : '—'}</td>
        <td>${acc.file_upload !== undefined ? acc.file_upload : '—'}</td>
        <td style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(acc.restore_at || 'Active')}</td>
      </tr>
    `;
  }).join('');

  // Grok Rate limits and imagine quotas
  const grokData = grok.data || {};
  const grokLimits = grokData.rate_limits || {};
  const grokImagine = grokData.imagine_quota || {};
  const grokRows = Object.entries(grokLimits).map(([mod, item]) => {
    return `
      <tr>
        <td style="font-weight: 600; font-family: var(--font-mono);">${escapeHtml(mod)}</td>
        <td><strong>${item.remainingQueries || 0} / ${item.totalQueries || 0}</strong></td>
        <td>${Math.round((item.windowSizeSeconds || 0) / 3600)} Hours</td>
        <td><span class="lock-badge unlocked">Operational</span></td>
      </tr>
    `;
  }).join('');

  // Kimi Accounts Table and Quotas
  const kimiSummary = kimi.summary || {};
  const kimiRows = (kimi.accounts || []).map(acc => {
    return `
      <tr>
        <td style="font-weight: 600; font-family: var(--font-mono);">${escapeHtml(acc.name || acc.id || 'Kimi Account')}</td>
        <td><span class="brand-badge">${escapeHtml(acc.plan || 'Free')}</span></td>
        <td><strong>${escapeHtml(acc.research_today || '50 / 50')}</strong></td>
        <td>${escapeHtml(acc.deep_research || '1 / 1 left')}</td>
        <td>${escapeHtml(acc.ok_computer || '3 / 3 left')}</td>
        <td>${escapeHtml(acc.slides || '3 / 3 left')}</td>
        <td style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(acc.reset_date || 'Active')}</td>
        <td><span class="lock-badge ${acc.status === 'Active' ? 'unlocked' : 'locked'}">${escapeHtml(acc.status || 'Active')}</span></td>
      </tr>
    `;
  }).join('');

  container.innerHTML = `
    <!-- ChatGPT Section -->
    <div class="limits-group">
      <div class="limits-group-header">
        <div>
          <h3 style="font-size: 16px; font-weight: 700;">ChatGPT Account Pool Quotas</h3>
          <p style="font-size: 12px; color: var(--text-muted);">Loaded live via account pool (${chatgpt.accounts_count || 0} accounts active)</p>
        </div>
      </div>
      <div class="table-wrapper">
        <table class="editorial-table">
          <thead>
            <tr>
              <th>Account</th>
              <th>Plan</th>
              <th>Image Quota</th>
              <th>Reasoning</th>
              <th>Deep Res</th>
              <th>Uploads</th>
              <th>Quota Reset</th>
            </tr>
          </thead>
          <tbody>
            ${chatgptRows || '<tr><td colspan="7">No accounts loaded</td></tr>'}
          </tbody>
        </table>
      </div>
    </div>

    <!-- Grok Section -->
    <div class="limits-group">
      <div class="limits-group-header">
        <div>
          <h3 style="font-size: 16px; font-weight: 700;">Grok / xAI Limits & Imagine Tokens</h3>
          <p style="font-size: 12px; color: var(--text-muted);">Account UID: ${escapeHtml(grokData.account_uid && grokData.account_uid !== 'default' ? grokData.account_uid : 'No Account Integrated')}</p>
        </div>
      </div>
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 16px;">
        <div class="card" style="padding: 14px;">
          <div style="font-size: 11px; font-family: var(--font-mono); color: var(--text-muted);">IMAGINE PRO 1.5</div>
          <div style="font-size: 20px; font-weight: 700; color: var(--brand-primary); margin-top: 4px;">
            ${grokImagine.imagePro?.remainingQueries ?? 0} Queries
          </div>
          <div style="font-size: 11px; color: var(--text-muted);">Reset: ${grokImagine.imagePro?.nextAvailableAt ? new Date(grokImagine.imagePro.nextAvailableAt).toLocaleTimeString() : '—'}</div>
        </div>
        <div class="card" style="padding: 14px;">
          <div style="font-size: 11px; font-family: var(--font-mono); color: var(--text-muted);">VIDEO 720P GENERATION</div>
          <div style="font-size: 20px; font-weight: 700; color: var(--color-success); margin-top: 4px;">
            ${grokImagine.video720p?.remainingQueries ?? 0} Slots
          </div>
          <div style="font-size: 11px; color: var(--text-muted);">${(grokData.account_uid && grokData.account_uid !== 'default') ? '24-hour window' : 'No account integrated'}</div>
        </div>
      </div>
      <div class="table-wrapper">
        <table class="editorial-table">
          <thead>
            <tr>
              <th>Mode / Model</th>
              <th>Remaining Queries</th>
              <th>Rolling Window</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            ${grokRows || '<tr><td colspan="4">No quota data</td></tr>'}
          </tbody>
        </table>
      </div>
    </div>

    <!-- Kimi Section -->
    <div class="limits-group">
      <div class="limits-group-header">
        <div>
          <h3 style="font-size: 16px; font-weight: 700;">Kimi / Moonshot AI Live Limits & Feature Pool</h3>
          <p style="font-size: 12px; color: var(--text-muted);">Introspected live from upstream tokens (${kimi.accounts_count || 0} accounts active)</p>
        </div>
      </div>
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 16px;">
        <div class="card" style="padding: 14px;">
          <div style="font-size: 11px; font-family: var(--font-mono); color: var(--text-muted);">DAILY RESEARCH QUOTA</div>
          <div style="font-size: 20px; font-weight: 700; color: var(--brand-primary); margin-top: 4px;">
            ${kimiSummary.research_queries || '—'}
          </div>
          <div style="font-size: 11px; color: var(--text-muted);">Reset: Midnight CST</div>
        </div>
        <div class="card" style="padding: 14px;">
          <div style="font-size: 11px; font-family: var(--font-mono); color: var(--text-muted);">DEEP RESEARCH</div>
          <div style="font-size: 20px; font-weight: 700; color: var(--color-success); margin-top: 4px;">
            ${kimiSummary.deep_research ?? 0} Queries
          </div>
          <div style="font-size: 11px; color: var(--text-muted);">Multi-Step Synthesis</div>
        </div>
        <div class="card" style="padding: 14px;">
          <div style="font-size: 11px; font-family: var(--font-mono); color: var(--text-muted);">OK COMPUTER AGENT</div>
          <div style="font-size: 20px; font-weight: 700; color: #38bdf8; margin-top: 4px;">
            ${kimiSummary.ok_computer ?? 0} Tasks
          </div>
          <div style="font-size: 11px; color: var(--text-muted);">Autonomous Execution</div>
        </div>
        <div class="card" style="padding: 14px;">
          <div style="font-size: 11px; font-family: var(--font-mono); color: var(--text-muted);">SLIDES GENERATOR</div>
          <div style="font-size: 20px; font-weight: 700; color: #a78bfa; margin-top: 4px;">
            ${kimiSummary.slides ?? 0} Decks
          </div>
          <div style="font-size: 11px; color: var(--text-muted);">Presentation Maker</div>
        </div>
      </div>
      <div class="table-wrapper">
        <table class="editorial-table">
          <thead>
            <tr>
              <th>Account</th>
              <th>Plan & Tier</th>
              <th>Daily Research</th>
              <th>Deep Research</th>
              <th>Ok Computer</th>
              <th>Slides Gen</th>
              <th>Cycle Reset</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            ${kimiRows || '<tr><td colspan="8">No Kimi accounts active in vault</td></tr>'}
          </tbody>
        </table>
      </div>
    </div>

    <!-- Claude, Gemini & GLM Grid -->
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px;">
      <!-- Claude -->
      <div class="limits-group">
        <h3 style="font-size: 16px; font-weight: 700; margin-bottom: 12px;">Claude / Anthropic Limits</h3>
        <div style="display: flex; flex-direction: column; gap: 10px;">
          <div style="display: flex; justify-content: space-between; border-bottom: 1px solid var(--border-subtle); padding-bottom: 8px;">
            <span style="color: var(--text-secondary);">Active Sessions</span>
            <span style="font-weight: 600; color: ${(claude.data?.active_sessions || 0) > 0 ? 'var(--brand-primary)' : 'var(--text-muted)'};">${claude.data?.active_sessions ?? 0} Connected</span>
          </div>
          <div style="display: flex; justify-content: space-between; border-bottom: 1px solid var(--border-subtle); padding-bottom: 8px;">
            <span style="color: var(--text-secondary);">Message Context Limit</span>
            <span style="font-weight: 600;">${(claude.data?.active_sessions || 0) > 0 ? (claude.data?.rolling_window || '5-hour window') : 'No session'}</span>
          </div>
          <div style="display: flex; justify-content: space-between; border-bottom: 1px solid var(--border-subtle); padding-bottom: 8px;">
            <span style="color: var(--text-secondary);">Standard Models</span>
            <span class="lock-badge ${(claude.data?.active_sessions || 0) > 0 ? 'unlocked' : 'locked'}">${(claude.data?.active_sessions || 0) > 0 ? 'Sonnet 5 & 4.6 Unlocked' : 'No Session Stacked'}</span>
          </div>
          <div style="display: flex; justify-content: space-between; padding-top: 2px;">
            <span style="color: var(--text-secondary);">Opus 5 Status</span>
            <span class="lock-badge locked">Locked (Requires Pro)</span>
          </div>
        </div>
      </div>

      <!-- Gemini -->
      <div class="limits-group">
        <h3 style="font-size: 16px; font-weight: 700; margin-bottom: 12px;">Gemini Limits</h3>
        <div style="display: flex; flex-direction: column; gap: 10px;">
          <div style="display: flex; justify-content: space-between; border-bottom: 1px solid var(--border-subtle); padding-bottom: 8px;">
            <span style="color: var(--text-secondary);">RPM Free Tier</span>
            <span style="font-weight: 600;">${gemini.data?.rpm_limit || '15 RPM'}</span>
          </div>
          <div style="display: flex; justify-content: space-between; border-bottom: 1px solid var(--border-subtle); padding-bottom: 8px;">
            <span style="color: var(--text-secondary);">Daily Limit (RPD)</span>
            <span style="font-weight: 600;">${gemini.data?.rpd_limit || '1,500 RPD'}</span>
          </div>
          <div style="display: flex; justify-content: space-between; padding-top: 2px;">
            <span style="color: var(--text-secondary);">Portrait Pipeline</span>
            <span class="lock-badge unlocked">Auto-Crop Active</span>
          </div>
        </div>
      </div>

      <!-- GLM -->
      <div class="limits-group">
        <h3 style="font-size: 16px; font-weight: 700; margin-bottom: 12px;">GLM Zhipu AI Limits</h3>
        <div style="display: flex; flex-direction: column; gap: 10px;">
          <div style="display: flex; justify-content: space-between; border-bottom: 1px solid var(--border-subtle); padding-bottom: 8px;">
            <span style="color: var(--text-secondary);">Concurrency Slots</span>
            <span style="font-weight: 600;">${glm.data?.concurrency_slots || '50 Slots'}</span>
          </div>
          <div style="display: flex; justify-content: space-between; border-bottom: 1px solid var(--border-subtle); padding-bottom: 8px;">
            <span style="color: var(--text-secondary);">Guest Mode</span>
            <span class="lock-badge unlocked">Auto-Rotating</span>
          </div>
          <div style="display: flex; justify-content: space-between; padding-top: 2px;">
            <span style="color: var(--text-secondary);">Image Gen (CogView-4)</span>
            <span class="lock-badge unlocked">Available</span>
          </div>
        </div>
      </div>
    </div>
  `;
}

// ===================================================================
// Available Models Catalog
// ===================================================================
async function fetchModels() {
  try {
    const res = await fetch('/api/models');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.models = data.models || [];
    document.getElementById('nav-model-count').textContent = `${state.models.length} Models`;
    renderModels();
    renderCustomSelectOptions();
  } catch (err) {
    console.error('Error fetching models:', err);
  }
}

const PROVIDER_METAS = {
  chatgpt: { name: 'ChatGPT', icon: '/static/icons/chatgpt.svg' },
  claude: { name: 'Claude', icon: '/static/icons/claude.svg' },
  gemini: { name: 'Gemini', icon: '/static/icons/gemini.svg' },
  kimi: { name: 'Kimi', icon: '/static/icons/kimi.svg' },
  glm: { name: 'GLM', icon: '/static/icons/glm.svg' },
  grok: { name: 'Grok', icon: '/static/icons/grok.svg' },
};

let isScrollSpyLocked = false;
let scrollSpyUnlockTimer = null;

function initModelFilters() {
  const pills = document.querySelectorAll('#model-filter-pills .filter-btn');
  pills.forEach(btn => {
    btn.addEventListener('click', () => {
      const filter = btn.dataset.filter;

      pills.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      if (['chatgpt', 'claude', 'gemini', 'kimi', 'glm', 'grok'].includes(filter)) {
        const sec = document.getElementById(`models-section-${filter}`);
        const viewport = document.querySelector('.panel-viewport');
        if (sec && viewport) {
          isScrollSpyLocked = true;
          sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
          clearTimeout(scrollSpyUnlockTimer);
          scrollSpyUnlockTimer = setTimeout(() => {
            isScrollSpyLocked = false;
          }, 700);
          return;
        }
      }

      if (filter === 'all') {
        const viewport = document.querySelector('.panel-viewport');
        if (viewport) {
          isScrollSpyLocked = true;
          viewport.scrollTo({ top: 0, behavior: 'smooth' });
          clearTimeout(scrollSpyUnlockTimer);
          scrollSpyUnlockTimer = setTimeout(() => {
            isScrollSpyLocked = false;
          }, 700);
        }
      }

      renderModels();
    });
  });

  const searchInput = document.getElementById('model-search');
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      renderModels();
    });
  }

  initModelsScrollSpy();
}

function initModelsScrollSpy() {
  const viewport = document.querySelector('.panel-viewport');
  if (!viewport || viewport._hasScrollSpyAttached) return;
  viewport._hasScrollSpyAttached = true;

  viewport.addEventListener('scroll', () => {
    if (isScrollSpyLocked) return;

    const activePane = document.querySelector('.tab-pane.active');
    if (!activePane || activePane.id !== 'pane-models') return;

    const activeFilterBtn = document.querySelector('#model-filter-pills .filter-btn.active');
    const currentFilter = activeFilterBtn ? activeFilterBtn.dataset.filter : 'all';
    if (currentFilter === 'unlocked' || currentFilter === 'locked') return;

    // Near top -> highlight 'all'
    if (viewport.scrollTop < 60) {
      const allBtn = document.querySelector('#model-filter-pills .filter-btn[data-filter="all"]');
      if (allBtn && !allBtn.classList.contains('active')) {
        document.querySelectorAll('#model-filter-pills .filter-btn').forEach(b => b.classList.remove('active'));
        allBtn.classList.add('active');
      }
      return;
    }

    const sections = document.querySelectorAll('.provider-models-section');
    if (!sections.length) return;

    const viewportRect = viewport.getBoundingClientRect();
    const probeY = viewportRect.top + 90;

    let currentSectionProvider = null;
    sections.forEach(sec => {
      const rect = sec.getBoundingClientRect();
      if (rect.top <= probeY && rect.bottom > probeY) {
        currentSectionProvider = sec.dataset.provider;
      }
    });

    if (!currentSectionProvider && sections.length > 0) {
      if (viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < 30) {
        currentSectionProvider = sections[sections.length - 1].dataset.provider;
      }
    }

    if (currentSectionProvider) {
      const targetBtn = document.querySelector(`#model-filter-pills .filter-btn[data-filter="${currentSectionProvider}"]`);
      if (targetBtn && !targetBtn.classList.contains('active')) {
        document.querySelectorAll('#model-filter-pills .filter-btn').forEach(b => b.classList.remove('active'));
        targetBtn.classList.add('active');
      }
    }
  }, { passive: true });
}

function renderSingleModelCard(m) {
  const isLocked = m.locked;
  const lockBadge = isLocked
    ? `<span class="lock-badge locked">LOCKED</span>`
    : `<span class="lock-badge unlocked">UNLOCKED</span>`;

  const capsHtml = (m.capabilities || []).map(c => `<span class="cap-tag">${escapeHtml(c)}</span>`).join('');

  return `
    <div class="model-card ${isLocked ? 'locked-model' : ''}">
      <div class="model-header">
        <div>
          <div class="model-title">${escapeHtml(m.name)}</div>
          <div class="model-id-badge">${escapeHtml(m.id)}</div>
        </div>
        ${lockBadge}
      </div>

      <p class="model-desc">${escapeHtml(m.description || '')}</p>

      ${isLocked && m.reason ? `<div style="font-size: 11px; color: var(--color-warning); font-family: var(--font-mono);">${escapeHtml(m.reason)}</div>` : ''}

      <div class="model-capabilities">
        <span class="cap-tag" style="color: var(--brand-primary); font-weight: 600;">${escapeHtml((m.provider || '').toUpperCase())}</span>
        <span class="cap-tag">${escapeHtml(m.context || '')}</span>
        ${capsHtml}
      </div>

      <div class="model-card-footer">
        <span style="color: var(--text-muted); font-size: 11px;">Base: /v1/chat/completions</span>
        <button class="btn btn-secondary btn-sm" onclick="selectAndTestModel('${escapeHtml(m.id)}')">
          Test in Playground
        </button>
      </div>
    </div>
  `;
}

function renderModels() {
  const container = document.getElementById('models-container');
  if (!container) return;

  const activeFilterBtn = document.querySelector('#model-filter-pills .filter-btn.active');
  const filter = activeFilterBtn ? activeFilterBtn.dataset.filter : 'all';
  const query = (document.getElementById('model-search')?.value || '').toLowerCase().trim();

  const filtered = state.models.filter(m => {
    if (filter === 'unlocked' && m.locked) return false;
    if (filter === 'locked' && !m.locked) return false;

    if (query) {
      const matchName = m.name.toLowerCase().includes(query);
      const matchId = m.id.toLowerCase().includes(query);
      const matchDesc = (m.description || '').toLowerCase().includes(query);
      const matchCaps = (m.capabilities || []).some(c => c.toLowerCase().includes(query));
      if (!matchName && !matchId && !matchDesc && !matchCaps) return false;
    }

    return true;
  });

  const providerOrder = ['chatgpt', 'claude', 'gemini', 'kimi', 'glm', 'grok'];
  const grouped = {};
  providerOrder.forEach(p => grouped[p] = []);

  filtered.forEach(m => {
    const p = (m.provider || '').toLowerCase();
    if (!grouped[p]) grouped[p] = [];
    grouped[p].push(m);
  });

  let html = '';
  providerOrder.forEach(provider => {
    const list = grouped[provider] || [];
    if (list.length === 0) return;

    const meta = PROVIDER_METAS[provider] || { name: provider.toUpperCase(), icon: '' };

    html += `
      <section class="provider-models-section" id="models-section-${provider}" data-provider="${provider}">
        <div class="provider-section-header">
          <div class="provider-section-title">
            <img src="${meta.icon}" class="provider-section-icon" alt="${meta.name}" onerror="this.style.display='none'" />
            <h3 class="provider-section-name">${escapeHtml(meta.name)}</h3>
          </div>
          <span class="provider-section-count">${list.length} Models</span>
        </div>
        <div class="models-grid">
          ${list.map(m => renderSingleModelCard(m)).join('')}
        </div>
      </section>
    `;
  });

  if (!html) {
    html = `
      <div style="text-align: center; padding: 60px 20px; color: var(--text-muted);">
        <p style="font-size: 16px; margin-bottom: 8px;">No models found matching your criteria</p>
        <span style="font-size: 13px;">Try changing the filter or clearing the search box.</span>
      </div>
    `;
  }

  container.innerHTML = html;
}

function selectAndTestModel(modelId) {
  state.selectedModel = modelId;
  const label = document.getElementById('model-select-label');
  if (label) label.textContent = modelId;
  switchTab('playground');
  showToast(`Selected model: ${modelId}`, 'info');
  document.getElementById('chat-input')?.focus();
}

// ===================================================================
// Cookie Changer & Stacker Section
// ===================================================================
function initCookieTabs() {
  const tabs = document.querySelectorAll('#cookie-provider-tabs .provider-tab-btn');
  tabs.forEach(btn => {
    btn.addEventListener('click', () => {
      tabs.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.activeCookieProvider = btn.dataset.p;
      loadCookiesTab();
    });
  });

  const saveBtn = document.getElementById('btn-save-cookie');
  if (saveBtn) saveBtn.addEventListener('click', saveCookies);

  const exportBtn = document.getElementById('btn-export-cookies');
  if (exportBtn) exportBtn.addEventListener('click', exportAllCookies);

  const importBtn = document.getElementById('btn-import-cookies');
  const importInput = document.getElementById('import-file-input');
  if (importBtn && importInput) {
    importBtn.addEventListener('click', () => importInput.click());
    importInput.addEventListener('change', handleImportCookiesFile);
  }
}

function getRuleIconSvg(icon) {
  if (icon === 'users') {
    return `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>`;
  }
  if (icon === 'lock') {
    return `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>`;
  }
  if (icon === 'shield') {
    return `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>`;
  }
  return `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`;
}

const TOKEN_GUIDES = {
  chatgpt: {
    title: 'How to Extract ChatGPT Session Tokens',
    steps: [
      {
        num: '1',
        text: 'Sign in to your ChatGPT account at <a href="https://chatgpt.com" target="_blank" rel="noopener" class="token-guide-link">chatgpt.com</a> in a dedicated browser profile.'
      },
      {
        num: '2',
        text: 'In the exact same browser profile, open <a href="https://chatgpt.com/api/auth/session" target="_blank" rel="noopener" class="token-guide-link">chatgpt.com/api/auth/session</a>.'
      },
      {
        num: '3',
        text: 'Copy the full JSON response dump (or the <code>accessToken</code> string) and paste it into the box below.'
      }
    ],
    rules: [
      {
        icon: 'users',
        title: 'Create Separate Chrome Profiles',
        desc: 'Always create a separate, isolated Chrome profile for each ChatGPT account you stack to prevent session cookie collisions.'
      },
      {
        icon: 'lock',
        title: 'Never Click "Log Out"',
        desc: 'Do not log out of the account in your browser! Logging out immediately revokes your session token on OpenAI servers. Simply close the tab/window.'
      },
      {
        icon: 'shield',
        title: 'Do Not Use Your Main Account',
        desc: 'Never use your primary daily personal ChatGPT account. Use dedicated secondary or throwaway accounts for API pooling.'
      }
    ]
  },
  claude: {
    title: 'How to Extract Claude SessionKey',
    steps: [
      {
        num: '1',
        text: 'Sign in to <a href="https://claude.ai" target="_blank" rel="noopener" class="token-guide-link">claude.ai</a> in your browser.'
      },
      {
        num: '2',
        text: 'Open Chrome Developer Tools (press <code>F12</code> or right-click &rarr; Inspect) &rarr; navigate to <strong>Application</strong> &rarr; <strong>Cookies</strong> &rarr; <code>https://claude.ai</code>.'
      },
      {
        num: '3',
        text: 'Locate the cookie named <code>sessionKey</code> (starts with <code>sk-ant-sid02-...</code>), copy its entire string value, and paste it below.'
      }
    ],
    rules: [
      {
        icon: 'users',
        title: 'Separate Browser Profiles',
        desc: 'Use distinct browser profiles when managing multiple Claude accounts to keep session credentials fully independent.'
      },
      {
        icon: 'lock',
        title: 'Do Not Log Out',
        desc: 'Logging out terminates the sessionKey immediately on Anthropic authentication servers. Just close the browser tab.'
      },
      {
        icon: 'shield',
        title: 'Avoid Personal Main Accounts',
        desc: 'Use secondary/dedicated accounts so automated API calls do not burn through your personal conversation rate limits.'
      }
    ]
  },
  grok: {
    title: 'How to Extract Grok SSO Cookies',
    steps: [
      {
        num: '1',
        text: 'Log into <a href="https://grok.com" target="_blank" rel="noopener" class="token-guide-link">grok.com</a> or <a href="https://x.com" target="_blank" rel="noopener" class="token-guide-link">x.com</a> in your browser.'
      },
      {
        num: '2',
        text: 'Open DevTools (<code>F12</code>) &rarr; go to <strong>Application</strong> &rarr; <strong>Cookies</strong> &rarr; <code>https://grok.com</code>.'
      },
      {
        num: '3',
        text: 'Copy the values for <code>sso</code> and <code>sso-rw</code>, or paste your raw Cookie header string into the box below.'
      }
    ],
    rules: [
      {
        icon: 'users',
        title: 'Separate Browser Profiles',
        desc: 'Keep separate browser profiles for each X/Grok account to prevent cookie collisions and cross-account logouts.'
      },
      {
        icon: 'lock',
        title: 'Never Click Sign Out',
        desc: 'Signing out revokes the Twitter/X SSO session. Leave the session active and just close the window.'
      },
      {
        icon: 'shield',
        title: 'Dedicated Grok Accounts',
        desc: 'Avoid using your primary personal Twitter profile for heavy API querying.'
      }
    ]
  },
  kimi: {
    title: 'How to Extract Kimi JWT Refresh Tokens',
    steps: [
      {
        num: '1',
        text: 'Log into <a href="https://kimi.com" target="_blank" rel="noopener" class="token-guide-link">kimi.com</a> in your browser.'
      },
      {
        num: '2',
        text: 'Press <code>F12</code> &rarr; select <strong>Application</strong> &rarr; <strong>Local Storage</strong> &rarr; <code>https://kimi.com</code>.'
      },
      {
        num: '3',
        text: 'Copy the <code>access_token</code> or <code>refresh_token</code> string (starts with <code>eyJ...</code>) and paste it below.'
      }
    ],
    rules: [
      {
        icon: 'users',
        title: 'Separate Browser Profiles',
        desc: 'Use distinct browser profiles if stacking multiple Moonshot / Kimi accounts.'
      },
      {
        icon: 'lock',
        title: 'Keep Sessions Active',
        desc: 'Do not click sign out in the web interface; simply close the browser window.'
      },
      {
        icon: 'shield',
        title: 'Dedicated Phone Accounts',
        desc: 'Use dedicated numbers for high-throughput automated workloads.'
      }
    ]
  },
  gemini: {
    title: 'How to Extract Gemini Google Cookies',
    steps: [
      {
        num: '1',
        text: 'Sign in to <a href="https://gemini.google.com" target="_blank" rel="noopener" class="token-guide-link">gemini.google.com</a> in an isolated Google Chrome profile.'
      },
      {
        num: '2',
        text: 'Press <code>F12</code> (DevTools) &rarr; go to <strong>Application</strong> tab &rarr; <strong>Cookies</strong> &rarr; <code>https://gemini.google.com</code>.'
      },
      {
        num: '3',
        text: 'Copy the values for <code>__Secure-1PSID</code> and <code>__Secure-1PSIDTS</code> and paste formatted as: <code>__Secure-1PSID=...; __Secure-1PSIDTS=...</code>'
      }
    ],
    rules: [
      {
        icon: 'users',
        title: 'Dedicated Chrome Profiles',
        desc: 'CRITICAL: Always create a separate Chrome profile for each Google account to keep Google credentials isolated.'
      },
      {
        icon: 'lock',
        title: 'Never Click Sign Out',
        desc: 'Signing out immediately destroys Google security tickets across all apps. Just close the Chrome window.'
      },
      {
        icon: 'shield',
        title: 'Never Use Primary Google Account',
        desc: 'Do NOT use your personal Google account with private Gmail, Drive, Photos, or payment methods. Use dedicated burner/secondary Google accounts.'
      }
    ]
  }
};

async function loadCookiesTab() {
  try {
    const res = await fetch('/api/cookies');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.cookiesData = await res.json();
  } catch (err) {
    console.error('Error fetching cookies:', err);
  }

  // Update cross-device SQLite status badge
  let totalAccounts = 0;
  if (state.cookiesData) {
    Object.values(state.cookiesData).forEach(entry => {
      if (entry && Array.isArray(entry.accounts)) {
        totalAccounts += entry.accounts.length;
      }
    });
  }
  const syncBadge = document.getElementById('sync-db-status');
  if (syncBadge) {
    syncBadge.textContent = `${totalAccounts} Stacked`;
  }

  const p = state.activeCookieProvider;
  const pData = state.cookiesData[p] || { accounts: [] };

  const title = document.getElementById('cookie-input-title');
  const desc = document.getElementById('cookie-input-desc');
  const textarea = document.getElementById('cookie-textarea');

  const meta = {
    chatgpt: {
      title: 'ChatGPT Account Stacker',
      desc: 'Paste Next-Auth session JSON dumps or access tokens. Paste multiple accounts line-by-line to stack your pool.',
      placeholder: '{"accessToken": "eyJhbGci...", "user": {"email": "account@gmail.com"}}',
    },
    claude: {
      title: 'Claude SessionKey Stacker',
      desc: 'Paste sessionKey strings (sk-ant-sid02-...). Stacks multiple sessions into the Singularity Unified Vault (SQLite).',
      placeholder: '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',
    },
    grok: {
      title: 'Grok SSO Stacker',
      desc: 'Paste Grok cookie strings containing sso=... and x-userid=... (one per line).',
      placeholder: 'sso=...; sso-rw=...; x-userid=b9e803ff-94ed-46c1-88bd-4baf02c5ccfe',
    },
    kimi: {
      title: 'Kimi JWT Stacker',
      desc: 'Paste Kimi refresh token JWT (one per line). Stored securely in Singularity Unified Vault (SQLite).',
      placeholder: 'eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9...',
    },
    gemini: {
      title: 'Gemini Cookie Stacker',
      desc: 'Paste raw Google cookies containing __Secure-1PSID and __Secure-1PSIDTS (one per line).',
      placeholder: '__Secure-1PSID=...; __Secure-1PSIDTS=...',
    },
    glm: {
      title: 'GLM Token Stacker',
      desc: 'Paste Zhipu AI refresh tokens (one per line). Stored securely in Singularity Unified Vault (SQLite).',
      placeholder: 'Paste GLM refresh token line-by-line...',
    },
  }[p] || { title: 'Account Stacker', desc: '', placeholder: '' };

  title.textContent = meta.title;
  desc.textContent = meta.desc;
  textarea.placeholder = meta.placeholder;
  textarea.value = '';

  // Render dynamic Token Extraction & Safety Guide (GLM has no guide)
  const guideCard = document.getElementById('token-guide-card');
  const guide = TOKEN_GUIDES[p];

  if (!guide || p === 'glm') {
    if (guideCard) guideCard.style.display = 'none';
  } else {
    if (guideCard) {
      guideCard.style.display = 'flex';
      guideCard.innerHTML = `
        <div class="token-guide-header">
          <div class="token-guide-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--brand-primary)" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="16" x2="12" y2="12"></line>
              <line x1="12" y1="8" x2="12.01" y2="8"></line>
            </svg>
            <span>${escapeHtml(guide.title)}</span>
          </div>
        </div>

        <div class="token-guide-steps">
          ${guide.steps.map(s => `
            <div class="token-step-item">
              <span class="token-step-num">${s.num}</span>
              <div>${s.text}</div>
            </div>
          `).join('')}
        </div>

        <div class="token-guide-rules">
          <div class="token-rules-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--brand-primary)" stroke-width="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
            </svg>
            <span>Session Stability & Account Safeguards</span>
          </div>
          <div class="token-rules-list">
            ${guide.rules.map(r => `
              <div class="token-rule-item">
                <span class="token-rule-icon-wrap">${getRuleIconSvg(r.icon)}</span>
                <div class="token-rule-text">
                  <strong>${escapeHtml(r.title)}:</strong>
                  <span>${escapeHtml(r.desc)}</span>
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }
  }

  // Render active stacked accounts
  const listContainer = document.getElementById('stacked-accounts-list');
  const accounts = pData.accounts || [];

  if (accounts.length === 0) {
    listContainer.innerHTML = `
      <div class="card" style="padding: 16px; color: var(--text-muted); text-align: center; font-size: 13px;">
        No active stacked accounts found for ${p.toUpperCase()}. Paste new credentials above to stack.
      </div>
    `;
    return;
  }

  listContainer.innerHTML = accounts.map((acc, idx) => {
    const label = acc.email || acc.name || acc.masked || `Account #${idx + 1}`;
    const sub = acc.plan ? `Plan: ${acc.plan.toUpperCase()} • Status: ${acc.status || 'Active'}` : (acc.masked || 'Active Session');
    const ident = acc.identifier || acc.email || acc.sessionKey || acc.token || acc.raw || '';

    return `
      <div class="account-card">
        <div class="account-card-info">
          <div class="account-card-title">${escapeHtml(label)}</div>
          <div class="account-card-desc">${escapeHtml(sub)}</div>
        </div>
        <div class="account-card-actions">
          <span class="lock-badge unlocked">STACKED</span>
          <button class="btn-remove-acc" onclick="removeStackedAccount('${p}', ${acc.id != null ? acc.id : idx}, '${escapeHtml(ident)}')" title="Remove this account">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"></polyline>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
              <line x1="10" y1="11" x2="10" y2="17"></line>
              <line x1="14" y1="11" x2="14" y2="17"></line>
            </svg>
            <span>Remove</span>
          </button>
        </div>
      </div>
    `;
  }).join('');
}

async function removeStackedAccount(provider, index, identifier) {
  if (!confirm(`Are you sure you want to remove this account from ${provider.toUpperCase()}?`)) {
    return;
  }

  try {
    showToast(`Removing account from ${provider.toUpperCase()}...`, 'info');
    const res = await fetch(`/api/cookies/${provider}/remove`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ index: index, identifier: identifier, id: index }),
    });
    const data = await res.json();
    if (data.status === 'ok') {
      showToast(data.message, 'success');
      await loadCookiesTab();
      // Also refresh limits tab in background
      try {
        const limRes = await fetch('/api/limits');
        if (limRes.ok) {
          state.limits = await limRes.json();
          renderLimits();
        }
      } catch (_) {}

      // Restart daemon to apply removal if currently running
      const srv = state.services?.find(s => s.id === provider);
      if (srv && srv.running) {
        setTimeout(() => {
          showToast(`Restarting ${provider} daemon to apply changes...`, 'info');
          restartService(provider);
        }, 800);
      }
    } else {
      showToast(data.message || 'Failed to remove account', 'error');
    }
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function saveCookies() {
  const p = state.activeCookieProvider;
  const textarea = document.getElementById('cookie-textarea');
  const content = textarea.value.trim();

  if (!content) {
    showToast('Please enter credential content to save.', 'error');
    return;
  }

  try {
    showToast(`Saving credentials for ${p.toUpperCase()}...`, 'info');
    const res = await fetch(`/api/cookies/${p}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ accounts: content }),
    });
    const data = await res.json();
    if (data.status === 'ok') {
      showToast(data.message, 'success');
      textarea.value = '';
      await loadCookiesTab();
      // Refresh limits tab so new accounts appear immediately
      try {
        const limRes = await fetch('/api/limits');
        if (limRes.ok) {
          state.limits = await limRes.json();
          renderLimits();
        }
      } catch (_) {}

      // Restart daemon to apply new credentials only if it is already running
      const srv = state.services?.find(s => s.id === p);
      if (srv && srv.running) {
        setTimeout(() => {
          showToast(`Restarting ${p} daemon to apply new credentials...`, 'info');
          restartService(p);
        }, 800);
      }
    } else {
      showToast(data.message || 'Failed to save', 'error');
    }
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function exportAllCookies() {
  try {
    showToast('Exporting credentials backup...', 'info');
    const res = await fetch('/api/cookies/export');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const jsonStr = JSON.stringify(data, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const dateStr = new Date().toISOString().slice(0, 10);
    a.download = `singularity_credentials_${dateStr}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    showToast(`Exported ${data.total_accounts || 0} accounts successfully!`, 'success');
  } catch (err) {
    showToast(`Export failed: ${err.message}`, 'error');
  }
}

async function handleImportCookiesFile(event) {
  const file = event.target.files?.[0];
  if (!file) return;

  try {
    showToast('Reading credentials file...', 'info');
    const text = await file.text();
    const parsed = JSON.parse(text);

    showToast('Importing credentials to SQLite...', 'info');
    const res = await fetch('/api/cookies/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(parsed),
    });

    const data = await res.json();
    if (!res.ok || data.status !== 'ok') {
      throw new Error(data.message || data.detail || 'Import failed');
    }

    showToast(data.message || 'Imported accounts successfully!', 'success');
    await loadCookiesTab();
    fetchServices();
  } catch (err) {
    showToast(`Import error: ${err.message}`, 'error');
  } finally {
    event.target.value = '';
  }
}


// ===================================================================
// Custom Select Component (NO DEFAULT GOOGLE SELECT)
// ===================================================================
function initCustomSelect() {
  const trigger = document.getElementById('model-select-trigger');
  const popover = document.getElementById('model-select-popover');
  const searchInput = document.getElementById('model-filter-input');

  trigger.addEventListener('click', (e) => {
    e.stopPropagation();
    const isOpen = popover.classList.toggle('open');
    trigger.classList.toggle('active', isOpen);
    if (isOpen) {
      searchInput.focus();
    }
  });

  document.addEventListener('click', (e) => {
    if (!popover.contains(e.target) && !trigger.contains(e.target)) {
      popover.classList.remove('open');
      trigger.classList.remove('active');
    }
  });

  searchInput.addEventListener('input', () => {
    renderCustomSelectOptions(searchInput.value.toLowerCase().trim());
  });
}

function renderCustomSelectOptions(query = '') {
  const list = document.getElementById('select-options-list');
  if (!list) return;

  const filtered = state.models.filter(m => {
    if (!query) return true;
    return m.name.toLowerCase().includes(query) || m.id.toLowerCase().includes(query) || m.provider.toLowerCase().includes(query);
  });

  list.innerHTML = filtered.map(m => {
    const isSelected = m.id === state.selectedModel;
    return `
      <div class="select-option ${isSelected ? 'selected' : ''}" data-id="${escapeHtml(m.id)}">
        <div>
          <span style="font-weight: 600;">${escapeHtml(m.name)}</span>
          <span style="font-size: 11px; color: var(--text-muted); margin-left: 6px;">(${escapeHtml(m.provider)})</span>
        </div>
        ${m.locked ? '<span class="lock-badge locked" style="font-size: 9px;">LOCKED</span>' : ''}
      </div>
    `;
  }).join('');

  list.querySelectorAll('.select-option').forEach(opt => {
    opt.addEventListener('click', () => {
      const modelId = opt.dataset.id;
      state.selectedModel = modelId;
      document.getElementById('model-select-label').textContent = modelId;
      document.getElementById('model-select-popover').classList.remove('open');
      document.getElementById('model-select-trigger').classList.remove('active');
      renderCustomSelectOptions();
    });
  });
}

// ===================================================================
// Interactive Playground
// ===================================================================
function initPlayground() {
  const sendBtn = document.getElementById('btn-send-chat');
  const input = document.getElementById('chat-input');
  const tempRange = document.getElementById('temp-range');
  const tempVal = document.getElementById('temp-val');
  const clearBtn = document.getElementById('btn-clear-chat');

  tempRange.addEventListener('input', () => {
    tempVal.textContent = tempRange.value;
  });

  sendBtn.addEventListener('click', sendChatMessage);

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendChatMessage();
    }
  });

  clearBtn.addEventListener('click', () => {
    state.chatMessages = [];
    document.getElementById('chat-history').innerHTML = `
      <div class="chat-msg assistant">
        <div class="msg-bubble">
          Chat cleared. Ready for your next query on <strong>${escapeHtml(state.selectedModel)}</strong>.
        </div>
      </div>
    `;
  });
}

async function sendChatMessage() {
  if (state.isStreaming) return;

  const input = document.getElementById('chat-input');
  const userText = input.value.trim();
  if (!userText) return;

  input.value = '';
  input.style.height = '44px';

  const history = document.getElementById('chat-history');

  // Append user message
  const userMsgEl = document.createElement('div');
  userMsgEl.className = 'chat-msg user';
  userMsgEl.innerHTML = `<div class="msg-bubble">${escapeHtml(userText)}</div>`;
  history.appendChild(userMsgEl);

  state.chatMessages.push({ role: 'user', content: userText });

  // Append assistant placeholder
  const assistantMsgEl = document.createElement('div');
  assistantMsgEl.className = 'chat-msg assistant';

  const bubbleEl = document.createElement('div');
  bubbleEl.className = 'msg-bubble';
  bubbleEl.textContent = 'Thinking...';
  assistantMsgEl.appendChild(bubbleEl);
  history.appendChild(assistantMsgEl);

  history.scrollTop = history.scrollHeight;

  state.isStreaming = true;
  const sendBtn = document.getElementById('btn-send-chat');
  sendBtn.disabled = true;

  const systemPrompt = document.getElementById('system-prompt-input')?.value.trim();
  const messagesPayload = [];
  if (systemPrompt) {
    messagesPayload.push({ role: 'system', content: systemPrompt });
  }
  messagesPayload.push(...state.chatMessages);

  const temperature = parseFloat(document.getElementById('temp-range')?.value || 0.7);

  let fullContent = '';
  let fullReasoning = '';
  let reasoningBox = null;
  const startTime = performance.now();

  try {
    const response = await fetch('/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: state.selectedModel,
        messages: messagesPayload,
        temperature: temperature,
        stream: true,
      }),
    });

    if (!response.ok) {
      const errText = await response.text();
      bubbleEl.innerHTML = `<span style="color: var(--color-error);">Error: ${escapeHtml(errText)}</span>`;
      state.isStreaming = false;
      sendBtn.disabled = false;
      return;
    }

    bubbleEl.textContent = '';

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // keep remainder

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith('data: ')) continue;
        const rawJson = trimmed.substring(6).trim();
        if (rawJson === '[DONE]') continue;

        try {
          const parsed = JSON.parse(rawJson);
          const delta = parsed.choices?.[0]?.delta || {};

          // Reasoning Delta
          if (delta.reasoning_content) {
            fullReasoning += delta.reasoning_content;
            if (!reasoningBox) {
              reasoningBox = document.createElement('div');
              reasoningBox.className = 'reasoning-box';
              reasoningBox.innerHTML = `
                <div class="reasoning-summary">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 14 14"></polyline></svg>
                  Thinking Process Trace
                </div>
                <div class="reasoning-content"></div>
              `;
              assistantMsgEl.insertBefore(reasoningBox, bubbleEl);
            }
            reasoningBox.querySelector('.reasoning-content').textContent = fullReasoning;
          }

          // Main Content Delta
          if (delta.content) {
            fullContent += delta.content;
            bubbleEl.textContent = fullContent;
          }
        } catch (e) {
          // ignore chunk parse errors
        }
      }
      history.scrollTop = history.scrollHeight;
    }

    const elapsed = Math.round(performance.now() - startTime);
    state.chatMessages.push({ role: 'assistant', content: fullContent });

    // Append meta badge
    const metaBadge = document.createElement('div');
    metaBadge.style.fontSize = '10px';
    metaBadge.style.fontFamily = 'var(--font-mono)';
    metaBadge.style.color = 'var(--text-muted)';
    metaBadge.style.marginTop = '4px';
    metaBadge.textContent = `${state.selectedModel} • ${elapsed}ms • ~${Math.round(fullContent.length / 4)} tokens`;
    assistantMsgEl.appendChild(metaBadge);

  } catch (err) {
    bubbleEl.innerHTML = `<span style="color: var(--color-error);">Stream Failed: ${escapeHtml(err.message)}</span>`;
  } finally {
    state.isStreaming = false;
    sendBtn.disabled = false;
    history.scrollTop = history.scrollHeight;
  }
}

// ===================================================================
// Copy Endpoint Action
// ===================================================================
function initCopyAction() {
  const btn = document.getElementById('btn-copy-url');
  btn.addEventListener('click', () => {
    const text = document.getElementById('gateway-url-text').textContent;
    navigator.clipboard.writeText(text).then(() => {
      showToast('Copied endpoint to clipboard: ' + text, 'success');
    });
  });

  const stChip = document.getElementById('chip-sillytavern');
  if (stChip) {
    stChip.addEventListener('click', () => {
      const urlSpan = document.getElementById('gateway-url-text');
      const base = 'http://localhost:9000/v1';
      if (urlSpan.textContent.endsWith('/chat/completions')) {
        urlSpan.textContent = base;
        stChip.classList.remove('active');
        showToast('Switched to Base URL: ' + base, 'info');
      } else {
        urlSpan.textContent = base + '/chat/completions';
        stChip.classList.add('active');
        showToast('Appended /chat/completions for SillyTavern', 'success');
      }
    });
  }
}

// ===================================================================
// Cloud Tunnel (ngrok Remote Access)
// ===================================================================
async function fetchTunnelStatus() {
  try {
    const res = await fetch('/api/tunnel/status');
    if (!res.ok) return;
    const data = await res.json();
    state.tunnel = data;
    updateTunnelUI();
  } catch (err) {
    console.error('Failed to fetch tunnel status:', err);
  }
}

function updateTunnelUI() {
  const t = state.tunnel || { status: 'offline' };
  const isOnline = t.status === 'online' && !!t.public_url;

  // Sidebar badge
  const navBadge = document.getElementById('nav-tunnel-badge');
  if (navBadge) {
    navBadge.textContent = isOnline ? 'ONLINE' : 'OFFLINE';
    navBadge.className = `nav-badge ${isOnline ? 'online' : 'offline'}`;
  }

  // Toggle button text & styles
  const toggleBtn = document.getElementById('btn-toggle-tunnel');
  const toggleBtnText = document.getElementById('btn-toggle-tunnel-text');
  if (toggleBtn && toggleBtnText) {
    if (isOnline) {
      toggleBtn.className = 'btn btn-secondary btn-sm';
      toggleBtnText.textContent = 'Stop Tunnel';
    } else {
      toggleBtn.className = 'btn btn-primary btn-sm';
      toggleBtnText.textContent = 'Start ngrok Tunnel';
    }
  }

  // URL Display Box & Text
  const urlText = document.getElementById('tunnel-url-text');
  const stChip = document.getElementById('chip-tunnel-st');
  if (urlText) {
    if (isOnline) {
      const base = `${t.public_url}/v1`;
      if (stChip && stChip.classList.contains('active')) {
        urlText.textContent = `${base}/chat/completions`;
      } else {
        urlText.textContent = base;
      }
    } else {
      urlText.textContent = 'Offline — Click "Start ngrok Tunnel" to expose';
      if (stChip) stChip.classList.remove('active');
    }
  }

  // Authtoken input placeholder
  const tokenInput = document.getElementById('input-ngrok-authtoken');
  if (tokenInput && t.has_authtoken && !tokenInput.value) {
    tokenInput.placeholder = '✓ Authtoken configured (paste new token to update)';
  }
}

async function toggleTunnel() {
  const isOnline = state.tunnel && state.tunnel.status === 'online';
  const endpoint = isOnline ? '/api/tunnel/stop' : '/api/tunnel/start';
  const toggleBtnText = document.getElementById('btn-toggle-tunnel-text');

  if (toggleBtnText) {
    toggleBtnText.textContent = isOnline ? 'Stopping...' : 'Starting...';
  }

  try {
    showToast(isOnline ? 'Stopping ngrok tunnel...' : 'Starting ngrok tunnel on port 9000...', 'info');
    const res = await fetch(endpoint, { method: 'POST' });
    const data = await res.json();

    if (data.status === 'error') {
      showToast(data.message || 'Tunnel operation failed', 'error');
    } else if (data.status === 'online') {
      showToast(`Tunnel active: ${data.public_url}`, 'success');
    } else if (data.status === 'offline') {
      showToast('ngrok tunnel stopped successfully', 'info');
    }
    await fetchTunnelStatus();
  } catch (err) {
    showToast(`Tunnel error: ${err.message}`, 'error');
    await fetchTunnelStatus();
  }
}

async function saveNgrokAuthtoken() {
  const input = document.getElementById('input-ngrok-authtoken');
  if (!input) return;
  const token = input.value.trim();
  if (!token) {
    showToast('Please paste an ngrok authtoken first.', 'error');
    return;
  }

  try {
    showToast('Saving ngrok authtoken...', 'info');
    const res = await fetch('/api/tunnel/authtoken', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ authtoken: token })
    });
    const data = await res.json();
    if (data.status === 'error') {
      showToast(data.message || 'Failed to save authtoken', 'error');
    } else {
      showToast('ngrok authtoken configured successfully!', 'success');
      input.value = '';
      await fetchTunnelStatus();
    }
  } catch (err) {
    showToast(`Failed to configure token: ${err.message}`, 'error');
  }
}

function initTunnelControls() {
  const btnToggle = document.getElementById('btn-toggle-tunnel');
  if (btnToggle) {
    btnToggle.addEventListener('click', toggleTunnel);
  }

  const btnRefresh = document.getElementById('btn-refresh-tunnel');
  if (btnRefresh) {
    btnRefresh.addEventListener('click', () => {
      showToast('Refreshing tunnel status...', 'info');
      fetchTunnelStatus();
    });
  }

  const btnCopy = document.getElementById('btn-copy-tunnel-url');
  if (btnCopy) {
    btnCopy.addEventListener('click', () => {
      const urlText = document.getElementById('tunnel-url-text');
      const text = urlText ? urlText.textContent : '';
      if (!text || text.startsWith('Offline')) {
        showToast('Start ngrok tunnel first to get an endpoint', 'info');
        return;
      }
      navigator.clipboard.writeText(text).then(() => {
        showToast('Copied endpoint to clipboard: ' + text, 'success');
      });
    });
  }

  const chipSt = document.getElementById('chip-tunnel-st');
  if (chipSt) {
    chipSt.addEventListener('click', () => {
      const t = state.tunnel;
      if (!t || t.status !== 'online' || !t.public_url) {
        showToast('Start ngrok tunnel first to use endpoint', 'info');
        return;
      }
      const urlSpan = document.getElementById('tunnel-url-text');
      const base = `${t.public_url}/v1`;
      if (urlSpan.textContent.endsWith('/chat/completions')) {
        urlSpan.textContent = base;
        chipSt.classList.remove('active');
        showToast('Switched to Base URL: ' + base, 'info');
      } else {
        urlSpan.textContent = base + '/chat/completions';
        chipSt.classList.add('active');
        showToast('Appended /chat/completions for SillyTavern', 'success');
      }
    });
  }

  const btnSaveToken = document.getElementById('btn-save-authtoken');
  if (btnSaveToken) {
    btnSaveToken.addEventListener('click', saveNgrokAuthtoken);
  }
}

function loadTunnelTab() {
  fetchTunnelStatus();
}

// ===================================================================
// Initialization
// ===================================================================
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initSimulationToggle();
  initNavigation();
  initModelFilters();
  initCookieTabs();
  initCustomSelect();
  initPlayground();
  initCopyAction();
  initTunnelControls();

  // Fleet controls (Desktop & Mobile)
  const handleRefresh = () => {
    showToast('Refreshing telemetry...', 'info');
    fetchServices();
    fetchLimits();
  };

  const btnRefresh = document.getElementById('btn-refresh-telemetry');
  if (btnRefresh) btnRefresh.addEventListener('click', handleRefresh);

  const btnRefreshMobile = document.getElementById('btn-refresh-telemetry-mobile');
  if (btnRefreshMobile) btnRefreshMobile.addEventListener('click', handleRefresh);

  const btnStartAll = document.getElementById('btn-start-all');
  if (btnStartAll) btnStartAll.addEventListener('click', startAllServices);

  const btnStartAllMobile = document.getElementById('btn-start-all-mobile');
  if (btnStartAllMobile) btnStartAllMobile.addEventListener('click', startAllServices);

  const btnStopAll = document.getElementById('btn-stop-all');
  if (btnStopAll) btnStopAll.addEventListener('click', stopAllServices);

  const btnStopAllMobile = document.getElementById('btn-stop-all-mobile');
  if (btnStopAllMobile) btnStopAllMobile.addEventListener('click', stopAllServices);

  // Initial Data Fetches
  fetchServices();
  fetchLimits();
  fetchModels();
  fetchTunnelStatus();

  // Background Telemetry Polling (every 3.5s)
  setInterval(() => {
    fetchServices();
    if (state.currentTab === 'limits') {
      fetchLimits();
    }
    if (state.currentTab === 'tunnel') {
      fetchTunnelStatus();
    }
  }, 3500);

  // Periodic tunnel status refresh (every 10s to keep sidebar badge updated)
  setInterval(() => {
    if (state.currentTab !== 'tunnel') {
      fetchTunnelStatus();
    }
  }, 10000);
});

