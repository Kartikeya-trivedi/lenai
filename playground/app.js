/**
 * LenAI Developer Portal — Application Logic
 * Vanilla JS, no dependencies.
 */

// ─── Configuration ────────────────────────────────────────
const API_BASE = '';  // Same origin
const POLL_INITIAL_DELAY = 1000;
const POLL_MAX_DELAY = 10000;
const POLL_BACKOFF = 1.5;

// ─── State ────────────────────────────────────────────────
let currentModality = 'image';
let currentApiKey = localStorage.getItem('lenai_api_key') || '';
let activePolls = new Map();

// ─── Initialization ───────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    // Restore saved API key
    const keyInput = document.getElementById('global-api-key');
    if (currentApiKey) keyInput.value = currentApiKey;
    keyInput.addEventListener('change', (e) => {
        currentApiKey = e.target.value;
        localStorage.setItem('lenai_api_key', currentApiKey);
        showToast('API key saved', 'success');
    });

    // Setup tab routing
    setupTabRouting();

    // Check system health
    checkSystemHealth();
    setInterval(checkSystemHealth, 30000);

    // Setup drag and drop
    setupDragAndDrop();

    // Load initial tab data
    const hash = window.location.hash.replace('#', '') || 'playground';
    switchTab(hash);
});

// ─── API Client ───────────────────────────────────────────
class ApiClient {
    static getHeaders() {
        const headers = {};
        if (currentApiKey) headers['X-API-Key'] = currentApiKey;
        return headers;
    }

    static async get(path) {
        const response = await fetch(`${API_BASE}${path}`, {
            headers: this.getHeaders(),
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({ error: { message: response.statusText } }));
            throw new Error(err.error?.message || `HTTP ${response.status}`);
        }
        return response.json();
    }

    static async post(path, body, isFormData = false) {
        const opts = {
            method: 'POST',
            headers: this.getHeaders(),
        };
        if (isFormData) {
            opts.body = body;
        } else {
            opts.headers['Content-Type'] = 'application/json';
            opts.body = JSON.stringify(body);
        }
        const response = await fetch(`${API_BASE}${path}`, opts);
        const data = await response.json().catch(() => null);
        if (!response.ok) {
            throw new Error(data?.error?.message || `HTTP ${response.status}`);
        }
        return data;
    }

    static async delete(path) {
        const response = await fetch(`${API_BASE}${path}`, {
            method: 'DELETE',
            headers: this.getHeaders(),
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({ error: { message: response.statusText } }));
            throw new Error(err.error?.message || `HTTP ${response.status}`);
        }
        return response.json().catch(() => ({}));
    }
}

// ─── Tab Routing ──────────────────────────────────────────
function setupTabRouting() {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const tab = item.dataset.tab;
            switchTab(tab);
            window.location.hash = tab;
        });
    });

    window.addEventListener('hashchange', () => {
        const tab = window.location.hash.replace('#', '') || 'playground';
        switchTab(tab);
    });
}

function switchTab(tabName) {
    // Update nav active state
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.tab === tabName);
    });

    // Show corresponding content
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.toggle('active', tab.id === `tab-${tabName}`);
        tab.classList.toggle('hidden', tab.id !== `tab-${tabName}`);
    });

    // Load tab-specific data
    if (tabName === 'keys') loadApiKeys();
    if (tabName === 'usage') loadUsageDashboard();
}

// ─── System Health ────────────────────────────────────────
async function checkSystemHealth() {
    const statusEl = document.getElementById('system-status');
    try {
        const data = await ApiClient.get('/health');
        const dot = statusEl.querySelector('.status-dot');
        const text = statusEl.querySelector('.status-text');

        dot.className = 'status-dot';
        if (data.status === 'ok') {
            dot.classList.add('status-ok');
            text.textContent = 'All systems operational';
        } else if (data.status === 'degraded') {
            dot.classList.add('status-degraded');
            text.textContent = 'Degraded performance';
        } else {
            dot.classList.add('status-error');
            text.textContent = 'System issues detected';
        }
    } catch {
        const dot = statusEl.querySelector('.status-dot');
        const text = statusEl.querySelector('.status-text');
        dot.className = 'status-dot status-error';
        text.textContent = 'Cannot reach API';
    }
}

