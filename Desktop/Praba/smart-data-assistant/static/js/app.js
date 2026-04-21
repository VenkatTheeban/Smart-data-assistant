const API = '';
let charts = {};
let chartId = 0;

const messagesEl = document.getElementById('messagesContainer');
const inputEl = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const refreshBtn = document.getElementById('refreshDataBtn');
const sidebar = document.getElementById('sidebar');
const menuToggle = document.getElementById('menuToggle');
const overlay = document.getElementById('sidebarOverlay');

document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    bindEvents();
    pollWatcher();
});

function bindEvents() {
    sendBtn.addEventListener('click', send);
    inputEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            send();
        }
    });

    inputEl.addEventListener('input', () => {
        inputEl.style.height = 'auto';
        inputEl.style.height = `${Math.min(inputEl.scrollHeight, 100)}px`;
    });

    document.querySelectorAll('.quick-item, .chip').forEach((b) => {
        b.addEventListener('click', () => {
            inputEl.value = b.dataset.query;
            send();
        });
    });

    refreshBtn.addEventListener('click', reprocess);
    menuToggle?.addEventListener('click', () => {
        sidebar.classList.add('open');
        overlay.classList.add('active');
    });
    overlay?.addEventListener('click', () => {
        sidebar.classList.remove('open');
        overlay.classList.remove('active');
    });
}

async function loadStats() {
    try {
        const r = await fetch(`${API}/api/stats`);
        const d = await r.json();
        if (d.success) {
            const s = d.stats;
            document.getElementById('totalRecords').textContent = fmt(s.total_records);
            document.getElementById('comboCount').textContent = fmt(s.by_custom?.Combo || 0);
            document.getElementById('lgCount').textContent = fmt(s.by_custom?.LG || 0);
            document.getElementById('dgCount').textContent = fmt(s.by_custom?.DG || 0);
        }
    } catch (e) {
        console.error('Stats error:', e);
    }
}