// ─── Modality Selection ───────────────────────────────────
function selectModality(modality) {
    currentModality = modality;

    // Update card states
    document.querySelectorAll('.modality-card').forEach(card => {
        card.classList.toggle('active', card.dataset.modality === modality);
    });

    // Show/hide param groups
    document.querySelectorAll('.param-group').forEach(group => {
        group.classList.toggle('hidden', group.id !== `params-${modality}`);
    });
}

// ─── Inference Submission ─────────────────────────────────
async function submitInference(e) {
    e.preventDefault();

    if (!currentApiKey) {
        showToast('Please enter your API key first', 'error');
        return;
    }

    const btn = document.getElementById('submit-btn');
    btn.classList.add('loading');
    btn.disabled = true;

    try {
        const formData = new FormData();

        // Add modality-specific params
        if (currentModality === 'image') {
            formData.append('prompt', document.getElementById('img-prompt').value);
            formData.append('negative_prompt', document.getElementById('img-negative').value);
            formData.append('width', document.getElementById('img-width').value);
            formData.append('height', document.getElementById('img-height').value);
            formData.append('steps', document.getElementById('img-steps').value);
            formData.append('cfg_scale', document.getElementById('img-cfg').value);
        } else if (currentModality === 'voice_stt') {
            const fileInput = document.getElementById('stt-file');
            if (fileInput.files.length > 0) {
                formData.append('file', fileInput.files[0]);
            } else {
                throw new Error('Please select an audio file');
            }
        } else if (currentModality === 'voice_tts') {
            formData.append('text', document.getElementById('tts-text').value);
            formData.append('voice', document.getElementById('tts-voice').value);
            formData.append('speed', document.getElementById('tts-speed').value);
        } else if (currentModality === 'video') {
            formData.append('prompt', document.getElementById('vid-prompt').value);
            const fileInput = document.getElementById('vid-file');
            if (fileInput.files.length > 0) {
                formData.append('file', fileInput.files[0]);
            }
        }

        if (currentModality === 'rag') {
            const payload = {
                question: document.getElementById('rag-question').value,
                top_k: parseInt(document.getElementById('rag-top-k').value),
                rerank_top_k: parseInt(document.getElementById('rag-rerank-k').value),
                use_cache: document.getElementById('rag-use-cache').checked
            };
            const data = await ApiClient.post('/v1/rag/query', payload, false);
            showToast('RAG Query Completed', 'success');
            renderRagResult(data);
        } else {
            // Add webhook URL if set
            const webhookUrl = document.getElementById('webhook-url').value;
            if (webhookUrl) formData.append('webhook_url', webhookUrl);

            const data = await ApiClient.post(`/v1/infer/${currentModality}`, formData, true);

            showToast(`Job submitted: ${data.job_id}`, 'success');
            renderJobResult(data);
            startPolling(data.job_id);
        }

    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        btn.classList.remove('loading');
        btn.disabled = false;
    }
}

// ─── Job Polling ──────────────────────────────────────────
function startPolling(jobId) {
    let delay = POLL_INITIAL_DELAY;

    const poll = async () => {
        try {
            const data = await ApiClient.get(`/v1/jobs/${jobId}`);
            updateJobResult(data);

            if (['completed', 'failed', 'dead_letter'].includes(data.status)) {
                activePolls.delete(jobId);
                if (data.status === 'completed') {
                    showToast('Job completed!', 'success');
                } else {
                    showToast(`Job ${data.status}: ${data.error_message || 'Unknown error'}`, 'error');
                }
                return;
            }

            delay = Math.min(delay * POLL_BACKOFF, POLL_MAX_DELAY);
            const timer = setTimeout(poll, delay);
            activePolls.set(jobId, timer);
        } catch {
            delay = Math.min(delay * POLL_BACKOFF, POLL_MAX_DELAY);
            const timer = setTimeout(poll, delay);
            activePolls.set(jobId, timer);
        }
    };

    const timer = setTimeout(poll, delay);
    activePolls.set(jobId, timer);
}

// ─── Result Rendering ────────────────────────────────────
function renderJobResult(data) {
    const area = document.getElementById('result-area');
    area.innerHTML = `
        <div class="result-job-id">
            <span>Job ID:</span>
            <code>${data.job_id}</code>
            <button class="btn-icon copy-btn" onclick="copyToClipboard('${data.job_id}')">📋</button>
        </div>
        <div id="result-status">
            <span class="status-badge ${data.status}">
                <span class="badge-dot"></span>
                ${data.status}
            </span>
        </div>
        <div class="progress-bar" id="result-progress">
            <div class="progress-fill" style="width: 0%"></div>
        </div>
        <div id="result-output"></div>
        <button class="json-toggle" onclick="toggleResultJson()">Show raw JSON ▾</button>
        <div class="result-json hidden" id="result-json">${syntaxHighlight(data)}</div>
    `;
}

function renderRagResult(data) {
    const area = document.getElementById('result-area');
    
    // Determine confidence color
    let confColor = 'var(--accent-red)';
    if (data.confidence > 0.8) confColor = 'var(--accent-green)';
    else if (data.confidence > 0.5) confColor = 'var(--accent-yellow)';

    // Build sources HTML
    const sourcesHtml = data.sources.map((src, i) => `
        <details class="rag-source-detail">
            <summary>
                <span class="rag-source-idx">[${i+1}]</span> 
                <span class="rag-source-name">${escapeHtml(src.source)}</span>
                <span class="rag-source-score">Score: ${(src.score * 100).toFixed(1)}%</span>
            </summary>
            <div class="rag-source-text">${escapeHtml(src.text)}</div>
        </details>
    `).join('');

    area.innerHTML = `
        <div class="rag-header">
            <span class="status-badge completed" style="border-color: ${confColor}; color: ${confColor}">
                <span class="badge-dot" style="background: ${confColor}"></span>
                Confidence: ${(data.confidence * 100).toFixed(1)}%
            </span>
            <span class="status-badge" style="background: rgba(99, 102, 241, 0.1); color: var(--accent-indigo);">
                🤖 ${data.model_used}
            </span>
            ${data.cached ? '<span class="status-badge" style="background: rgba(6, 182, 212, 0.1); color: #06b6d4;">⚡ Cached</span>' : ''}
        </div>
        
        <div class="rag-answer">
            ${data.answer.replace(/\n/g, '<br>')}
        </div>

        <div class="rag-sources">
            <h4 style="margin-bottom: 8px; color: var(--text-secondary); font-size: 0.85rem;">Retrieved Context</h4>
            ${sourcesHtml}
        </div>

        <button class="json-toggle" onclick="toggleResultJson()">Show raw JSON ▾</button>
        <div class="result-json hidden" id="result-json">${syntaxHighlight(data)}</div>
    `;
}

function updateJobResult(data) {
    const statusEl = document.getElementById('result-status');
    if (statusEl) {
        statusEl.innerHTML = `
            <span class="status-badge ${data.status}">
                <span class="badge-dot"></span>
                ${data.status}
            </span>
        `;
    }

    const progressEl = document.getElementById('result-progress');
    if (progressEl) {
        const fill = progressEl.querySelector('.progress-fill');
        fill.style.width = `${data.progress || 0}%`;
    }

    const outputEl = document.getElementById('result-output');
    if (outputEl && data.status === 'completed' && data.output_url) {
        if (data.modality === 'image') {
            outputEl.innerHTML = `<img src="${data.output_url}" class="result-image" alt="Generated image">`;
        } else if (data.modality === 'voice_tts') {
            outputEl.innerHTML = `<audio controls class="result-audio"><source src="${data.output_url}" type="audio/mpeg"></audio>`;
        } else if (data.modality === 'video') {
            outputEl.innerHTML = `<video controls class="result-video"><source src="${data.output_url}" type="video/mp4"></video>`;
        } else if (data.modality === 'voice_stt') {
            outputEl.innerHTML = `<div class="result-json">${JSON.stringify(data, null, 2)}</div>`;
        }
    } else if (data.status === 'failed' || data.status === 'dead_letter') {
        if (outputEl) {
            outputEl.innerHTML = `<div class="result-json" style="color: var(--accent-red);">${data.error_message || 'Unknown error'}</div>`;
        }
    }

    const jsonEl = document.getElementById('result-json');
    if (jsonEl) jsonEl.innerHTML = syntaxHighlight(data);
}

function toggleResultJson() {
    const el = document.getElementById('result-json');
    el.classList.toggle('hidden');
}