async function send() {
    const text = inputEl.value.trim();
    if (!text) return;

    const welcome = document.querySelector('.welcome-hero');
    if (welcome) welcome.remove();

    addMsg(text, 'user');
    inputEl.value = '';
    inputEl.style.height = 'auto';
    const tid = showTyping();

    try {
        const r = await fetch(`${API}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question: text }),
        });
        const d = await r.json();
        removeTyping(tid);
        if (d.success) {
            renderBot(d);
        } else {
            addMsg(d.error || 'Something went wrong.', 'bot');
        }
    } catch (e) {
        removeTyping(tid);
        addMsg(`Connection error: ${e.message}`, 'bot');
    }
}

function renderBot(d) {
    const el = makeMsgEl('bot');
    const bubble = el.querySelector('.msg-bubble');

    if (d.explanation) {
        const p = document.createElement('p');
        p.textContent = d.explanation;
        p.style.marginBottom = '6px';
        bubble.appendChild(p);
    }

    if (d.row_count !== undefined) {
        const b = document.createElement('span');
        b.className = 'row-badge';
        b.textContent = `${fmt(d.row_count)} result${d.row_count !== 1 ? 's' : ''}`;
        bubble.appendChild(b);
    }

    if (d.download_file) {
        const a = document.createElement('a');
        a.href = `/static/exports/${d.download_file}`;
        a.className = 'dl-btn';
        a.download = d.download_file;
        a.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>' + d.download_file;
        bubble.appendChild(a);
    }

    if (d.base64_image) {
        const img = document.createElement('img');
        img.src = `data:image/png;base64,${d.base64_image}`;
        img.style.maxWidth = '100%';
        img.style.borderRadius = 'var(--r-sm)';
        img.style.marginTop = '12px';
        img.style.border = '1px solid var(--line)';
        bubble.appendChild(img);
    }

    if (d.response_type === 'chart' && d.data?.length) {
        renderChart(bubble, d.data, d.chart_config);
    }

    if (d.data?.length && d.response_type !== 'chart') {
        renderTable(bubble, d.data);
    }

    messagesEl.appendChild(el);
    scrollEnd();
}

function renderTable(container, data) {
    const wrap = document.createElement('div');
    wrap.className = 'table-wrap';
    const table = document.createElement('table');
    table.className = 'data-table';
    const headers = reorderHeaders(Object.keys(data[0]));

    const thead = document.createElement('thead');
    const hr = document.createElement('tr');
    headers.forEach((h) => {
        const th = document.createElement('th');
        th.textContent = formatHeader(h);
        hr.appendChild(th);
    });
    thead.appendChild(hr);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    const show = data.slice(0, 50);
    show.forEach((row) => {
        const tr = document.createElement('tr');
        headers.forEach((h) => {
            const td = document.createElement('td');
            const v = row[h];
            if (h.toLowerCase() === 'custom') {
                td.innerHTML = badge(v);
            } else {
                td.textContent = formatCellValue(h, v);
            }
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    wrap.appendChild(table);
    container.appendChild(wrap);

    if (data.length > 50) {
        const p = document.createElement('p');
        p.style.cssText = 'font-size:11px;color:var(--text-soft);margin-top:6px;';
        p.textContent = `Showing 50 of ${data.length} rows. Ask to download for full data.`;
        container.appendChild(p);
    }
}

function reorderHeaders(headers) {
    const out = [...headers];
    const reactIdx = out.indexOf('reactivation');
    const diffIdx = out.indexOf('different_device');

    // Business requirement: Different Device should appear immediately after Reactivation
    if (reactIdx !== -1 && diffIdx !== -1) {
        out.splice(diffIdx, 1);
        const newReactIdx = out.indexOf('reactivation');
        out.splice(newReactIdx + 1, 0, 'different_device');
    }

    return out;
}

function formatHeader(header) {
    const wordMap = {
        pct: '%',
        lg: 'LG',
        dg: 'DG',
    };
    const words = String(header).replace(/_/g, ' ').split(/\s+/).filter(Boolean);
    const pretty = words.map((w) => {
        const lw = w.toLowerCase();
        if (wordMap[lw]) return wordMap[lw];
        return lw.charAt(0).toUpperCase() + lw.slice(1);
    });
    return pretty.join(' ');
}

function formatCellValue(header, value) {
    if (value === null || value === undefined) return '';
    const h = String(header).toLowerCase();

    if (typeof value === 'number') {
        if (h.includes('pct') || h.includes('percent')) {
            return `${Number(value).toFixed(2)}%`;
        }
        return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
    }

    if ((h.includes('pct') || h.includes('percent')) && /^-?\d+(\.\d+)?$/.test(String(value))) {
        return `${Number(value).toFixed(2)}%`;
    }

    if (/^-?\d+(\.\d+)?$/.test(String(value)) && !h.includes('year')) {
        const n = Number(value);
        return Number.isInteger(n) ? n.toLocaleString() : n.toLocaleString(undefined, { maximumFractionDigits: 2 });
    }

    return String(value);
}

function badge(type) {
    const cls = {
        Combo: 'badge-combo',
        LG: 'badge-lg',
        DG: 'badge-dg',
        'Other Model': 'badge-other',
    };
    return `<span class="badge ${cls[type] || 'badge-other'}">${type || '-'}</span>`;
}

function renderChart(container, data, cfg) {
    const box = document.createElement('div');
    box.className = 'chart-box';
    if (container.classList.contains('dash-box')) {
        box.className = '';
    }

    const canvas = document.createElement('canvas');
    const cid = `c${++chartId}`;
    canvas.id = cid;
    box.appendChild(canvas);
    container.appendChild(box);

    requestAnimationFrame(() => {
        try {
            if (cfg?.special === 'combo_trend') {
                if (charts[cid]) charts[cid].destroy();
                charts[cid] = renderComboTrendChart(canvas, data, cfg);
                return;
            }

            const type = cfg?.type || 'bar';
            const keys = Object.keys(data[0]);
            const lk = keys[0];

            let vks = keys.slice(1);
            if (cfg?.filter_keys) {
                vks = cfg.filter_keys.filter((k) => k !== lk);
            }

            const palette = ['rgba(31,111,235,.82)', 'rgba(213,63,87,.82)', 'rgba(19,138,143,.82)', 'rgba(186,127,23,.82)', 'rgba(24,136,91,.82)', 'rgba(87,108,132,.82)'];

            const datasets = vks.map((k, i) => ({
                label: k.replace(/_/g, ' '),
                data: data.map((r) => Number(r[k]) || 0),
                backgroundColor: type === 'pie' || type === 'polarArea' || type === 'doughnut' ? palette : palette[i % palette.length],
                borderColor: type === 'pie' || type === 'polarArea' || type === 'doughnut' ? palette.map((p) => p.replace('.82', '1')) : palette[i % palette.length].replace('.82', '1'),
                borderWidth: type === 'line' ? 2 : 1,
                tension: 0.35,
                fill: false,
            }));

            if (charts[cid]) charts[cid].destroy();
            charts[cid] = new Chart(canvas, {
                type,
                data: { labels: data.map((r) => r[lk]), datasets },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: type === 'pie' || type === 'polarArea' || type === 'doughnut' || datasets.length > 1,
                            labels: { color: '#284262', font: { family: 'Source Sans 3', size: 11 } },
                        },
                        title: { display: !!cfg?.title, text: cfg?.title || '', color: '#18345a', font: { size: 13, family: 'Manrope' } },
                    },
                    scales: (type === 'pie' || type === 'polarArea' || type === 'doughnut') ? undefined : {
                        x: { ticks: { color: '#55708f', font: { size: 10 } }, grid: { color: 'rgba(31,111,235,.08)' } },
                        y: { ticks: { color: '#55708f', font: { size: 10 } }, grid: { color: 'rgba(31,111,235,.08)' } },
                    },
                },
            });
        } catch (e) {
            console.error('Chart error:', e);
        }
    });
}

function renderComboTrendChart(canvas, data, cfg) {
    const labels = data.map((r) => r.period);
    const totals = data.map((r) => Number(r.total) || 0);
    const comboReact = data.map((r) => Number(r.combo_reactivation) || 0);
    const pct = data.map((r) => Number(r.combo_reactivation_pct) || 0);

    return new Chart(canvas, {
        data: {
            labels,
            datasets: [
                {
                    type: 'bar',
                    label: 'Total Activations',
                    data: totals,
                    backgroundColor: 'rgba(31,111,235,0.28)',
                    borderColor: 'rgba(31,111,235,0.85)',
                    borderWidth: 1,
                    yAxisID: 'y',
                    order: 2,
                },
                {
                    type: 'bar',
                    label: 'COMBO Reactivation',
                    data: comboReact,
                    backgroundColor: 'rgba(213,63,87,0.72)',
                    borderColor: 'rgba(213,63,87,0.95)',
                    borderWidth: 1,
                    yAxisID: 'y',
                    order: 2,
                },
                {
                    type: 'line',
                    label: 'COMBO Reactivation %',
                    data: pct,
                    borderColor: 'rgba(20,125,130,1)',
                    backgroundColor: 'rgba(20,125,130,0.2)',
                    pointBackgroundColor: 'rgba(20,125,130,1)',
                    pointRadius: 3,
                    pointHoverRadius: 4,
                    borderWidth: 2,
                    tension: 0.3,
                    yAxisID: 'y1',
                    order: 1,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    labels: { color: '#284262', font: { family: 'Source Sans 3', size: 11 } },
                },
                title: {
                    display: !!cfg?.title,
                    text: cfg?.title || '',
                    color: '#18345a',
                    font: { size: 13, family: 'Manrope' },
                },
                tooltip: {
                    callbacks: {
                        label(context) {
                            const label = context.dataset.label || '';
                            const val = context.parsed.y;
                            if (context.dataset.yAxisID === 'y1') return `${label}: ${Number(val).toFixed(2)}%`;
                            return `${label}: ${Number(val).toLocaleString()}`;
                        },
                    },
                },
            },
            scales: {
                x: {
                    ticks: { color: '#55708f', font: { size: 10 } },
                    grid: { color: 'rgba(31,111,235,.08)' },
                },
                y: {
                    position: 'left',
                    ticks: {
                        color: '#55708f',
                        font: { size: 10 },
                        callback: (v) => Number(v).toLocaleString(),
                    },
                    grid: { color: 'rgba(31,111,235,.08)' },
                    title: { display: true, text: 'Count', color: '#55708f', font: { size: 10 } },
                },
                y1: {
                    position: 'right',
                    min: 0,
                    max: 100,
                    ticks: {
                        color: '#55708f',
                        font: { size: 10 },
                        callback: (v) => `${v}%`,
                    },
                    grid: { drawOnChartArea: false },
                    title: { display: true, text: 'Percentage', color: '#55708f', font: { size: 10 } },
                },
            },
        },
    });
}

function addMsg(text, type) {
    const el = makeMsgEl(type);
    el.querySelector('.msg-bubble').textContent = text;
    messagesEl.appendChild(el);
    scrollEnd();
}

function makeMsgEl(type) {
    const d = document.createElement('div');
    d.className = `message ${type}`;

    const av = document.createElement('div');
    av.className = 'msg-avatar';
    av.innerHTML = type === 'bot'
        ? '<i class="bi bi-cpu-fill" aria-hidden="true"></i>'
        : '<i class="bi bi-person-fill" aria-hidden="true"></i>';

    const body = document.createElement('div');
    body.className = 'msg-body';

    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';

    const time = document.createElement('div');
    time.className = 'msg-time';
    time.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    body.appendChild(bubble);
    body.appendChild(time);
    d.appendChild(av);
    d.appendChild(body);
    return d;
}

function showTyping() {
    const id = `t_${Date.now()}`;

    const d = document.createElement('div');
    d.className = 'message bot';
    d.id = id;

    const av = document.createElement('div');
    av.className = 'msg-avatar';
    av.innerHTML = '<i class="bi bi-cpu-fill" aria-hidden="true"></i>';

    const body = document.createElement('div');
    body.className = 'msg-body';

    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';

    const dots = document.createElement('div');
    dots.className = 'typing-dots';
    dots.innerHTML = '<span></span><span></span><span></span>';

    bubble.appendChild(dots);
    body.appendChild(bubble);
    d.appendChild(av);
    d.appendChild(body);
    messagesEl.appendChild(d);
    scrollEnd();
    return id;
}

function removeTyping(id) {
    document.getElementById(id)?.remove();
}

function scrollEnd() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

function fmt(n) {
    return Number(n).toLocaleString();
}

async function reprocess() {
    refreshBtn.style.opacity = '.5';
    addMsg('Re-processing all data with business logic...', 'bot');
    try {
        const r = await fetch(`${API}/api/reprocess`, { method: 'POST' });
        const d = await r.json();
        addMsg(d.success ? d.message : (d.error || 'Failed.'), 'bot');
        if (d.success) loadStats();
    } catch (e) {
        addMsg(`Error: ${e.message}`, 'bot');
    }
    refreshBtn.style.opacity = '1';
}

let lastEvt = 0;
async function pollWatcher() {
    try {
        const r = await fetch(`${API}/api/watcher-events`);
        const d = await r.json();
        if (d.events?.length > lastEvt) {
            const fresh = d.events.slice(lastEvt);
            const el = document.getElementById('watcherEvents');
            fresh.forEach((e) => {
                const div = document.createElement('div');
                div.className = 'watcher-event';
                div.textContent = e.type === 'file_detected' ? `New: ${e.filename}`
                    : e.type === 'import_complete' ? (e.result?.message || 'Imported')
                    : e.type === 'processing_complete' ? (e.result?.message || 'Processed')
                    : e.error || '';
                el.prepend(div);
                if (e.type === 'import_complete' || e.type === 'processing_complete') loadStats();
            });
            lastEvt = d.events.length;
        }
    } catch (_) {
        // no-op
    }
    setTimeout(pollWatcher, 5000);
}