// ─── API Keys ─────────────────────────────────────────────
async function loadApiKeys() {
    const tbody = document.getElementById('keys-tbody');
    try {
        const data = await ApiClient.get('/v1/api-keys');
        const keys = data.keys || data || [];

        if (keys.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-cell">No API keys found. Create one to get started.</td></tr>';
            return;
        }

        tbody.innerHTML = keys.map(key => `
            <tr>
                <td>${escapeHtml(key.name)}</td>
                <td class="mono">${escapeHtml(key.key_prefix)}...</td>
                <td>${(key.scopes || []).map(s => `<span class="scope-tag">${s}</span>`).join('')}</td>
                <td>${key.rate_limit_rpm || 60} RPM</td>
                <td>${key.last_used_at ? new Date(key.last_used_at).toLocaleDateString() : 'Never'}</td>
                <td><span class="status-badge ${key.is_active ? 'completed' : 'failed'}">${key.is_active ? 'Active' : 'Revoked'}</span></td>
                <td>
                    <button class="btn btn-sm btn-secondary" onclick="rotateKey('${key.id}')">Rotate</button>
                    <button class="btn btn-sm btn-danger" onclick="revokeKey('${key.id}')">Revoke</button>
                </td>
            </tr>
        `).join('');
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="7" class="empty-cell">Error loading keys: ${escapeHtml(err.message)}</td></tr>`;
    }
}

function showCreateKeyModal() {
    const modal = document.getElementById('modal-overlay');
    document.getElementById('modal-title').textContent = 'Create API Key';
    document.getElementById('modal-body').innerHTML = `
        <div class="form-field">
            <label for="new-key-name">Key Name</label>
            <input type="text" id="new-key-name" placeholder="Production Key" required>
        </div>
        <div class="form-field">
            <label>Scopes</label>
            <div style="display: flex; gap: 12px; flex-wrap: wrap;">
                <label style="display: flex; align-items: center; gap: 6px; font-size: 0.85rem; cursor: pointer;">
                    <input type="checkbox" class="scope-cb" value="image" checked> Image
                </label>
                <label style="display: flex; align-items: center; gap: 6px; font-size: 0.85rem; cursor: pointer;">
                    <input type="checkbox" class="scope-cb" value="voice_stt" checked> Voice STT
                </label>
                <label style="display: flex; align-items: center; gap: 6px; font-size: 0.85rem; cursor: pointer;">
                    <input type="checkbox" class="scope-cb" value="voice_tts" checked> Voice TTS
                </label>
                <label style="display: flex; align-items: center; gap: 6px; font-size: 0.85rem; cursor: pointer;">
                    <input type="checkbox" class="scope-cb" value="video" checked> Video
                </label>
            </div>
        </div>
        <div class="form-field">
            <label for="new-key-rpm">Rate Limit (RPM)</label>
            <input type="number" id="new-key-rpm" value="60" min="1" max="1000">
        </div>
        <button class="btn btn-primary btn-lg" onclick="createApiKey()">Create Key</button>
    `;
    modal.classList.remove('hidden');
}

async function createApiKey() {
    const name = document.getElementById('new-key-name').value;
    const scopes = [...document.querySelectorAll('.scope-cb:checked')].map(cb => cb.value);
    const rpm = parseInt(document.getElementById('new-key-rpm').value);

    if (!name) {
        showToast('Please enter a key name', 'error');
        return;
    }

    try {
        const data = await ApiClient.post('/v1/api-keys', { name, scopes, rate_limit_rpm: rpm });

        // Show the raw key
        document.getElementById('modal-body').innerHTML = `
            <p>Your API key has been created:</p>
            <div class="key-display">
                <code>${data.raw_key || data.key || 'N/A'}</code>
                <button class="btn-icon" onclick="copyToClipboard('${data.raw_key || data.key || ''}')">📋</button>
            </div>
            <div class="key-warning">
                ⚠️ Save this key now. It will not be shown again.
            </div>
            <button class="btn btn-secondary btn-lg" style="margin-top: 16px;" onclick="closeModal(); loadApiKeys();">Done</button>
        `;

        showToast('API key created!', 'success');
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function rotateKey(keyId) {
    if (!confirm('Rotate this key? The old key will be immediately revoked.')) return;
    try {
        const data = await ApiClient.post(`/v1/api-keys/${keyId}/rotate`);
        showToast('Key rotated successfully', 'success');

        // Show new key in modal
        document.getElementById('modal-title').textContent = 'Key Rotated';
        document.getElementById('modal-body').innerHTML = `
            <p>Your new API key:</p>
            <div class="key-display">
                <code>${data.raw_key || data.new_key || 'N/A'}</code>
                <button class="btn-icon" onclick="copyToClipboard('${data.raw_key || data.new_key || ''}')">📋</button>
            </div>
            <div class="key-warning">⚠️ Save this key now. The old key has been revoked.</div>
            <button class="btn btn-secondary btn-lg" style="margin-top: 16px;" onclick="closeModal(); loadApiKeys();">Done</button>
        `;
        document.getElementById('modal-overlay').classList.remove('hidden');

        loadApiKeys();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function revokeKey(keyId) {
    if (!confirm('Revoke this API key? This action cannot be undone.')) return;
    try {
        await ApiClient.delete(`/v1/api-keys/${keyId}`);
        showToast('API key revoked', 'success');
        loadApiKeys();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// ─── Usage Dashboard ──────────────────────────────────────
async function loadUsageDashboard() {
    try {
        const data = await ApiClient.get('/v1/usage?days=30');
        const summary = data.summary || {};

        document.getElementById('stat-total-requests').textContent =
            formatNumber(summary.total_requests || 0);
        document.getElementById('stat-avg-latency').textContent =
            `${Math.round(summary.avg_compute_time_ms || 0)}ms`;
        document.getElementById('stat-error-rate').textContent =
            `${((summary.total_errors || 0) / Math.max(summary.total_requests || 1, 1) * 100).toFixed(1)}%`;
        document.getElementById('stat-storage').textContent =
            formatBytes(summary.total_output_bytes || 0);

        // Draw charts
        drawRequestsChart(data.daily_usage || []);
        drawModalityChart(data.by_modality || []);
    } catch (err) {
        console.error('Usage load error:', err);
        // Show placeholder data
        document.getElementById('stat-total-requests').textContent = '—';
        document.getElementById('stat-avg-latency').textContent = '—';
        document.getElementById('stat-error-rate').textContent = '—';
        document.getElementById('stat-storage').textContent = '—';
    }
}

function drawRequestsChart(dailyData) {
    const canvas = document.getElementById('requests-chart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width = canvas.offsetWidth * 2;
    const H = canvas.height = 400;
    ctx.scale(1, 1);
    ctx.clearRect(0, 0, W, H);

    if (dailyData.length === 0) {
        ctx.fillStyle = '#64748b';
        ctx.font = '24px Inter';
        ctx.textAlign = 'center';
        ctx.fillText('No data yet', W / 2, H / 2);
        return;
    }

    const values = dailyData.map(d => d.request_count || 0);
    const maxVal = Math.max(...values, 1);
    const padding = { top: 30, right: 20, bottom: 50, left: 60 };
    const chartW = W - padding.left - padding.right;
    const chartH = H - padding.top - padding.bottom;

    // Grid lines
    ctx.strokeStyle = 'rgba(255,255,255,0.05)';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
        const y = padding.top + (chartH / 4) * i;
        ctx.beginPath();
        ctx.moveTo(padding.left, y);
        ctx.lineTo(W - padding.right, y);
        ctx.stroke();

        ctx.fillStyle = '#64748b';
        ctx.font = '20px Inter';
        ctx.textAlign = 'right';
        ctx.fillText(Math.round(maxVal * (1 - i / 4)), padding.left - 10, y + 6);
    }

    // Line
    const gradient = ctx.createLinearGradient(0, padding.top, 0, H - padding.bottom);
    gradient.addColorStop(0, 'rgba(99, 102, 241, 0.3)');
    gradient.addColorStop(1, 'rgba(99, 102, 241, 0)');

    ctx.beginPath();
    values.forEach((val, i) => {
        const x = padding.left + (i / Math.max(values.length - 1, 1)) * chartW;
        const y = padding.top + (1 - val / maxVal) * chartH;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });

    // Fill area
    ctx.lineTo(padding.left + chartW, padding.top + chartH);
    ctx.lineTo(padding.left, padding.top + chartH);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // Stroke line
    ctx.beginPath();
    values.forEach((val, i) => {
        const x = padding.left + (i / Math.max(values.length - 1, 1)) * chartW;
        const y = padding.top + (1 - val / maxVal) * chartH;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = '#6366f1';
    ctx.lineWidth = 3;
    ctx.stroke();

    // Dots
    values.forEach((val, i) => {
        const x = padding.left + (i / Math.max(values.length - 1, 1)) * chartW;
        const y = padding.top + (1 - val / maxVal) * chartH;
        ctx.beginPath();
        ctx.arc(x, y, 5, 0, Math.PI * 2);
        ctx.fillStyle = '#6366f1';
        ctx.fill();
        ctx.strokeStyle = '#0a0a0f';
        ctx.lineWidth = 2;
        ctx.stroke();
    });
}

function drawModalityChart(modalityData) {
    const canvas = document.getElementById('modality-chart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width = canvas.offsetWidth * 2;
    const H = canvas.height = 400;
    ctx.clearRect(0, 0, W, H);

    if (modalityData.length === 0) {
        ctx.fillStyle = '#64748b';
        ctx.font = '24px Inter';
        ctx.textAlign = 'center';
        ctx.fillText('No data yet', W / 2, H / 2);
        return;
    }

    const colors = ['#6366f1', '#06b6d4', '#a855f7', '#10b981'];
    const maxVal = Math.max(...modalityData.map(d => d.request_count || 0), 1);
    const barWidth = Math.min(60, (W - 100) / modalityData.length - 20);
    const padding = { top: 30, bottom: 60, left: 60 };

    modalityData.forEach((item, i) => {
        const x = padding.left + i * (barWidth + 20);
        const barH = ((item.request_count || 0) / maxVal) * (H - padding.top - padding.bottom);
        const y = H - padding.bottom - barH;

        // Bar
        ctx.fillStyle = colors[i % colors.length];
        ctx.beginPath();
        ctx.roundRect(x, y, barWidth, barH, [6, 6, 0, 0]);
        ctx.fill();

        // Label
        ctx.fillStyle = '#94a3b8';
        ctx.font = '18px Inter';
        ctx.textAlign = 'center';
        ctx.fillText(item.modality || 'unknown', x + barWidth / 2, H - 20);

        // Value
        ctx.fillStyle = '#f1f5f9';
        ctx.fillText(item.request_count || 0, x + barWidth / 2, y - 10);
    });
}

// ─── File Upload ──────────────────────────────────────────
function setupDragAndDrop() {
    document.querySelectorAll('.drop-zone').forEach(zone => {
        zone.addEventListener('dragover', (e) => {
            e.preventDefault();
            zone.classList.add('dragover');
        });
        zone.addEventListener('dragleave', () => {
            zone.classList.remove('dragover');
        });
        zone.addEventListener('drop', (e) => {
            e.preventDefault();
            zone.classList.remove('dragover');
            const input = zone.querySelector('.file-input');
            input.files = e.dataTransfer.files;
            handleFileSelect(input);
        });
    });
}

function handleFileSelect(input) {
    const file = input.files[0];
    if (!file) return;

    const prefix = input.id.split('-')[0]; // 'stt' or 'vid'
    const content = input.closest('.drop-zone').querySelector('.drop-zone-content');
    const preview = document.getElementById(`${prefix}-preview`);
    const filename = document.getElementById(`${prefix}-filename`);

    content.classList.add('hidden');
    preview.classList.remove('hidden');
    filename.textContent = `${file.name} (${formatBytes(file.size)})`;
}

function clearFile(prefix) {
    const input = document.getElementById(`${prefix}-file`);
    input.value = '';
    const content = input.closest('.drop-zone').querySelector('.drop-zone-content');
    const preview = document.getElementById(`${prefix}-preview`);
    content.classList.remove('hidden');
    preview.classList.add('hidden');
}

// ─── Utilities ────────────────────────────────────────────
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
}

function closeModal() {
    document.getElementById('modal-overlay').classList.add('hidden');
}

function toggleKeyVisibility() {
    const input = document.getElementById('global-api-key');
    input.type = input.type === 'password' ? 'text' : 'password';
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('Copied to clipboard!', 'success');
    }).catch(() => {
        // Fallback
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        showToast('Copied!', 'success');
    });
}

function syntaxHighlight(obj) {
    const json = JSON.stringify(obj, null, 2);
    return json
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"([^"]+)":/g, '<span style="color:#a78bfa">"$1"</span>:')
        .replace(/: "([^"]+)"/g, ': <span style="color:#10b981">"$1"</span>')
        .replace(/: (\d+)/g, ': <span style="color:#f59e0b">$1</span>')
        .replace(/: (true|false|null)/g, ': <span style="color:#06b6d4">$1</span>');
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
}

function formatNumber(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return n.toString();
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}
