/* CIC AI Compute Platform v7.0 */
(function () {
    'use strict';
    const API = '/api/v1'; let N = [], authH = '', cView = 'global', topo = [], notifs = [], sortCol = '', sortAsc = true, capTab = 'overview', dashTab = 'fleet-health', glRange = '7d';
    const $ = s => document.querySelector(s), $$ = s => document.querySelectorAll(s);
    async function g(u) { const r = await fetch(u, { headers: { Authorization: authH } }); if (r.status === 401) { showLogin(); throw new Error('401') } if (!r.ok) throw new Error(r.status); return r.json() }
    function toast(msg, type = 'info') { const t = document.createElement('div'); t.className = 'toast t-' + type; t.textContent = msg; $('#toast-container').appendChild(t); requestAnimationFrame(() => t.classList.add('show')); setTimeout(() => { t.classList.remove('show'); setTimeout(() => t.remove(), 400) }, 3500) }
    function addNotif(msg, type = 'info') { notifs.unshift({ msg, type, time: new Date() }); renderNotifs() }
    function renderNotifs() { const b = $('#bell-badge'); b.textContent = notifs.length; b.style.display = notifs.length ? 'flex' : 'none'; $('#notif-list').innerHTML = notifs.length ? notifs.map(n => `<div class="notif-item n-${n.type}"><span>${n.msg}</span><span class="notif-time">${n.time.toLocaleTimeString()}</span></div>`).join('') : '<div class="notif-empty">No notifications</div>' }
    $('#notif-bell').onclick = () => $('#notif-drawer').classList.toggle('open');
    $('#notif-clear').onclick = () => { notifs = []; renderNotifs() }; renderNotifs();

    function animNum(el, target, suffix = '', dur = 1000) { const s = performance.now(); (function t(now) { const p = Math.min((now - s) / dur, 1), e = 1 - Math.pow(1 - p, 3), v = (target * e); el.textContent = (Number.isInteger(target) ? Math.round(v) : v.toFixed(1)) + suffix; if (p < 1) requestAnimationFrame(t) })(performance.now()) }
    function spark(data, w = 60, h = 20, color = '#3b82f6') { if (!data || data.length < 2) return ''; const mx = Math.max(...data), mn = Math.min(...data), rng = mx - mn || 1; const pts = data.map((v, i) => [i / (data.length - 1) * w, h - (v - mn) / rng * h]); return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><polyline points="${pts.map(p => p.join(',')).join(' ')}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linecap="round"/></svg>` }
    function mockRange(base, v, range) { const counts = { '7d': 7, '30d': 30, '90d': 90, '6mo': 180, '1yr': 365 }; return Array.from({ length: counts[range] || 7 }, () => base + ((Math.random() - .5) * 2 * v)) }
    function rangeLabels(range) { const n = { '7d': 7, '30d': 30, '90d': 90, '6mo': 180, '1yr': 365 }[range] || 7; const labels = []; const d = new Date(); for (let i = n - 1; i >= 0; i--) { const dt = new Date(d); dt.setDate(d.getDate() - i); labels.push(range === '7d' ? ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][dt.getDay()] : (dt.getMonth() + 1) + '/' + dt.getDate()) } return labels }
    const SC = { provisioning: '#a855f7', burn_in: '#f97316', testing: '#3b82f6', certified_ready: '#22c55e', customer_assigned: '#06b6d4', draining: '#eab308', emergency_drain: '#ef4444', scheduled_maintenance: '#eab308', repair: '#f97316', rma: '#ef4444', decommissioned: '#5d6177' };

    /* Chart with legends BELOW */
    function drawChart(el, legendEl, datasets, labels) {
        el.innerHTML = ''; const c = document.createElement('canvas'); const W = el.offsetWidth || 500, H = el.offsetHeight || 160; c.width = W; c.height = H; el.appendChild(c); const ctx = c.getContext('2d'); const p = { t: 12, r: 12, b: 28, l: 48 }, cw = W - p.l - p.r, ch = H - p.t - p.b;
        ctx.fillStyle = 'rgba(10,15,30,.4)'; ctx.fillRect(0, 0, W, H);
        const allV = datasets.flatMap(d => d.data); const mn = Math.min(...allV), mx = Math.max(...allV), rng = mx - mn || 1;
        ctx.strokeStyle = 'rgba(59,130,246,.06)'; ctx.lineWidth = 1;
        for (let i = 0; i <= 4; i++) { const y = p.t + ch * (i / 4); ctx.beginPath(); ctx.moveTo(p.l, y); ctx.lineTo(W - p.r, y); ctx.stroke(); ctx.fillStyle = 'rgba(148,163,184,.5)'; ctx.font = '11px Inter'; ctx.textAlign = 'right'; ctx.fillText((mx - rng * i / 4).toFixed(1), p.l - 6, y + 4) }
        ctx.textAlign = 'center'; ctx.fillStyle = 'rgba(148,163,184,.5)'; ctx.font = '11px Inter';
        const step = Math.max(1, Math.ceil(labels.length / 10));
        labels.forEach((l, i) => { if (i % step === 0) { ctx.fillText(l, p.l + cw * i / (labels.length - 1), H - 6) } });
        datasets.forEach(ds => {
            ctx.beginPath(); ctx.strokeStyle = ds.color; ctx.lineWidth = 2; ctx.lineJoin = 'round'; ds.data.forEach((v, i) => { const x = p.l + cw * i / (ds.data.length - 1), y = p.t + ch * (1 - (v - mn) / rng); i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y) }); ctx.stroke();
            const grd = ctx.createLinearGradient(0, p.t, 0, p.t + ch); grd.addColorStop(0, ds.color.replace(')', ',0.12)').replace('rgb', 'rgba')); grd.addColorStop(1, ds.color.replace(')', ',0)').replace('rgb', 'rgba')); ctx.lineTo(p.l + cw, p.t + ch); ctx.lineTo(p.l, p.t + ch); ctx.closePath(); ctx.fillStyle = grd; ctx.fill()
        });
        if (legendEl) legendEl.innerHTML = datasets.map(ds => `<span class="lg-item"><span class="lg-dot" style="background:${ds.color}"></span>${ds.label}</span>`).join('');
    }

    function mkRing(id, val, label, color, sz = 110) { return `<div class="ring-box"><svg class="ring-svg" viewBox="0 0 120 120" width="${sz}" height="${sz}"><circle class="ring-bg" cx="60" cy="60" r="52"/><circle class="ring-fill" id="${id}" cx="60" cy="60" r="52"/></svg><div class="ring-text"><span class="ring-val">${val.toFixed(1)}</span><span class="ring-lbl">${label}</span></div></div>` }
    function animRing(el, val, color) { const c = 2 * Math.PI * 52, off = c - (val / 100) * c; el.style.stroke = color; el.style.strokeDasharray = c; el.style.strokeDashoffset = c; el.getBoundingClientRect(); el.style.strokeDashoffset = off }
    function setBreadcrumb(items) { if (!items || items.length <= 1) { $('#breadcrumb').style.display = 'none'; return } $('#breadcrumb').style.display = 'block'; $('#breadcrumb-inner').innerHTML = items.map((it, i) => i < items.length - 1 ? `<span class="bc-link" onclick="${it.action || ''}">${it.label}</span><span class="bc-sep">/</span>` : `<span class="bc-current">${it.label}</span>`).join('') }

    /* Auth */
    function showLogin() { $('.login-overlay').classList.remove('hidden'); $('#app-shell').style.display = 'none' }
    function hideLogin() { $('.login-overlay').classList.add('hidden'); $('#app-shell').style.display = 'block' }
    $('#login-form').addEventListener('submit', async e => { e.preventDefault(); $('#login-spinner').style.display = 'inline-block'; $('#login-btn-text').textContent = 'Signing in...'; const u = $('#login-user').value, p = $('#login-pass').value; authH = 'Basic ' + btoa(u + ':' + p); try { const r = await fetch(API + '/auth/check', { headers: { Authorization: authH } }); if (!r.ok) throw 0; hideLogin(); $('#nav-user').textContent = u; toast('Welcome, ' + u, 'success'); init() } catch { $('#login-error').style.display = 'block'; $('#login-error').textContent = 'Invalid credentials'; toast('Authentication failed', 'error') } finally { $('#login-spinner').style.display = 'none'; $('#login-btn-text').textContent = 'Sign In' } });
    $('#logout-btn').onclick = () => { authH = ''; N = []; showLogin(); toast('Signed out', 'info'); $('#login-user').value = ''; $('#login-pass').value = ''; $('#login-error').style.display = 'none' };

    /* Nav */
    $$('.nav-tab').forEach(t => t.addEventListener('click', () => { switchView(t.dataset.view); $$('.nav-tab').forEach(x => x.classList.remove('active')); t.classList.add('active') }));
    function switchView(v) { cView = v; $$('.view').forEach(x => x.classList.remove('active')); const el = $('#v-' + v); if (el) el.classList.add('active'); setBreadcrumb([{ label: 'CIC', action: "switchView('global')" }, { label: v.charAt(0).toUpperCase() + v.slice(1) }]); const m = { global: loadGlobal, capacity: loadCapacity, health: loadHealth, incidents: loadIncidents, help: loadHelp }; if (m[v]) m[v]() }

    /* Sub-tab wiring */
    function wireSubTabs(containerSel, loadFns) {
        $$(containerSel + ' .sub-tab').forEach(t => t.addEventListener('click', () => {
            $$(containerSel + ' .sub-tab').forEach(x => x.classList.remove('active')); t.classList.add('active');
            $$(containerSel).forEach(p => { const panels = p.parentElement.querySelectorAll('.sub-panel'); panels.forEach(x => x.classList.remove('active')); const target = p.parentElement.querySelector('#sub-' + t.dataset.sub); if (target) target.classList.add('active') });
            if (loadFns && loadFns[t.dataset.sub]) loadFns[t.dataset.sub]();
        }));
    }

    /* CmdK */
    let cmdkOpen = false, cmdkIdx = 0, cmdkItems = [];
    function openCmdk() { cmdkOpen = true; $('#cmdk-overlay').classList.add('open'); $('#cmdk-input').value = ''; $('#cmdk-input').focus(); renderCmdkR('') }
    function closeCmdk() { cmdkOpen = false; $('#cmdk-overlay').classList.remove('open') }
    $('#open-cmdk').onclick = openCmdk; $('#cmdk-overlay').onclick = e => { if (e.target.id === 'cmdk-overlay') closeCmdk() };
    $('#cmdk-input').oninput = e => renderCmdkR(e.target.value);
    $('#cmdk-input').onkeydown = e => { if (e.key === 'ArrowDown') { cmdkIdx = Math.min(cmdkIdx + 1, cmdkItems.length - 1); hlCmdk() } else if (e.key === 'ArrowUp') { cmdkIdx = Math.max(cmdkIdx - 1, 0); hlCmdk() } else if (e.key === 'Enter' && cmdkItems[cmdkIdx]) { cmdkItems[cmdkIdx].action(); closeCmdk() } };
    function renderCmdkR(q) {
        q = q.toLowerCase(); cmdkItems = [];
        ['Global View:global', 'Capacity:capacity', 'Health:health', 'Incidents:incidents', 'Help:help'].forEach(s => { const [l, k] = s.split(':'); if (!q || l.toLowerCase().includes(q)) cmdkItems.push({ label: l, type: 'View', action: () => { switchView(k); $$('.nav-tab').forEach(x => x.classList.toggle('active', x.dataset.view === k)) } }) });
        N.forEach(n => { if (!q || n.id.includes(q) || n.sku.toLowerCase().includes(q)) cmdkItems.push({ label: n.id, type: n.sku, action: () => window._showDP(n.id) }) });
        cmdkItems = cmdkItems.slice(0, 12); cmdkIdx = 0; $('#cmdk-results').innerHTML = cmdkItems.length ? cmdkItems.map((it, i) => `<div class="cmdk-item${i === 0 ? ' active' : ''}" data-i="${i}">${it.label}<span class="cmdk-type">${it.type}</span></div>`).join('') : '<div class="cmdk-empty">No results</div>';
        $$('.cmdk-item').forEach(el => { el.onmouseenter = () => { $$('.cmdk-item').forEach(x => x.classList.remove('active')); el.classList.add('active'); cmdkIdx = +el.dataset.i }; el.onclick = () => { cmdkItems[+el.dataset.i].action(); closeCmdk() } })
    }
    function hlCmdk() { $$('.cmdk-item').forEach((x, i) => x.classList.toggle('active', i === cmdkIdx)) }

    /* Keys */
    let gP = false; document.addEventListener('keydown', e => { if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return; if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); openCmdk(); return } if (e.key === '/') { e.preventDefault(); openCmdk(); return } if (e.key === 'Escape') { closeCmdk(); $('#detail-panel').classList.remove('open'); $('#notif-drawer').classList.remove('open'); $('#node-diagram-overlay').classList.remove('open'); return } if (e.key === 'g') { gP = true; setTimeout(() => gP = false, 800); return } if (gP) { gP = false; const m = { g: 'global', c: 'capacity', h: 'health', i: 'incidents', p: 'help' }; const v = m[e.key.toLowerCase()]; if (v) { switchView(v); $$('.nav-tab').forEach(x => x.classList.toggle('active', x.dataset.view === v)) } } });
    $('#hero-collapse').onclick = () => $('.hero-banner').classList.toggle('collapsed');
    $('#nd-close').onclick = () => $('#node-diagram-overlay').classList.remove('open');
    $('#node-diagram-overlay').onclick = e => { if (e.target.id === 'node-diagram-overlay') e.target.classList.remove('open') };

    /* Particles */
    function initParticles() { const c = $('#particle-canvas'); if (!c) return; const x = c.getContext('2d'); let P = []; function rs() { c.width = innerWidth; c.height = innerHeight } rs(); addEventListener('resize', rs); for (let i = 0; i < 50; i++)P.push({ x: Math.random() * c.width, y: Math.random() * c.height, vx: (Math.random() - .5) * .15, vy: (Math.random() - .5) * .15, r: Math.random() * 1 + .3, o: Math.random() * .2 + .05, co: ['59,130,246', '139,92,246', '6,182,212'][Math.floor(Math.random() * 3)] }); (function d() { x.clearRect(0, 0, c.width, c.height); P.forEach(p => { p.x += p.vx; p.y += p.vy; if (p.x < 0) p.x = c.width; if (p.x > c.width) p.x = 0; if (p.y < 0) p.y = c.height; if (p.y > c.height) p.y = 0; x.beginPath(); x.arc(p.x, p.y, p.r, 0, Math.PI * 2); x.fillStyle = 'rgba(' + p.co + ',' + p.o + ')'; x.fill() }); for (let i = 0; i < P.length; i++)for (let j = i + 1; j < P.length; j++) { const d = Math.hypot(P[i].x - P[j].x, P[i].y - P[j].y); if (d < 120) { x.beginPath(); x.moveTo(P[i].x, P[i].y); x.lineTo(P[j].x, P[j].y); x.strokeStyle = 'rgba(59,130,246,' + (1 - d / 120) * .03 + ')'; x.lineWidth = .3; x.stroke() } } if (!document.hidden) requestAnimationFrame(d) })() }

    /* ═══════════════ GLOBAL VIEW ═══════════════ */
    async function loadGlobal() {
        topo = await g(API + '/topology'); const pw = await g(API + '/power/summary'); const tN = N.length, tGPU = N.filter(n => n.type === 'gpu').reduce((a, n) => a + n.gpu_count, 0), hy = N.filter(n => n.health_score >= .8).length, avgH = (N.reduce((a, n) => a + n.health_score, 0) / N.length) * 100, gpuA = N.filter(n => n.type === 'gpu' && n.state === 'customer_assigned').reduce((a, n) => a + n.gpu_count, 0), gpuU = tGPU ? (gpuA / tGPU * 100) : 0;
        /* Time range buttons */
        $$('#gl-time-range .tr-btn').forEach(b => { b.classList.toggle('active', b.dataset.range === glRange); b.onclick = () => { glRange = b.dataset.range; $$('#gl-time-range .tr-btn').forEach(x => x.classList.toggle('active', x.dataset.range === glRange)); renderGlobalCharts(avgH, pw, gpuU) } });
        $('#gl-kpis').innerHTML = [['Region', 'ap-korea-1'], ['AZs', '2'], ['Nodes', tN], ['GPUs', tGPU], ['Power', pw.total_power_kw + ' kW'], ['Health', avgH.toFixed(1) + '%']].map(([l, v], i) => `<div class="kpi-tile anim-in" style="--d:${i * .04}s"><span class="kpi-l">${l}</span><span class="kpi-v${l === 'Health' ? (avgH >= 80 ? ' kpi-ok' : ' kpi-warn') : ''}" id="kpi${i}">${v}</span></div>`).join('');
        const gpuN = N.filter(n => n.type === 'gpu'), cpuN = N.filter(n => n.type === 'cpu');
        const gpuStates = {}, cpuStates = {}; gpuN.forEach(n => { gpuStates[n.state] = (gpuStates[n.state] || 0) + 1 }); cpuN.forEach(n => { cpuStates[n.state] = (cpuStates[n.state] || 0) + 1 });
        $('#gl-rings').innerHTML = mkRing('rh', avgH, 'Health', avgH >= 80 ? '#22c55e' : '#f59e0b') + mkRing('rg', gpuU, 'GPU Util', gpuU >= 60 ? '#22c55e' : '#3b82f6') + mkRing('rp', pw.total_power_kw / 600 * 100, 'Power/600kW', '#8b5cf6');
        setTimeout(() => { ['rh', 'rg', 'rp'].forEach((id, i) => { const el = $('#' + id); if (!el) return; const vals = [avgH, gpuU, pw.total_power_kw / 600 * 100], colors = [avgH >= 80 ? '#22c55e' : '#f59e0b', gpuU >= 60 ? '#22c55e' : '#3b82f6', '#8b5cf6']; animRing(el, vals[i], colors[i]) }) }, 50);
        /* GPU/CPU state donut charts */
        function drawDonut(containerId, states, total, title) {
            const el = document.getElementById(containerId); if (!el) return;
            const sz = 130, cx = sz / 2, cy = sz / 2, r = 48, lw = 16;
            const sorted = Object.entries(states).sort((a, b) => b[1] - a[1]);
            el.innerHTML = '<div style="text-align:center"><canvas id="' + containerId + '-c" width="' + sz + '" height="' + sz + '"></canvas><div class="donut-label">' + title + ' (' + total + ')</div><div class="donut-legend">' + sorted.map(([s, c]) => '<span class="donut-lg-item"><span class="donut-lg-dot" style="background:' + (SC[s] || '#555') + '"></span>' + s.replace(/_/g, ' ') + ' ' + c + '</span>').join('') + '</div></div>';
            const cvs = document.getElementById(containerId + '-c'); if (!cvs) return;
            const ctx = cvs.getContext('2d'); let angle = -Math.PI / 2;
            sorted.forEach(([s, c]) => {
                const slice = (c / total) * Math.PI * 2;
                ctx.beginPath(); ctx.arc(cx, cy, r, angle, angle + slice); ctx.lineWidth = lw; ctx.strokeStyle = SC[s] || '#555'; ctx.stroke();
                angle += slice;
            });
            ctx.fillStyle = 'rgba(226,232,240,.7)'; ctx.font = 'bold 16px Inter'; ctx.textAlign = 'center'; ctx.fillText(total, cx, cy + 6);
        }
        const stEl = $('#gl-node-states');
        if (stEl) {
            stEl.innerHTML = '<div class="donut-row"><div id="gpu-donut"></div><div id="cpu-donut"></div></div>';
            setTimeout(() => { drawDonut('gpu-donut', gpuStates, gpuN.length, 'GPU Nodes'); drawDonut('cpu-donut', cpuStates, cpuN.length, 'CPU Nodes') }, 60);
        }
        renderGlobalCharts(avgH, pw, gpuU);
        renderRackElevation();
        renderNetworkTopo();
        /* Korea Map with AZ markers */
        let h = '<div class="korea-map-section"><div class="korea-map-wrap"><svg class="korea-map" viewBox="0 0 400 500" xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="mg" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="rgba(59,130,246,.12)"/><stop offset="100%" stop-color="rgba(139,92,246,.06)"/></linearGradient></defs><path d="M180 60 C200 50 230 55 250 70 C270 85 290 100 300 130 C310 155 315 180 310 210 C305 240 295 260 285 280 C275 300 265 320 260 340 C255 355 245 370 230 380 C218 388 205 395 195 405 C188 412 182 420 175 425 C165 415 158 405 150 395 C140 380 130 365 125 345 C118 320 115 300 110 275 C105 250 100 225 105 200 C108 175 120 150 135 130 C148 112 165 90 180 60Z" fill="url(#mg)" stroke="rgba(59,130,246,.25)" stroke-width="1.5"/><text x="200" y="130" text-anchor="middle" fill="rgba(226,232,240,.3)" font-size="14" font-family="Inter" font-weight="600">ap-korea-1</text>';
        topo.forEach((reg, ri) => {
            reg.azs.forEach((az, ai) => {
                const cx = 160 + ai * 80, cy = 220 + ri * 80;
                const hp = az.node_count ? ((az.healthy / az.node_count) * 100) : 0;
                const col = hp >= 80 ? '#22c55e' : hp >= 50 ? '#f59e0b' : '#ef4444';
                h += '<circle cx="' + cx + '" cy="' + cy + '" r="22" fill="' + col + '" opacity=".12" stroke="' + col + '" stroke-width="2" class="map-az-dot" onclick="window._drillAZ(\'' + reg.region + '\',\'' + az.az + '\')"/>';
                h += '<circle cx="' + cx + '" cy="' + cy + '" r="7" fill="' + col + '" opacity=".9" class="map-az-dot" onclick="window._drillAZ(\'' + reg.region + '\',\'' + az.az + '\')"/>';
                h += '<text x="' + cx + '" y="' + (cy + 35) + '" text-anchor="middle" fill="rgba(226,232,240,.8)" font-size="12" font-family="Inter" font-weight="600">' + az.az.toUpperCase() + '</text>';
                h += '<text x="' + cx + '" y="' + (cy + 48) + '" text-anchor="middle" fill="' + col + '" font-size="10" font-family="JetBrains Mono" font-weight="700">' + hp.toFixed(0) + '% · ' + az.node_count + ' nodes</text>';
            });
        });
        h += '</svg><div class="map-legend"><span class="map-legend-title">ap-korea-1 Region — Click an AZ to drill down</span></div></div></div>';
        $('#gl-regions').innerHTML = h;
        $('#nav-count').textContent = tN + ' nodes'; setBreadcrumb(null)
    }

    /* ─── Rack Elevation (Global View) ─── */
    function renderRackElevation() {
        const racks = {};
        N.forEach(n => {
            const r = n.rack || 'unassigned';
            if (!racks[r]) racks[r] = { nodes: [], az: n.az || '', env: n.environment || '', power: 0, gpus: 0 };
            racks[r].nodes.push(n);
            racks[r].power += n.power_draw_kw || 0;
            racks[r].gpus += n.gpu_count || 0;
        });
        const rackNames = Object.keys(racks).sort();
        let h = '<div class="rack-elev-grid">';
        rackNames.forEach(rk => {
            const rd = racks[rk];
            const hy = rd.nodes.filter(n => n.health_score >= .8).length;
            const hp = rd.nodes.length ? ((hy / rd.nodes.length) * 100) : 0;
            h += `<div class="rev-rack"><div class="rev-rack-head"><span class="rev-rack-name">${rk}</span><span class="rev-rack-meta">${rd.nodes.length} nodes · ${rd.gpus} GPUs</span><span class="rev-rack-power">${rd.power.toFixed(0)}kW</span></div><div class="rev-rack-body">`;
            // Show slots from top (highest position) to bottom
            const maxU = Math.max(...rd.nodes.map(n => n.position || 1), 10);
            for (let u = maxU; u >= 1; u--) {
                const nd = rd.nodes.find(n => n.position === u);
                if (nd) {
                    const hc = nd.health_score >= .8 ? '#22c55e' : nd.health_score >= .5 ? '#f59e0b' : '#ef4444';
                    const sc = SC[nd.state] || '#555';
                    h += `<div class="rev-slot filled" style="--sc:${sc}" onclick="window._showDP('${nd.id}')" title="${nd.id} — ${nd.state.replace(/_/g, ' ')} — ${(nd.health_score * 100).toFixed(0)}%"><span class="rev-u">U${u}</span><span class="rev-id">${nd.id}</span><span class="rev-sku">${nd.sku}</span><span class="rev-hp" style="color:${hc}">${(nd.health_score * 100).toFixed(0)}%</span></div>`;
                } else if (u % 3 === 0) {
                    h += `<div class="rev-slot empty"><span class="rev-u">U${u}</span></div>`;
                }
            }
            h += `</div><div class="rev-rack-foot"><div class="hbar"><div class="hbar-bg"><div class="hbar-fill" style="width:${hp}%;background:${hp >= 80 ? '#22c55e' : '#f59e0b'}"></div></div>${hp.toFixed(0)}%</div></div></div>`;
        });
        h += '</div>';
        const el = $('#gl-rack-elevation'); if (el) el.innerHTML = h;
    }

    /* ─── Network Topology (Global View) ─── */
    function renderNetworkTopo() {
        const racks = {};
        N.forEach(n => { const r = n.rack || 'unassigned'; if (!racks[r]) racks[r] = []; racks[r].push(n) });
        const rackNames = Object.keys(racks).sort();
        const totalRacks = rackNames.length;
        // Simulated spine switches
        const spines = [{ name: 'SPINE-01', bw: '400Gbps', tput: '1.3 Tbps', status: 'ok' }, { name: 'SPINE-02', bw: '400Gbps', tput: '1.2 Tbps', status: 'ok' }];
        // ToR leaf switches per rack
        const totalBw = N.reduce((a, n) => a + (n.power_draw_kw || 0), 0);
        const avgLat = (1.2 + Math.random() * 0.8).toFixed(1);

        let h = '<div class="net-topo-wrap">';
        // KPIs
        h += `<div class="net-kpis"><span class="fk">Spine Switches: <b>${spines.length}</b></span><span class="fk">Leaf Switches: <b>${totalRacks}</b></span><span class="fk ok">Avg Latency: <b>${avgLat}ms</b></span><span class="fk">Total Links: <b>${totalRacks * 2}</b></span></div>`;

        // SVG topology
        const maxNodesPerRack = Math.max(...rackNames.map(rk => racks[rk].length), 1);
        const svgW = Math.max(800, totalRacks * 90 + 100);
        const spineY = 40, leafY = 150, nodeY = 250;
        const svgH = Math.max(320, nodeY + maxNodesPerRack * 18 + 30);
        h += `<div class="net-topo-svg-wrap"><svg class="net-topo-svg" viewBox="0 0 ${svgW} ${svgH}" xmlns="http://www.w3.org/2000/svg">`;
        // Draw spines
        const spineCX = [];
        spines.forEach((sp, i) => {
            const cx = svgW / (spines.length + 1) * (i + 1);
            spineCX.push(cx);
            h += `<rect x="${cx - 45}" y="${spineY - 15}" width="90" height="30" rx="6" fill="rgba(59,130,246,.15)" stroke="#3b82f6" stroke-width="1.5"/>`;
            h += `<text x="${cx}" y="${spineY + 5}" text-anchor="middle" fill="#e2e8f0" font-size="11" font-family="JetBrains Mono">${sp.name}</text>`;
        });
        // Draw leafs (ToR) and connections
        const leafCX = [];
        rackNames.forEach((rk, i) => {
            const cx = 50 + i * ((svgW - 100) / Math.max(totalRacks - 1, 1));
            leafCX.push(cx);
            const rNodes = racks[rk];
            const avgH = rNodes.reduce((a, n) => a + n.health_score, 0) / rNodes.length;
            const col = avgH >= .8 ? '#22c55e' : avgH >= .5 ? '#f59e0b' : '#ef4444';
            // Link utilization (simulated)
            const util = Math.random() * 100;
            const linkCol = util > 80 ? '#ef4444' : util > 50 ? '#f59e0b' : '#22c55e';
            // Draw connections to spines
            spineCX.forEach(sx => {
                h += `<line x1="${sx}" y1="${spineY + 15}" x2="${cx}" y2="${leafY - 15}" stroke="${linkCol}" stroke-width="1.5" opacity=".5"/>`;
            });
            // Leaf switch
            h += `<rect x="${cx - 30}" y="${leafY - 12}" width="60" height="24" rx="4" fill="rgba(${col === '#22c55e' ? '34,197,94' : col === '#f59e0b' ? '245,158,11' : '239,68,68'},.12)" stroke="${col}" stroke-width="1"/>`;
            h += `<text x="${cx}" y="${leafY + 4}" text-anchor="middle" fill="${col}" font-size="9" font-family="JetBrains Mono">${rk}</text>`;
            // Draw ALL nodes below leaf
            rNodes.forEach((nd, ni) => {
                const ny = nodeY + ni * 18;
                const nc = nd.health_score >= .8 ? '#22c55e' : '#ef4444';
                h += `<line x1="${cx}" y1="${leafY + 12}" x2="${cx}" y2="${ny - 5}" stroke="rgba(148,163,184,.15)" stroke-width="1"/>`;
                h += `<rect x="${cx - 22}" y="${ny - 7}" width="44" height="14" rx="3" fill="rgba(${nc === '#22c55e' ? '34,197,94' : '239,68,68'},.08)" stroke="${nc}" stroke-width=".5" class="topo-node" onclick="window._showDP('${nd.id}')"/>`;
                h += `<text x="${cx}" y="${ny + 3}" text-anchor="middle" fill="rgba(226,232,240,.6)" font-size="7" font-family="JetBrains Mono" class="topo-node" onclick="window._showDP('${nd.id}')">${nd.id.replace(/gpu-|cpu-/, '').substring(0, 10)}</text>`;
            });
        });
        h += '</svg></div>';

        // Link table
        h += `<div class="net-link-table"><table class="dt"><thead><tr><th>Leaf Switch</th><th>Nodes</th><th>IB Ports</th><th>Throughput</th><th>Latency</th><th>Link Util</th></tr></thead><tbody>`;
        rackNames.forEach(rk => {
            const rNodes = racks[rk];
            const ibPorts = rNodes.reduce((a, n) => a + (n.ib_ports || 0), 0) || rNodes.length * 4;
            const tput = (ibPorts * 50 + Math.random() * 200).toFixed(0);
            const lat = (0.8 + Math.random() * 1.2).toFixed(1);
            const util = (40 + Math.random() * 50).toFixed(0);
            const uc = util > 80 ? 'danger' : util > 50 ? 'warn' : 'ok';
            h += `<tr><td class="mono accent">${rk}</td><td>${rNodes.length}</td><td>${ibPorts}</td><td class="mono">${tput} Gbps</td><td class="mono">${lat} ms</td><td><div class="hbar"><div class="hbar-bg"><div class="hbar-fill" style="width:${util}%;background:${util > 80 ? '#ef4444' : util > 50 ? '#f59e0b' : '#22c55e'}"></div></div><span class="${uc}">${util}%</span></div></td></tr>`;
        });
        h += '</tbody></table></div></div>';
        const el = $('#gl-network-topo'); if (el) el.innerHTML = h;
    }

    function renderGlobalCharts(avgH, pw, gpuU) {
        const lbl = rangeLabels(glRange);
        setTimeout(() => {
            drawChart($('#gl-chart-health'), $('#gl-legend-health'), [{ label: 'Health %', data: mockRange(avgH, 5, glRange), color: 'rgb(34,197,94)' }], lbl);
            drawChart($('#gl-chart-power'), $('#gl-legend-power'), [{ label: 'Power kW', data: mockRange(pw.total_power_kw, 20, glRange), color: 'rgb(139,92,246)' }], lbl);
            drawChart($('#gl-chart-mom'), $('#gl-legend-mom'), [{ label: 'Current Month', data: mockRange(avgH, 4, glRange), color: 'rgb(59,130,246)' }, { label: 'Previous Month', data: mockRange(avgH - 3, 5, glRange), color: 'rgb(100,116,139)' }], lbl);
            drawChart($('#gl-chart-util'), $('#gl-legend-util'), [{ label: 'GPU Utilization %', data: mockRange(gpuU, 8, glRange), color: 'rgb(6,182,212)' }], lbl);
            const slaEl = $('#gl-chart-sla'); if (slaEl) drawChart(slaEl, $('#gl-legend-sla'), [{ label: 'SLA Availability %', data: mockRange(avgH, 3, glRange).map(v => Math.min(100, v)), color: 'rgb(34,197,94)' }, { label: 'Target 99.5%', data: Array(mockRange(1, 0, glRange).length).fill(99.5), color: 'rgb(100,116,139)' }], lbl);
            const incEl = $('#gl-chart-inc'); if (incEl) drawBarChart(incEl, $('#gl-legend-inc'), [{ label: 'New', data: mockRange(2, 1.5, glRange).map(v => Math.max(0, Math.round(v))), color: 'rgb(239,68,68)' }, { label: 'Resolved', data: mockRange(1.5, 1, glRange).map(v => Math.max(0, Math.round(v))), color: 'rgb(34,197,94)' }], lbl);
        }, 80);
    }

    window._drillAZ = function (region, az) {
        const reg = topo.find(r => r.region === region); if (!reg) return; const azD = reg.azs.find(a => a.az === az); if (!azD) return;
        setBreadcrumb([{ label: 'Global', action: "switchView('global')" }, { label: region }, { label: az.toUpperCase() }]);
        const azNodes = N.filter(n => n.az === az);
        const gpuAZ = azNodes.filter(n => n.type === 'gpu'), cpuAZ = azNodes.filter(n => n.type === 'cpu');
        const gpuSt = {}, cpuSt = {}; gpuAZ.forEach(n => { gpuSt[n.state] = (gpuSt[n.state] || 0) + 1 }); cpuAZ.forEach(n => { cpuSt[n.state] = (cpuSt[n.state] || 0) + 1 });
        const p = $('#az-drill');
        let dh = `<div class="drill-header"><button class="drill-back" onclick="$('#az-drill').style.display='none';setBreadcrumb(null)">\u2190 Back to Map</button><h3>${az.toUpperCase()} \u2014 ${region}</h3><span class="dim">${azD.node_count} nodes \u00b7 ${azD.total_gpus} GPUs \u00b7 ${azD.rack_count} racks</span></div>`;
        /* Rack Elevation */
        dh += '<div class="section-header" style="margin-top:16px"><h2>Rack Elevation</h2></div><div class="rack-grid">';
        azD.racks.forEach(r => {
            dh += `<div class="rack-elevation"><div class="re-header"><span class="re-title">${r.rack}</span><span class="re-meta">${r.device_count} devices \u00b7 ${r.total_power_kw}kW</span></div><div class="re-body">`;
            for (let u = 42; u >= 1; u--) {
                const d = r.devices.find(x => x.position === u);
                if (d) { const hc = d.health >= .8 ? '#22c55e' : '#ef4444'; dh += `<div class="re-slot filled" style="--sc:${SC[d.state] || '#555'}" onclick="window._showDP('${d.id}')" title="${d.id}"><span class="re-u">U${u}</span><span class="re-id">${d.id}</span><span class="re-sku">${d.sku}</span><span class="re-pw">${d.power_kw}kW</span><span class="re-hp" style="color:${hc}">${(d.health * 100).toFixed(0)}%</span></div>`; }
                else if (u % 4 === 0) { dh += `<div class="re-slot empty"><span class="re-u">U${u}</span></div>`; }
            }
            dh += '</div></div>';
        });
        dh += '</div>';
        /* Network Topology for AZ */
        const rackNames = azD.racks.map(r => r.rack);
        const maxDevPerRack = Math.max(...azD.racks.map(r => r.devices.length), 1);
        const svgW = Math.max(600, rackNames.length * 100 + 100), svgH = Math.max(260, 135 + maxDevPerRack * 18 + 30);
        dh += `<div class="section-header" style="margin-top:20px"><h2>Network Topology \u2014 ${az.toUpperCase()}</h2></div>`;
        dh += `<div class="net-topo-svg-wrap"><svg class="net-topo-svg" viewBox="0 0 ${svgW} ${svgH}" xmlns="http://www.w3.org/2000/svg">`;
        dh += `<rect x="${svgW / 2 - 50}" y="15" width="100" height="28" rx="6" fill="rgba(59,130,246,.12)" stroke="#3b82f6" stroke-width="1.5"/>`;
        dh += `<text x="${svgW / 2}" y="34" text-anchor="middle" fill="#e2e8f0" font-size="11" font-family="JetBrains Mono">SPINE-01</text>`;
        rackNames.forEach((rk, i) => {
            const cx = 50 + i * ((svgW - 100) / Math.max(rackNames.length - 1, 1));
            const rData = azD.racks[i];
            const avgH2 = rData.devices.length ? rData.devices.reduce((a, d) => a + d.health, 0) / rData.devices.length : 1;
            const col = avgH2 >= .8 ? '#22c55e' : avgH2 >= .5 ? '#f59e0b' : '#ef4444';
            dh += `<line x1="${svgW / 2}" y1="43" x2="${cx}" y2="95" stroke="${col}" stroke-width="1.5" opacity=".4"/>`;
            dh += `<rect x="${cx - 30}" y="95" width="60" height="22" rx="4" fill="rgba(34,197,94,.08)" stroke="${col}" stroke-width="1"/>`;
            dh += `<text x="${cx}" y="110" text-anchor="middle" fill="${col}" font-size="9" font-family="JetBrains Mono">${rk}</text>`;
            rData.devices.forEach((d, di) => {
                const ny = 135 + di * 18; const nc = d.health >= .8 ? '#22c55e' : '#ef4444';
                dh += `<line x1="${cx}" y1="117" x2="${cx}" y2="${ny - 5}" stroke="rgba(148,163,184,.12)" stroke-width="1"/>`;
                dh += `<rect x="${cx - 22}" y="${ny - 7}" width="44" height="14" rx="3" fill="rgba(34,197,94,.06)" stroke="${nc}" stroke-width=".5" class="topo-node" onclick="window._showDP('${d.id}')"/>`;
                dh += `<text x="${cx}" y="${ny + 3}" text-anchor="middle" fill="rgba(226,232,240,.5)" font-size="7" font-family="JetBrains Mono">${d.id.replace(/gpu-|cpu-/, '').substring(0, 10)}</text>`;
            });
        });
        dh += '</svg></div>';
        /* Node State Distribution donuts */
        const allSt = {}; azNodes.forEach(n => { allSt[n.state] = (allSt[n.state] || 0) + 1 });
        dh += `<div class="section-header" style="margin-top:20px"><h2>Node State Distribution \u2014 ${az.toUpperCase()}</h2></div>`;
        dh += '<div class="donut-row" id="az-donuts"></div>';
        const sorted = Object.entries(allSt).sort((a, b) => b[1] - a[1]);
        const mx = Math.max(...sorted.map(x => x[1]), 1);
        dh += '<div class="state-bars" style="margin-top:8px">' + sorted.map(([s, c]) => `<div class="state-bar-row"><span class="state-bar-label">${s.replace(/_/g, ' ')}</span><div class="hbar"><div class="hbar-bg"><div class="hbar-fill" style="width:${c / mx * 100}%;background:${SC[s] || '#555'}"></div></div><span class="mono">${c}</span></div><span class="dim" style="min-width:40px;text-align:right">${(c / azNodes.length * 100).toFixed(0)}%</span></div>`).join('') + '</div>';
        p.innerHTML = dh; p.style.display = 'block';
        setTimeout(() => {
            const container = document.getElementById('az-donuts'); if (!container) return;
            container.innerHTML = '<div id="az-gpu-donut"></div><div id="az-cpu-donut"></div><div id="az-all-donut"></div>';
            drawDonut('az-gpu-donut', gpuSt, gpuAZ.length, 'GPU Nodes');
            drawDonut('az-cpu-donut', cpuSt, cpuAZ.length, 'CPU Nodes');
            drawDonut('az-all-donut', allSt, azNodes.length, 'All Nodes');
        }, 80);
        p.scrollIntoView({ behavior: 'smooth' })
    };
    window._drillRack = function (rk, az) { const reg = topo.find(r => r.azs.some(a => a.az === az)); if (reg) window._drillAZ(reg.region, az) };

    /* ═══════════════ CAPACITY (merged) ═══════════════ */
    async function loadCapacity() {
        wireSubTabs('#cap-sub-tabs', { 'cap-overview': loadCapOverview, 'cap-fleet': loadFleet, 'cap-bom': loadBOM });
        loadCapOverview();
    }
    async function loadCapOverview() {
        const pw = await g(API + '/power/summary'); const gpuT = N.filter(n => n.type === 'gpu').reduce((a, n) => a + n.gpu_count, 0), gpuA = N.filter(n => n.type === 'gpu' && n.state === 'customer_assigned').reduce((a, n) => a + n.gpu_count, 0), cpuT = N.filter(n => n.type === 'cpu').length;
        const utilP = gpuT ? (gpuA / gpuT * 100) : 0;
        $$('.cap-tab').forEach(t => { t.classList.toggle('active', t.dataset.cap === capTab); t.onclick = () => { capTab = t.dataset.cap; $$('.cap-tab').forEach(x => x.classList.toggle('active', x.dataset.cap === capTab)); renderCap() } });
        $('#cap-kpis').innerHTML = `<div class="fleet-kpi-row"><span class="fk">Total Nodes: <b>${N.length}</b></span><span class="fk">GPU Nodes: <b>${N.filter(n => n.type === 'gpu').length}</b></span><span class="fk ok">Assigned GPUs: <b>${gpuA}/${gpuT}</b></span><span class="fk ${utilP >= 70 ? 'ok' : 'warn'}">Utilization: <b>${utilP.toFixed(0)}%</b></span><span class="fk">CPU: <b>${cpuT}</b></span><span class="fk">Power: <b>${pw.total_power_kw} kW</b></span></div>`;
        function renderCap() {
            if (capTab === 'overview') { $('#cap-body').innerHTML = `<div class="kpi-grid">${[['Total GPUs', gpuT, ''], ['Assigned', gpuA, 'kpi-ok'], ['Available', gpuT - gpuA, ''], ['CPU Nodes', cpuT, ''], ['Utilization', utilP.toFixed(0) + '%', utilP >= 70 ? 'kpi-ok' : 'kpi-warn'], ['Power', pw.total_power_kw + ' kW', '']].map(([l, v, c]) => `<div class="kpi-tile"><span class="kpi-l">${l}</span><span class="kpi-v ${c}">${v}</span></div>`).join('')}</div><div class="ring-row">${mkRing('cr1', utilP, 'GPU Util', utilP >= 70 ? '#22c55e' : '#f59e0b', 130)}${mkRing('cr2', gpuT ? (((gpuT - gpuA) / gpuT) * 100) : 0, 'Available', '#3b82f6', 130)}</div>`; setTimeout(() => { const e = $('#cr1'); if (e) animRing(e, utilP, utilP >= 70 ? '#22c55e' : '#f59e0b'); const f = $('#cr2'); if (f) animRing(f, gpuT ? (((gpuT - gpuA) / gpuT) * 100) : 0, '#3b82f6') }, 50) }
            else {
                const groups = {}; const groupKey = capTab === 'env' ? 'environment' : capTab === 'sku' ? 'sku' : 'az'; N.forEach(n => { const k = groupKey === 'az' ? (n.az || '?').toUpperCase() : (n[groupKey] || '?'); if (!groups[k]) groups[k] = { nodes: 0, gpus: 0, assigned: 0, cpu: 0, power: 0, healthy: 0 }; groups[k].nodes++; if (n.type === 'gpu') { groups[k].gpus += n.gpu_count; if (n.state === 'customer_assigned') groups[k].assigned += n.gpu_count } else groups[k].cpu++; groups[k].power += n.power_draw_kw || 0; if (n.health_score >= .8) groups[k].healthy++ });
                $('#cap-body').innerHTML = `<div class="table-wrap"><table class="dt"><thead><tr><th>${groupKey === 'az' ? 'AZ' : groupKey === 'environment' ? 'Environment' : 'SKU'}</th><th>Nodes</th><th>GPUs</th><th>Assigned</th><th>Avail</th><th>CPU</th><th>Power</th><th>Util</th><th>Trend</th></tr></thead><tbody>${Object.entries(groups).map(([k, v]) => { const u = v.gpus ? (v.assigned / v.gpus * 100) : 0; return `<tr><td class="accent bold">${k}</td><td>${v.nodes}</td><td>${v.gpus}</td><td class="ok">${v.assigned}</td><td>${v.gpus - v.assigned}</td><td>${v.cpu}</td><td class="mono">${v.power.toFixed(1)}</td><td><div class="hbar"><div class="hbar-bg"><div class="hbar-fill" style="width:${u}%;background:${u >= 70 ? '#22c55e' : '#f59e0b'}"></div></div>${u.toFixed(0)}%</div></td><td>${spark(mockRange(u, 12, '7d'), 55, 18, u >= 70 ? '#22c55e' : '#f59e0b')}</td></tr>` }).join('')}</tbody></table></div>`
            }
        } renderCap();
        /* SLAs */
        const envs = {}; N.forEach(n => { const e = n.environment || 'Unknown'; if (!envs[e]) envs[e] = { total: 0, healthy: 0, gpu: 0, assigned: 0, power: 0 }; envs[e].total++; if (n.health_score >= .8) envs[e].healthy++; if (n.type === 'gpu') { envs[e].gpu += n.gpu_count; if (n.state === 'customer_assigned') envs[e].assigned += n.gpu_count } envs[e].power += n.power_draw_kw || 0 });
        const slaTargets = { 'KR1A Prod': 99.9, 'KR1B Dev': 99.0 };
        $('#sla-body').innerHTML = `<div class="sla-grid">${Object.entries(envs).map(([env, d]) => { const uptime = d.total ? (d.healthy / d.total * 100) : 0; const target = slaTargets[env] || 99.5; const met = uptime >= target; const gpuU = d.gpu ? (d.assigned / d.gpu * 100) : 0; return `<div class="sla-card"><div class="sla-env">${env}</div><div class="sla-metrics"><div class="sla-metric"><span class="sla-label">Uptime</span><span class="sla-value ${met ? 'ok' : 'danger'}">${uptime.toFixed(1)}%</span><span class="sla-target">Target: ${target}%</span></div><div class="sla-metric"><span class="sla-label">Nodes</span><span class="sla-value">${d.total}</span><span class="sla-target">${d.healthy} healthy</span></div><div class="sla-metric"><span class="sla-label">GPU Util</span><span class="sla-value ${gpuU >= 70 ? 'ok' : 'warn'}">${gpuU.toFixed(0)}%</span><span class="sla-target">${d.assigned}/${d.gpu} GPUs</span></div><div class="sla-metric"><span class="sla-label">Power</span><span class="sla-value">${d.power.toFixed(0)} kW</span><span class="sla-target">&nbsp;</span></div></div><div class="sla-bar"><div class="hbar"><div class="hbar-bg"><div class="hbar-fill" style="width:${uptime}%;background:${met ? '#22c55e' : '#ef4444'}"></div></div><span class="${met ? 'ok' : 'danger'}">${met ? '✓ SLA Met' : '✗ SLA Breach'}</span></div></div></div>` }).join('')}</div>`;
        setTimeout(() => { drawChart($('#cap-chart-util'), $('#cap-legend-util'), [{ label: 'GPU Util %', data: mockRange(utilP, 8, '7d'), color: 'rgb(6,182,212)' }, { label: 'Available %', data: mockRange(100 - utilP, 8, '7d'), color: 'rgb(139,92,246)' }], rangeLabels('7d')); drawChart($('#cap-chart-power'), $('#cap-legend-power'), [{ label: 'Power kW', data: mockRange(pw.total_power_kw, 25, '7d'), color: 'rgb(249,115,22)' }], rangeLabels('7d')) }, 100);
        /* State Distribution */
        renderStateDistribution();
    }
    function renderStateDistribution() {
        const azs = [...new Set(N.map(n => n.az).filter(Boolean))].sort();
        const el = $('#cap-state-dist');
        if (!el) return;
        const fHtml = `<div style="margin-bottom:8px;display:flex;gap:8px"><select id="sd-az" class="f-input" style="width:140px"><option value="">All AZs</option>${azs.map(a => `<option value="${a}">${a.toUpperCase()}</option>`).join('')}</select><select id="sd-type" class="f-input" style="width:140px"><option value="">All Types</option><option value="gpu">GPU</option><option value="cpu">CPU</option></select></div>`;
        function doRender() {
            const azF = $('#sd-az')?.value, typeF = $('#sd-type')?.value;
            let f = [...N]; if (azF) f = f.filter(n => n.az === azF); if (typeF) f = f.filter(n => n.type === typeF);
            const sc2 = {}; f.forEach(n => { sc2[n.state] = (sc2[n.state] || 0) + 1 });
            const s2 = Object.entries(sc2).sort((a, b) => b[1] - a[1]), mx = Math.max(...s2.map(x => x[1]), 1);
            const gF = f.filter(n => n.type === 'gpu'), cF = f.filter(n => n.type === 'cpu');
            const gA = gF.filter(n => n.state === 'customer_assigned').reduce((a, n) => a + n.gpu_count, 0), gT = gF.reduce((a, n) => a + n.gpu_count, 0);
            const gu = gT ? (gA / gT * 100) : 0, av = gT ? ((gT - gA) / gT * 100) : 0;
            el.innerHTML = fHtml + `<div class="ring-row" style="margin-bottom:12px">${mkRing('csd1', gu, 'GPU Util', gu >= 60 ? '#22c55e' : '#3b82f6', 90)}${mkRing('csd2', av, 'Available', '#8b5cf6', 90)}${mkRing('csd3', gF.length ? (gF.filter(n => n.health_score >= .8).length / gF.length * 100) : 0, 'GPU Health', '#06b6d4', 90)}${mkRing('csd4', cF.length ? (cF.filter(n => n.health_score >= .8).length / cF.length * 100) : 0, 'CPU Health', '#f97316', 90)}</div><div class="state-bars">${s2.map(([s, c]) => `<div class="state-bar-row"><span class="state-bar-label">${s.replace(/_/g, ' ')}</span><div class="hbar"><div class="hbar-bg"><div class="hbar-fill" style="width:${c / mx * 100}%;background:${SC[s] || '#555'}"></div></div><span class="mono">${c}</span></div><span class="dim" style="min-width:45px;text-align:right">${(c / f.length * 100).toFixed(1)}%</span></div>`).join('')}</div>`;
            setTimeout(() => { ['csd1', 'csd2', 'csd3', 'csd4'].forEach((id, i) => { const e2 = $('#' + id); if (!e2) return; animRing(e2, [gu, av, gF.length ? (gF.filter(n => n.health_score >= .8).length / gF.length * 100) : 0, cF.length ? (cF.filter(n => n.health_score >= .8).length / cF.length * 100) : 0][i], ['#22c55e', '#8b5cf6', '#06b6d4', '#f97316'][i]) }) }, 50);
            $('#sd-az').onchange = doRender; $('#sd-type').onchange = doRender;
        }
        el.innerHTML = fHtml; doRender();
        const sDescs = { provisioning: ['Provisioning', 'Node setup and initial configuration'], burn_in: ['Burn-In', 'Hardware stress testing'], testing: ['Testing', 'Validation and certification tests'], certified_ready: ['Certified Ready', 'Available for customer assignment'], customer_assigned: ['Customer Assigned', 'Running production workloads'], draining: ['Draining', 'Graceful workload evacuation'], emergency_drain: ['Emergency Drain', 'Urgent evacuation due to failure'], scheduled_maintenance: ['Scheduled Maintenance', 'Planned maintenance window'], repair: ['Repair', 'Active hardware/firmware remediation'], rma: ['RMA', 'Awaiting vendor replacement'], decommissioned: ['Decommissioned', 'Removed from fleet inventory'] };
        const sc3 = {}; N.forEach(n => { sc3[n.state] = (sc3[n.state] || 0) + 1 });
        const defsEl = $('#cap-state-defs');
        if (defsEl) {
            defsEl.innerHTML = `<div class="state-defs-table"><table class="dt"><thead><tr><th>State</th><th>Label</th><th>Description</th><th>Count</th></tr></thead><tbody>${Object.entries(sDescs).map(([k, [l, d]]) => { const c = sc3[k] || 0; return `<tr><td><span class="pill" style="background:${SC[k] || '#555'};color:#fff;font-size:.65rem">${k.replace(/_/g, ' ')}</span></td><td class="bold">${l}</td><td class="dim" style="font-size:.75rem">${d}</td><td class="mono bold">${c}</td></tr>` }).join('')}</tbody></table></div>`;
        }
    }


    /* Fleet Explorer (inside Capacity) */


    /* Fleet Explorer (inside Capacity) */
    function loadFleet() {
        const states = [...new Set(N.map(n => n.state))].sort(), azs = [...new Set(N.map(n => n.az))].sort(), skus = [...new Set(N.map(n => n.sku))].sort(), types = [...new Set(N.map(n => n.type))].sort(), racks = [...new Set(N.map(n => n.rack).filter(Boolean))].sort();
        $('#fleet-filters').innerHTML = `<select id="ff-s" class="f-input"><option value="">All States</option>${states.map(s => `<option>${s}</option>`).join('')}</select><select id="ff-a" class="f-input"><option value="">All AZs</option>${azs.map(a => `<option value="${a}">${a.toUpperCase()}</option>`).join('')}</select><select id="ff-sku" class="f-input"><option value="">All SKUs</option>${skus.map(s => `<option>${s}</option>`).join('')}</select><select id="ff-type" class="f-input"><option value="">All Types</option>${types.map(t => `<option>${t}</option>`).join('')}</select><input id="ff-q" class="f-input" placeholder="Search nodes..." style="width:200px">`;
        $('#fleet-filters2').innerHTML = `<select id="ff-rack" class="f-input"><option value="">All Racks</option>${racks.map(r => `<option>${r}</option>`).join('')}</select><select id="ff-health" class="f-input"><option value="">All Health</option><option value="healthy">Healthy (≥0.8)</option><option value="degraded">Degraded</option></select><select id="ff-cordon" class="f-input"><option value="">Cordon Status</option><option value="cordoned">Cordoned</option><option value="active">Active</option></select>`;
        const hs = N.filter(n => n.health_score >= .8).length, c = N.filter(n => n.cordon && n.cordon.active).length; $('#fleet-kpis').innerHTML = `<div class="fleet-kpi-row"><span class="fk">Total: <b>${N.length}</b></span><span class="fk ok">Healthy: <b>${hs}</b></span><span class="fk warn">Degraded: <b>${N.length - hs}</b></span><span class="fk danger">Cordoned: <b>${c}</b></span><span class="fk">GPU: <b>${N.filter(n => n.type === 'gpu').length}</b></span><span class="fk">CPU: <b>${N.filter(n => n.type === 'cpu').length}</b></span></div>`;
        const render = () => {
            let f = [...N]; const sv = $('#ff-s')?.value, av = $('#ff-a')?.value, q = $('#ff-q')?.value?.toLowerCase(), sk = $('#ff-sku')?.value, tp = $('#ff-type')?.value, rk = $('#ff-rack')?.value, hf = $('#ff-health')?.value, cf = $('#ff-cordon')?.value; if (sv) f = f.filter(n => n.state === sv); if (av) f = f.filter(n => n.az === av); if (sk) f = f.filter(n => n.sku === sk); if (tp) f = f.filter(n => n.type === tp); if (rk) f = f.filter(n => n.rack === rk); if (hf === 'healthy') f = f.filter(n => n.health_score >= .8); else if (hf === 'degraded') f = f.filter(n => n.health_score < .8); if (cf === 'cordoned') f = f.filter(n => n.cordon?.active); else if (cf === 'active') f = f.filter(n => !n.cordon?.active); if (q) f = f.filter(n => n.id.includes(q) || n.sku.toLowerCase().includes(q) || n.environment.toLowerCase().includes(q)); if (sortCol) f.sort((a, b) => { let va = a[sortCol], vb = b[sortCol]; if (typeof va === 'string') return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va); return sortAsc ? va - vb : vb - va });
            $('#fleet-count').textContent = f.length + '/' + N.length;
            $('#fleet-tbody').innerHTML = f.map(n => { const hp = n.health_score * 100, hc = hp >= 80 ? '#22c55e' : hp >= 50 ? '#f59e0b' : '#ef4444'; return `<tr onclick="window._showDP('${n.id}')"><td class="mono accent">${n.id}</td><td><span class="pill s-${n.state}">${n.state.replace(/_/g, ' ')}</span></td><td>${n.environment}</td><td>${n.sku}</td><td><div class="hbar"><div class="hbar-bg"><div class="hbar-fill" style="width:${hp}%;background:${hc}"></div></div>${n.health_score.toFixed(2)}</div></td><td>${spark(mockRange(n.health_score, 0.1, '7d'), 48, 16, hc)}</td><td class="mono">${(n.power_draw_kw || 0).toFixed(1)}</td><td>${n.cordon?.active ? '<span class="danger">' + n.cordon.reason + '</span>' : '—'}</td></tr>` }).join('')
        };
        render(); $$('#fleet-filters select, #fleet-filters input, #fleet-filters2 select').forEach(el => { el.onchange = render; if (el.tagName === 'INPUT') el.oninput = render });
        $$('#fleet-table th[data-sort]').forEach(th => { th.onclick = () => { const c = th.dataset.sort; if (sortCol === c) sortAsc = !sortAsc; else { sortCol = c; sortAsc = true } $$('#fleet-table th').forEach(x => x.classList.remove('sort-asc', 'sort-desc')); th.classList.add(sortAsc ? 'sort-asc' : 'sort-desc'); render() } });
        $('#fleet-export').onclick = () => { let csv = 'Node ID,State,Environment,SKU,Type,Health,Power kW,AZ,Rack,Cordon\n'; N.forEach(n => csv += `${n.id},${n.state},${n.environment},${n.sku},${n.type},${n.health_score},${n.power_draw_kw || 0},${n.az || ''},${n.rack || ''},${n.cordon?.active ? n.cordon.reason : ''}\n`); const b = new Blob([csv], { type: 'text/csv' }); const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = 'cic_fleet.csv'; a.click(); toast('Fleet exported', 'success') }
    }

    /* BOM (inside Capacity) */
    async function loadBOM() {
        const skus = [...new Set(N.map(n => n.sku))]; let allBom = [];
        for (const sku of skus) { const s = N.find(n => n.sku === sku); if (!s) continue; const bom = await g(API + '/nodes/' + s.id + '/bom'); allBom.push({ sku, bom, count: N.filter(n => n.sku === sku).length }) }
        const totalComps = allBom.reduce((a, b) => a + b.bom.components.length, 0), platforms = [...new Set(allBom.map(b => b.bom.platform))];
        $('#bom-count').textContent = allBom.length + ' SKUs';
        $('#bom-filters').innerHTML = `<select id="bf-sku" class="f-input"><option value="">All SKUs</option>${skus.map(s => `<option>${s}</option>`).join('')}</select><select id="bf-cat" class="f-input"><option value="">All Categories</option>${[...new Set(allBom.flatMap(b => b.bom.components.map(c => c.category)))].sort().map(c => `<option>${c}</option>`).join('')}</select><input id="bf-q" class="f-input" placeholder="Search parts..." style="width:200px">`;
        $('#bom-kpis').innerHTML = `<div class="fleet-kpi-row"><span class="fk">SKUs: <b>${skus.length}</b></span><span class="fk">Platforms: <b>${platforms.join(', ')}</b></span><span class="fk">Components: <b>${totalComps}</b></span><span class="fk">Nodes: <b>${N.length}</b></span></div>`;
        function renderBOM() {
            const sf = $('#bf-sku')?.value, cf = $('#bf-cat')?.value, qf = $('#bf-q')?.value?.toLowerCase(); let filtered = allBom; if (sf) filtered = filtered.filter(b => b.sku === sf);
            let h = ''; filtered.forEach(({ sku, bom, count }) => { let comps = bom.components; if (cf) comps = comps.filter(c => c.category === cf); if (qf) comps = comps.filter(c => c.part_name.toLowerCase().includes(qf) || c.category.toLowerCase().includes(qf) || (c.part_number || '').toLowerCase().includes(qf)); if (comps.length === 0 && (cf || qf)) return; h += `<div class="card"><div class="card-head"><span class="card-title">${bom.platform} — ${sku}</span><span class="dim">${count} nodes · ${comps.length} components</span></div><div class="card-body"><table class="dt"><thead><tr><th>Category</th><th>Part</th><th>P/N</th><th>Qty</th><th>FW</th></tr></thead><tbody>${comps.map(c => `<tr><td class="accent bold uc">${c.category}</td><td>${c.part_name}</td><td class="mono dim">${c.part_number || '—'}</td><td>${c.quantity}</td><td class="mono ${c.firmware_version ? 'ok' : 'dim'}">${c.firmware_version || '—'}</td></tr>`).join('')}</tbody></table></div></div>` }); $('#bom-body').innerHTML = h || '<div class="empty-state">No matching components</div>'
        }
        renderBOM(); $$('#bom-filters select, #bom-filters input').forEach(el => { el.onchange = renderBOM; if (el.tagName === 'INPUT') el.oninput = renderBOM });
        $('#bom-export').onclick = () => { let csv = 'SKU,Platform,Category,Part,P/N,Qty,FW\n'; allBom.forEach(({ sku, bom }) => bom.components.forEach(c => csv += `${sku},${bom.platform},${c.category},${c.part_name},${c.part_number || ''},${c.quantity},${c.firmware_version || ''}\n`)); const b = new Blob([csv], { type: 'text/csv' }); const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = 'cic_bom.csv'; a.click(); toast('BOM exported', 'success') }
    }

    /* ═══════════════ HEALTH (merged) ═══════════════ */
    async function loadHealth() {
        wireSubTabs('#health-sub-tabs', { 'health-fleet': loadFleetHealth, 'health-clusters': loadLogicalClusters, 'health-firmware': loadFirmware, 'health-dashboards': loadDashboards });
        loadFleetHealth();
    }
    async function loadFleetHealth() {
        const co = N.filter(n => n.cordon?.active), dg = N.filter(n => n.health_score < .8).sort((a, b) => a.health_score - b.health_score), ua = N.filter(n => n.type === 'gpu' && n.state === 'certified_ready' && !n.tenant);
        $('#hc-cordon').innerHTML = co.length ? `<table class="dt"><thead><tr><th>Node</th><th>SKU</th><th>Source</th><th>Priority</th><th>Reason</th><th>Health</th><th>Diagram</th></tr></thead><tbody>${co.map(n => `<tr><td class="mono accent clickable" onclick="window._showDP('${n.id}')">${n.id}</td><td>${n.sku}</td><td class="warn">${n.cordon.owner}</td><td><span class="pill s-${n.cordon.priority === 'P0' ? 'emergency_drain' : 'repair'}">${n.cordon.priority}</span></td><td>${n.cordon.reason || 'N/A'}</td><td><div class="hbar"><div class="hbar-bg"><div class="hbar-fill" style="width:${n.health_score * 100}%;background:${n.health_score >= .5 ? '#f59e0b' : '#ef4444'}"></div></div>${n.health_score.toFixed(2)}</div></td><td><button class="action-btn sm" onclick="window._showNodeDiagram('${n.id}')">🔍 View</button></td></tr>`).join('')}</tbody></table>` : '<div class="empty-state">✓ No cordoned nodes</div>';
        $('#hc-degraded').innerHTML = dg.length ? `<table class="dt"><thead><tr><th>Node</th><th>SKU</th><th>State</th><th>Health</th><th>Trend</th><th>Diagram</th></tr></thead><tbody>${dg.map(n => `<tr><td class="mono accent clickable" onclick="window._showDP('${n.id}')">${n.id}</td><td>${n.sku}</td><td><span class="pill s-${n.state}">${n.state.replace(/_/g, ' ')}</span></td><td class="danger bold mono">${n.health_score.toFixed(2)}</td><td>${spark(mockRange(n.health_score, 0.15, '7d'), 55, 18, '#ef4444')}</td><td><button class="action-btn sm" onclick="window._showNodeDiagram('${n.id}')">🔍 View</button></td></tr>`).join('')}</tbody></table>` : '<div class="empty-state">All nodes healthy</div>';
        $('#hc-available').innerHTML = ua.length ? `<table class="dt"><thead><tr><th>Node</th><th>SKU</th><th>AZ</th><th>GPUs</th><th>Health</th><th>Power</th></tr></thead><tbody>${ua.sort((a, b) => b.health_score - a.health_score).map(n => `<tr onclick="window._showDP('${n.id}')"><td class="mono accent">${n.id}</td><td>${n.sku}</td><td>${(n.az || '').toUpperCase()}</td><td>${n.gpu_count}</td><td class="ok mono bold">${n.health_score.toFixed(2)}</td><td class="mono">${(n.power_draw_kw || 0).toFixed(1)}</td></tr>`).join('')}</tbody></table>` : '<div class="empty-state">No unassigned nodes</div>'
    }
    /* ═══════════════ LOGICAL CLUSTERS ═══════════════ */
    async function loadLogicalClusters() {
        const incs = await g(API + '/incidents');
        /* Group nodes by environment (= logical cluster) */
        const clusters = {};
        N.forEach(n => {
            const env = n.environment || 'Unknown';
            if (!clusters[env]) clusters[env] = { nodes: [], gpuTotal: 0, gpuAssigned: 0, healthy: 0, power: 0, tenants: {} };
            clusters[env].nodes.push(n);
            if (n.type === 'gpu') { clusters[env].gpuTotal += n.gpu_count; if (n.state === 'customer_assigned') clusters[env].gpuAssigned += n.gpu_count }
            if (n.health_score >= .8) clusters[env].healthy++;
            clusters[env].power += n.power_draw_kw || 0;
            if (n.tenant) { if (!clusters[env].tenants[n.tenant]) clusters[env].tenants[n.tenant] = { gpus: 0, nodes: 0, healthy: 0 }; clusters[env].tenants[n.tenant].nodes++; clusters[env].tenants[n.tenant].gpus += n.gpu_count || 0; if (n.health_score >= .8) clusters[env].tenants[n.tenant].healthy++ }
        });
        const slaTargets = { 'KR1A Prod': 99.9, 'KR1A Dev': 99.0, 'KR1B Prod BMaaS': 99.9, 'KR1B Prod K8s': 99.5, 'KR1B Staging': 95.0 };

        /* Match incidents to clusters by environment or affected nodes */
        function clusterIncidents(env, clNodes) {
            return incs.filter(i => {
                if (i.environment === env) return true;
                const nids = new Set(clNodes.map(n => n.id));
                return (i.affected_nodes || []).some(a => nids.has(a));
            });
        }

        let h = '<div class="cluster-grid">';
        Object.entries(clusters).sort((a, b) => a[0].localeCompare(b[0])).forEach(([env, d]) => {
            const total = d.nodes.length;
            const uptime = total ? (d.healthy / total * 100) : 0;
            const target = slaTargets[env] || 99.5;
            const slaMet = uptime >= target;
            const gpuUtil = d.gpuTotal ? (d.gpuAssigned / d.gpuTotal * 100) : 0;
            const stC = {}; d.nodes.forEach(n => { stC[n.state] = (stC[n.state] || 0) + 1 });
            const stSorted = Object.entries(stC).sort((a, b) => b[1] - a[1]);
            const clIncs = clusterIncidents(env, d.nodes);
            const activeIncs = clIncs.filter(i => !i.resolved_at);
            const ringId = 'cl-ring-' + env.replace(/\s+/g, '-').toLowerCase();
            const tenantEntries = Object.entries(d.tenants);

            h += `<div class="cluster-card">`;
            /* Header with health ring */
            h += `<div class="cluster-header">`;
            h += `<div class="cluster-title-row"><span class="cluster-name">${env}</span><span class="cluster-meta">${total} nodes · ${d.gpuTotal} GPUs · ${d.power.toFixed(0)} kW</span></div>`;
            h += `<div class="cluster-ring">${mkRing(ringId, uptime, 'Health', uptime >= 80 ? '#22c55e' : '#f59e0b', 80)}</div>`;
            h += `</div>`;

            /* SLA section */
            h += `<div class="cluster-sla">`;
            h += `<div class="cluster-sla-row"><span class="cluster-sla-label">Uptime</span><span class="cluster-sla-val ${slaMet ? 'ok' : 'danger'}">${uptime.toFixed(1)}%</span></div>`;
            h += `<div class="cluster-sla-row"><span class="cluster-sla-label">SLA Target</span><span class="cluster-sla-val">${target}%</span></div>`;
            h += `<div class="cluster-sla-row"><span class="cluster-sla-label">Status</span><span class="cluster-sla-val ${slaMet ? 'ok' : 'danger'}">${slaMet ? '✓ SLA Met' : '✗ SLA Breach'}</span></div>`;
            h += `<div class="hbar" style="margin-top:6px"><div class="hbar-bg"><div class="hbar-fill" style="width:${uptime}%;background:${slaMet ? '#22c55e' : '#ef4444'}"></div></div></div>`;
            h += `</div>`;

            /* Node states */
            h += `<div class="cluster-states"><div class="cluster-section-title">Node States</div>`;
            h += stSorted.map(([s, c]) => `<div class="state-bar-row compact"><span class="state-bar-label">${s.replace(/_/g, ' ')}</span><div class="hbar"><div class="hbar-bg"><div class="hbar-fill" style="width:${c / total * 100}%;background:${SC[s] || '#555'}"></div></div><span class="mono">${c}</span></div></div>`).join('');
            h += `</div>`;

            /* Tenant assigned capacity with SLA */
            if (tenantEntries.length) {
                h += `<div class="cluster-tenants"><div class="cluster-section-title">Tenant Assigned Capacity</div>`;
                h += `<table class="dt compact"><thead><tr><th>Tenant</th><th>Nodes</th><th>GPUs</th><th>Healthy</th><th>SLA</th></tr></thead><tbody>`;
                tenantEntries.forEach(([t, td]) => {
                    const tSla = td.nodes ? (td.healthy / td.nodes * 100) : 0;
                    const tMet = tSla >= target;
                    h += `<tr><td class="mono accent">${t}</td><td>${td.nodes}</td><td>${td.gpus}</td><td class="${tSla >= 80 ? 'ok' : 'danger'}">${td.healthy}/${td.nodes}</td><td class="${tMet ? 'ok' : 'danger'}">${tSla.toFixed(0)}% ${tMet ? '✓' : '✗'}</td></tr>`;
                });
                h += `</tbody></table></div>`;
            }

            /* GPU Utilization */
            h += `<div class="cluster-gpu-util"><div class="cluster-section-title">GPU Utilization</div>`;
            h += `<div class="hbar"><div class="hbar-bg"><div class="hbar-fill" style="width:${gpuUtil}%;background:${gpuUtil >= 60 ? '#22c55e' : '#f59e0b'}"></div></div><span class="mono">${gpuUtil.toFixed(0)}% (${d.gpuAssigned}/${d.gpuTotal})</span></div>`;
            h += `</div>`;

            /* Incidents */
            h += `<div class="cluster-incidents"><div class="cluster-section-title">Incidents</div>`;
            if (clIncs.length) {
                h += `<div class="cluster-inc-stats"><span class="danger">${activeIncs.length} active</span> · <span class="ok">${clIncs.length - activeIncs.length} resolved</span> · ${clIncs.length} total</div>`;
                clIncs.slice(0, 3).forEach(i => {
                    const sevC = { critical: '#ef4444', high: '#f97316', medium: '#f59e0b', low: '#3b82f6' };
                    h += `<div class="cluster-inc-item"><span class="inc-sev-dot" style="background:${sevC[i.severity] || '#888'}"></span><span class="cluster-inc-title">${i.title}</span><span class="pill" style="background:${sevC[i.severity] || '#888'};color:#fff;font-size:.6rem">${i.severity}</span></div>`;
                });
            } else {
                h += `<div class="cluster-inc-stats ok">No incidents</div>`;
            }
            h += `</div>`;

            h += `</div>`; /* end cluster-card */
        });
        h += '</div>';
        const el = $('#clusters-body'); if (el) el.innerHTML = h;

        /* Animate health rings */
        setTimeout(() => {
            Object.entries(clusters).forEach(([env, d]) => {
                const total = d.nodes.length;
                const uptime = total ? (d.healthy / total * 100) : 0;
                const ringId = 'cl-ring-' + env.replace(/\s+/g, '-').toLowerCase();
                const el2 = $('#' + ringId); if (el2) animRing(el2, uptime, uptime >= 80 ? '#22c55e' : '#f59e0b');
            });
        }, 60);
    }
    window._showNodeDiagram = async function (id) {
        const n = N.find(x => x.id === id); if (!n) return;
        const bom = await g(API + '/nodes/' + id + '/bom');
        const hp = n.health_score, hc = hp >= .8 ? '#22c55e' : hp >= .5 ? '#f59e0b' : '#ef4444';
        const comps = [{ name: 'GPU', icon: '🟢', count: n.gpu_count, model: n.gpu_model, status: 'ok', color: '#22c55e' }, { name: 'CPU', icon: '🔵', count: 2, model: n.cpu_model, status: 'ok', color: '#22c55e' }, { name: 'RAM', icon: '💾', count: 1, model: n.ram_gb + 'GB', status: 'ok', color: '#22c55e' }, { name: 'NIC', icon: '🌐', count: 4, model: 'ConnectX-7', status: 'ok', color: '#22c55e' }, { name: 'NVMe', icon: '💿', count: 4, model: 'NVMe SSD', status: 'ok', color: '#22c55e' }, { name: 'PSU', icon: '⚡', count: 2, model: 'Redundant PSU', status: 'ok', color: '#22c55e' }];
        if (hp < .8) comps[0].status = 'degraded'; if (hp < .8) comps[0].color = '#f59e0b';
        if (n.cordon?.active) { const r = (n.cordon.reason || '').toLowerCase(); if (r.includes('gpu')) { comps[0].status = 'failed'; comps[0].color = '#ef4444' } if (r.includes('nic') || r.includes('link')) { comps[3].status = 'failed'; comps[3].color = '#ef4444' } if (r.includes('nvme')) { comps[4].status = 'failed'; comps[4].color = '#ef4444' } if (r.includes('psu') || r.includes('power')) { comps[5].status = 'failed'; comps[5].color = '#ef4444' } }
        $('#nd-header').innerHTML = `<div class="nd-title"><span class="mono accent">${n.id}</span><span class="pill s-${n.state}">${n.state.replace(/_/g, ' ')}</span></div><div class="nd-meta"><span>${n.sku}</span><span>${n.environment}</span><span>Rack: ${n.rack} U${n.position}</span><span>Health: <b style="color:${hc}">${(hp * 100).toFixed(0)}%</b></span></div>`;
        $('#nd-body').innerHTML = `<div class="nd-schematic"><div class="nd-chassis"><div class="nd-chassis-label">DGX Node — ${n.sku}</div><div class="nd-comp-grid">${comps.map(c => `<div class="nd-comp ${c.status}" style="--comp-color:${c.color}"><div class="nd-comp-icon">${c.icon}</div><div class="nd-comp-name">${c.name}</div><div class="nd-comp-detail">${c.count}× ${c.model}</div><div class="nd-comp-status"><span class="nd-status-dot" style="background:${c.color}"></span>${c.status.toUpperCase()}</div></div>`).join('')}</div></div></div><div class="nd-bom-summary"><h4>Component BOM</h4><table class="dt"><thead><tr><th>Category</th><th>Part</th><th>Qty</th><th>FW</th></tr></thead><tbody>${bom.components.slice(0, 8).map(c => `<tr><td class="accent uc">${c.category}</td><td>${c.part_name}</td><td>${c.quantity}</td><td class="mono ${c.firmware_version ? 'ok' : 'dim'}">${c.firmware_version || '—'}</td></tr>`).join('')}</tbody></table></div>`;
        $('#node-diagram-overlay').classList.add('open');
    };
    async function loadFirmware() {
        const fw = await g(API + '/firmware/compliance'); const fields = ['gpu_driver', 'cuda', 'bios', 'bmc', 'ofed', 'gpu_vbios', 'nvswitch_fw', 'cx_fw', 'transceiver_fw', 'nvme_fw', 'psu_fw', 'hgx_fw', 'bf_fw'];
        const baseline = {}; fw.forEach(n => { if (!baseline[n.sku]) baseline[n.sku] = {}; fields.forEach(f => { if (n[f]) { if (!baseline[n.sku][f]) baseline[n.sku][f] = {}; baseline[n.sku][f][n[f]] = (baseline[n.sku][f][n[f]] || 0) + 1 } }) });
        const golden = {}; Object.entries(baseline).forEach(([sku, flds]) => { golden[sku] = {}; Object.entries(flds).forEach(([f, vers]) => { golden[sku][f] = Object.entries(vers).sort((a, b) => b[1] - a[1])[0][0] }) });
        const fwSkus = [...new Set(fw.map(n => n.sku))].sort();
        $('#fw-filters').innerHTML = `<select id="fwf-sku" class="f-input"><option value="">All SKUs</option>${fwSkus.map(s => `<option>${s}</option>`).join('')}</select><select id="fwf-drift" class="f-input"><option value="">All</option><option value="drift">Drift Only</option><option value="compliant">Compliant</option></select><input id="fwf-q" class="f-input" placeholder="Search..." style="width:180px">`;
        function renderFW() {
            const sf = $('#fwf-sku')?.value, df = $('#fwf-drift')?.value, qf = $('#fwf-q')?.value?.toLowerCase(); let filtered = [...fw]; if (sf) filtered = filtered.filter(n => n.sku === sf); if (qf) filtered = filtered.filter(n => n.node_id.toLowerCase().includes(qf)); let dc = 0, cn = 0; filtered.forEach(n => { let hd = false; fields.forEach(f => { const v = n[f], gv = golden[n.sku]?.[f] || ''; if (v && gv && v !== gv) { dc++; hd = true } }); if (!hd) cn++; n._hd = hd }); if (df === 'drift') filtered = filtered.filter(n => n._hd); else if (df === 'compliant') filtered = filtered.filter(n => !n._hd);
            $('#fw-kpis').innerHTML = `<div class="fleet-kpi-row"><span class="fk">Nodes: <b>${fw.length}</b></span><span class="fk ok">Compliant: <b>${cn}</b></span><span class="fk ${dc ? 'danger' : ''}">Drifts: <b>${dc}</b></span><span class="fk ${cn / fw.length * 100 >= 90 ? 'ok' : 'warn'}">Rate: <b>${(cn / fw.length * 100).toFixed(0)}%</b></span></div>`;
            $('#fw-body').innerHTML = `<div class="table-wrap" style="max-height:520px;overflow:auto"><table class="dt"><thead><tr><th>Node</th><th>SKU</th>${fields.map(f => `<th class="fw-th">${f.replace(/_/g, ' ')}</th>`).join('')}</tr></thead><tbody>${filtered.map(n => `<tr><td class="mono accent">${n.node_id}</td><td>${n.sku}</td>${fields.map(f => { const v = n[f], gv = golden[n.sku]?.[f] || '', dr = v && gv && v !== gv; return `<td class="mono ${dr ? 'fw-drift-cell' : ''}${!v ? ' dim' : ''}" title="${dr ? 'Baseline: ' + gv : ''}">${v || '—'}</td>` }).join('')}</tr>`).join('')}</tbody></table></div>`
        }
        renderFW(); $$('#fw-filters select, #fw-filters input').forEach(el => { el.onchange = renderFW; if (el.tagName === 'INPUT') el.oninput = renderFW });
        $('#fw-export').onclick = () => { let csv = 'Node,SKU,' + fields.join(',') + '\n'; fw.forEach(n => csv += `${n.node_id},${n.sku},${fields.map(f => n[f] || '').join(',')}\n`); const b = new Blob([csv], { type: 'text/csv' }); const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = 'cic_firmware.csv'; a.click(); toast('Exported', 'success') }
    }
    /* ═══════════════ BAR CHART ═══════════════ */
    function drawBarChart(el, legendEl, datasets, labels) {
        el.innerHTML = ''; const c = document.createElement('canvas'); const W = el.offsetWidth || 500, H = el.offsetHeight || 160; c.width = W; c.height = H; el.appendChild(c); const ctx = c.getContext('2d'); const p = { t: 12, r: 12, b: 28, l: 48 }, cw = W - p.l - p.r, ch = H - p.t - p.b;
        ctx.fillStyle = 'rgba(10,15,30,.4)'; ctx.fillRect(0, 0, W, H);
        const allV = datasets.flatMap(d => d.data); const mn = 0, mx = Math.max(...allV, 1), rng = mx - mn || 1;
        ctx.strokeStyle = 'rgba(59,130,246,.06)'; ctx.lineWidth = 1;
        for (let i = 0; i <= 4; i++) { const y = p.t + ch * (i / 4); ctx.beginPath(); ctx.moveTo(p.l, y); ctx.lineTo(W - p.r, y); ctx.stroke(); ctx.fillStyle = 'rgba(148,163,184,.5)'; ctx.font = '11px Inter'; ctx.textAlign = 'right'; ctx.fillText((mx - rng * i / 4).toFixed(0), p.l - 6, y + 4) }
        const n = labels.length, grpW = cw / n, barW = Math.max(4, (grpW - 4) / datasets.length - 2), step = Math.max(1, Math.ceil(n / 10));
        ctx.textAlign = 'center'; ctx.fillStyle = 'rgba(148,163,184,.5)'; ctx.font = '11px Inter';
        labels.forEach((l, i) => { if (i % step === 0) ctx.fillText(l, p.l + grpW * i + grpW / 2, H - 6) });
        datasets.forEach((ds, di) => {
            ds.data.forEach((v, i) => {
                const x = p.l + grpW * i + 2 + di * (barW + 2), bh = ch * ((v - mn) / rng), y = p.t + ch - bh;
                ctx.fillStyle = ds.color; const rd = Math.min(3, barW / 2);
                ctx.beginPath(); ctx.moveTo(x, y + rd); ctx.arcTo(x, y, x + barW, y, rd); ctx.arcTo(x + barW, y, x + barW, y + bh, rd); ctx.lineTo(x + barW, p.t + ch); ctx.lineTo(x, p.t + ch); ctx.closePath(); ctx.fill();
            });
        });
        if (legendEl) legendEl.innerHTML = datasets.map(ds => `<span class="lg-item"><span class="lg-dot" style="background:${ds.color}"></span>${ds.label}</span>`).join('');
    }

    let incRange = '7d', incSevFilter = '', incStatusFilter = '';
    async function loadIncidents() {
        wireSubTabs('#inc-sub-tabs', { 'inc-overview': loadIncOverview, 'inc-patterns': loadIncPatterns, 'inc-components': loadIncComponents });
        loadIncOverview();
    }
    async function loadIncOverview() {
        const incs = await g(API + '/incidents'); const sevC = { critical: '#ef4444', high: '#f97316', medium: '#f59e0b', low: '#3b82f6' }, stC = { mitigated: '#f59e0b', resolved: '#22c55e', investigating: '#ef4444' };
        /* Filters */
        $('#inc-filters').innerHTML = `<select id="if-sev" class="f-input"><option value="">All Severities</option><option value="critical">Critical</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select><select id="if-status" class="f-input"><option value="">All Status</option><option value="new">New</option><option value="mitigated">Mitigated</option><option value="resolved">Resolved</option><option value="investigating">Investigating</option></select><div class="time-range-bar" id="inc-time-range"><button class="tr-btn${incRange === '7d' ? ' active' : ''}" data-range="7d">7d</button><button class="tr-btn${incRange === '30d' ? ' active' : ''}" data-range="30d">30d</button><button class="tr-btn${incRange === '90d' ? ' active' : ''}" data-range="90d">90d</button><button class="tr-btn${incRange === '6mo' ? ' active' : ''}" data-range="6mo">6mo</button><button class="tr-btn${incRange === '1yr' ? ' active' : ''}" data-range="1yr">1yr</button></div>`;
        $$('#inc-time-range .tr-btn').forEach(b => { b.onclick = () => { incRange = b.dataset.range; loadIncOverview() } });
        $('#if-sev').value = incSevFilter; $('#if-status').value = incStatusFilter;
        $('#if-sev').onchange = () => { incSevFilter = $('#if-sev').value; renderIncs() };
        $('#if-status').onchange = () => { incStatusFilter = $('#if-status').value; renderIncs() };
        function renderIncs() {
            let fi = [...incs]; const sf = $('#if-sev')?.value, stf = $('#if-status')?.value;
            if (sf) fi = fi.filter(i => i.severity === sf);
            if (stf === 'new') fi = fi.filter(i => !i.mitigated_at && !i.resolved_at);
            else if (stf === 'mitigated') fi = fi.filter(i => i.mitigated_at && !i.resolved_at);
            else if (stf === 'resolved') fi = fi.filter(i => i.resolved_at);
            else if (stf === 'investigating') fi = fi.filter(i => i.status === 'investigating');
            const act = fi.filter(i => !i.resolved_at).length, res = fi.filter(i => i.resolved_at).length, mit = fi.filter(i => i.mitigated_at && !i.resolved_at).length;
            const mt = fi.filter(i => i.resolved_at && i.started_at).map(i => new Date(i.resolved_at) - new Date(i.started_at)); const avgM = mt.length ? (mt.reduce((a, b) => a + b, 0) / mt.length / 3600000).toFixed(1) : '-';
            $('#inc-stats').innerHTML = `<div class="inc-stat-row"><div class="inc-stat"><span class="inc-stat-v danger">${act}</span><span class="inc-stat-l">New / Active</span></div><div class="inc-stat"><span class="inc-stat-v warn">${mit}</span><span class="inc-stat-l">Mitigated</span></div><div class="inc-stat"><span class="inc-stat-v ok">${res}</span><span class="inc-stat-l">Resolved</span></div><div class="inc-stat"><span class="inc-stat-v">${fi.length}</span><span class="inc-stat-l">Total</span></div><div class="inc-stat"><span class="inc-stat-v">${avgM}h</span><span class="inc-stat-l">Avg MTTR</span></div></div>`;
            const lbl = rangeLabels(incRange);
            setTimeout(() => {
                drawBarChart($('#inc-chart-vol'), $('#inc-legend-vol'), [{ label: 'New', data: mockRange(2, 1.5, incRange).map(v => Math.max(0, Math.round(v))), color: 'rgb(239,68,68)' }, { label: 'Mitigated', data: mockRange(1, 0.8, incRange).map(v => Math.max(0, Math.round(v))), color: 'rgb(245,158,11)' }, { label: 'Resolved', data: mockRange(1.5, 1, incRange).map(v => Math.max(0, Math.round(v))), color: 'rgb(34,197,94)' }], lbl);
                drawBarChart($('#inc-chart-mttr'), $('#inc-legend-mttr'), [{ label: 'MTTR (h)', data: mockRange(parseFloat(avgM) || 4, 2, incRange).map(v => Math.max(.5, v)), color: 'rgb(245,158,11)' }], lbl);
            }, 50);
            $('#inc-body').innerHTML = fi.map(i => `<div class="inc-card"><div class="inc-header"><div class="inc-sev" style="background:${sevC[i.severity] || '#555'}">${i.severity.toUpperCase()}</div><div><div class="inc-id-row"><span class="inc-id">${i.id}</span><span class="inc-status" style="color:${stC[i.status] || '#888'}">${i.status.toUpperCase()}</span></div><div class="inc-title">${i.title}</div></div></div><div class="inc-meta"><span>Service: <b>${i.service}</b></span><span>Commander: <b>${i.commander}</b></span></div><div class="inc-summary">${i.summary}</div><div class="inc-nodes">Affected: ${(i.affected_nodes || []).map(n => `<span class="inc-node-tag" onclick="window._showDP('${n}')">${n}</span>`).join(' ')}</div><div class="inc-timeline"><div class="inc-tl-title">Timeline</div>${(i.timeline || []).map(t => `<div class="inc-tl-item"><span class="inc-tl-time">${new Date(t.time).toLocaleString()}</span><span>${t.event}</span></div>`).join('')}</div>${(i.action_items || []).length ? `<div class="inc-actions"><div class="inc-tl-title">Action Items</div>${i.action_items.map(a => `<div class="inc-action"><span class="pill s-${a.status === 'done' ? 'certified_ready' : 'testing'}">${a.status}</span> ${a.task} <span class="dim">(${a.owner})</span></div>`).join('')}</div>` : ''}</div>`).join('')
        }
        renderIncs();
        /* Changes inline */
        const ch = [{ id: 'CR-2024-0147', title: 'GPU Driver 550→555', status: 'approved', reviewer: 'Kim Joon', env: 'KR1A Prod', date: '2024-03-10', risk: 'medium', nodes: 10 }, { id: 'CR-2024-0148', title: 'OFED Upgrade 24.1.1', status: 'in_review', reviewer: 'Park Soo', env: 'KR1B Dev', date: '2024-03-12', risk: 'low', nodes: 5 }, { id: 'CR-2024-0149', title: 'BMC FW Patch 01.02.03', status: 'approved', reviewer: 'Lee Min', env: 'KR1A Prod', date: '2024-03-08', risk: 'high', nodes: 20 }]; const rC = { high: '#ef4444', medium: '#f59e0b', low: '#3b82f6' }, sC = { approved: '#22c55e', in_review: '#f59e0b', pending: '#94a3b8' };
        $('#inc-changes').innerHTML = `<table class="dt"><thead><tr><th>CR</th><th>Change</th><th>Status</th><th>Reviewer</th><th>Env</th><th>Risk</th><th>Nodes</th><th>Date</th></tr></thead><tbody>${ch.map(c => `<tr><td class="mono accent">${c.id}</td><td>${c.title}</td><td><span class="pill" style="background:${sC[c.status] || '#555'};color:#fff">${c.status.replace(/_/g, ' ')}</span></td><td>${c.reviewer}</td><td>${c.env}</td><td style="color:${rC[c.risk]}">${c.risk.toUpperCase()}</td><td>${c.nodes}</td><td class="mono dim">${c.date}</td></tr>`).join('')}</tbody></table>`;
        /* Audit inline */
        const logs = [{ time: '2024-03-13 21:30', user: 'admin', action: 'Login', detail: 'Basic Auth', ip: '10.0.1.50' }, { time: '2024-03-13 21:15', user: 'sre-oncall', action: 'Node Cordon', detail: 'gpu-h200-007 P0 GPU XID 94', ip: '10.0.1.51' }, { time: '2024-03-13 20:45', user: 'admin', action: 'FW Export', detail: 'Firmware CSV export', ip: '10.0.1.50' }, { time: '2024-03-13 20:30', user: 'platform-eng', action: 'Login', detail: 'Basic Auth', ip: '10.0.1.52' }, { time: '2024-03-13 19:00', user: 'sre-oncall', action: 'Incident', detail: 'INC-2024-003 created', ip: '10.0.1.51' }];
        $('#inc-audit').innerHTML = `<table class="dt"><thead><tr><th>Time</th><th>User</th><th>Action</th><th>Detail</th><th>IP</th></tr></thead><tbody>${logs.map(l => `<tr><td class="mono dim">${l.time}</td><td class="accent bold">${l.user}</td><td><span class="pill s-testing">${l.action}</span></td><td>${l.detail}</td><td class="mono dim">${l.ip}</td></tr>`).join('')}</tbody></table>`
    }
    async function loadIncPatterns() { const incs = await g(API + '/incidents'); const byRack = {}, byComp = {}; incs.forEach(i => { (i.affected_nodes || []).forEach(nid => { const n = N.find(x => x.id === nid); if (n) { byRack[n.rack || '?'] = (byRack[n.rack || '?'] || 0) + 1 } }); (i.labels || []).forEach(l => { byComp[l] = (byComp[l] || 0) + 1 }) }); $('#inc-patterns').innerHTML = `<div class="pattern-grid"><div class="card"><div class="card-head"><span class="card-title">By Rack</span></div><div class="card-body"><div class="state-bars">${Object.entries(byRack).sort((a, b) => b[1] - a[1]).map(([r, c]) => `<div class="state-bar-row"><span class="state-bar-label">${r}</span><div class="hbar"><div class="hbar-bg"><div class="hbar-fill" style="width:${c / Math.max(...Object.values(byRack)) * 100}%;background:#ef4444"></div></div>${c}</div></div>`).join('')}</div></div></div><div class="card"><div class="card-head"><span class="card-title">By Component</span></div><div class="card-body"><div class="state-bars">${Object.entries(byComp).sort((a, b) => b[1] - a[1]).map(([l, c]) => `<div class="state-bar-row"><span class="state-bar-label">${l}</span><div class="hbar"><div class="hbar-bg"><div class="hbar-fill" style="width:${c / Math.max(...Object.values(byComp)) * 100}%;background:#f97316"></div></div>${c}</div></div>`).join('')}</div></div></div></div>` }
    async function loadIncComponents() {
        const comps = { GPU: { total: 0, failed: 0, degraded: 0, color: '#ef4444' }, CPU: { total: 0, failed: 0, degraded: 0, color: '#3b82f6' }, NIC: { total: 0, failed: 0, degraded: 0, color: '#8b5cf6' }, NVMe: { total: 0, failed: 0, degraded: 0, color: '#f97316' }, PSU: { total: 0, failed: 0, degraded: 0, color: '#f59e0b' }, RAM: { total: 0, failed: 0, degraded: 0, color: '#06b6d4' } };
        N.forEach(n => { comps.GPU.total += n.gpu_count || 0; comps.CPU.total += 2; comps.NIC.total += 4; comps.NVMe.total += 4; comps.PSU.total += 2; comps.RAM.total += 1; if (n.health_score < .5) { comps.GPU.failed++; } else if (n.health_score < .8) { comps.GPU.degraded++ } if (n.cordon?.active) { const r = (n.cordon.reason || '').toLowerCase(); if (r.includes('gpu') || r.includes('xid')) comps.GPU.failed++; if (r.includes('nic') || r.includes('link') || r.includes('ib')) comps.NIC.failed++; if (r.includes('nvme') || r.includes('ssd')) comps.NVMe.failed++; if (r.includes('psu') || r.includes('power')) comps.PSU.failed++ } });
        $('#inc-components').innerHTML = `<div class="section-header"><h2>Component-Level Health</h2><span class="dim">Fleet-wide component failure analysis</span></div><div class="comp-grid">${Object.entries(comps).map(([name, d]) => { const okP = d.total ? ((d.total - d.failed - d.degraded) / d.total * 100) : 100; return `<div class="comp-card"><div class="comp-header"><span class="comp-icon" style="color:${d.color}">${{ GPU: '🟢', CPU: '🔵', NIC: '🌐', NVMe: '💿', PSU: '⚡', RAM: '💾' }[name]}</span><span class="comp-name">${name}</span></div><div class="comp-stats"><div class="comp-stat"><span class="comp-sv">${d.total}</span><span class="comp-sl">Total</span></div><div class="comp-stat"><span class="comp-sv ok">${d.total - d.failed - d.degraded}</span><span class="comp-sl">Healthy</span></div><div class="comp-stat"><span class="comp-sv warn">${d.degraded}</span><span class="comp-sl">Degraded</span></div><div class="comp-stat"><span class="comp-sv danger">${d.failed}</span><span class="comp-sl">Failed</span></div></div><div class="hbar" style="margin-top:8px"><div class="hbar-bg"><div class="hbar-fill" style="width:${okP}%;background:${okP >= 95 ? '#22c55e' : okP >= 80 ? '#f59e0b' : '#ef4444'}"></div></div>${okP.toFixed(0)}%</div></div>` }).join('')}</div><div class="section-header" style="margin-top:24px"><h2>Component Incident Correlation</h2></div><div class="chart-card" style="margin-top:12px"><div class="chart-title">Failures by Component Type</div><div class="chart-container" id="comp-chart-fail"></div><div class="chart-legend" id="comp-legend-fail"></div></div>`;
        setTimeout(() => { drawBarChart($('#comp-chart-fail'), $('#comp-legend-fail'), Object.entries(comps).map(([name, d]) => ({ label: name, data: mockRange(d.failed + d.degraded, 1, '7d').map(v => Math.max(0, Math.round(v))), color: d.color })), rangeLabels('7d')) }, 80)
    }
    function loadDashboards() { $$('.dash-tab').forEach(t => { t.classList.toggle('active', t.dataset.dash === dashTab); t.onclick = () => { dashTab = t.dataset.dash; $$('.dash-tab').forEach(x => x.classList.toggle('active', x.dataset.dash === dashTab)); renderDash() } }); renderDash() }
    function renderDash() { const b = $('#dash-body'); if (dashTab === 'fleet-health') { const sc = {}; N.forEach(n => { sc[n.state] = (sc[n.state] || 0) + 1 }); const ah = (N.reduce((a, n) => a + n.health_score, 0) / N.length) * 100; b.innerHTML = `<div class="dash-grid"><div class="dash-card"><div class="dash-card-title">Health Dist</div><div class="chart-container" id="dc-h"></div><div class="chart-legend" id="dcl-h"></div></div><div class="dash-card"><div class="dash-card-title">State Dist</div><div class="state-bars">${Object.entries(sc).sort((a, b) => b[1] - a[1]).map(([s, c]) => `<div class="state-bar-row"><span class="state-bar-label">${s.replace(/_/g, ' ')}</span><div class="hbar"><div class="hbar-bg"><div class="hbar-fill" style="width:${c / N.length * 100}%;background:${SC[s] || '#555'}"></div></div>${c}</div></div>`).join('')}</div></div></div>`; setTimeout(() => drawChart($('#dc-h'), $('#dcl-h'), [{ label: 'Healthy', data: mockRange(N.filter(n => n.health_score >= .8).length, 2, '7d'), color: 'rgb(34,197,94)' }, { label: 'Degraded', data: mockRange(N.filter(n => n.health_score < .8).length, 2, '7d'), color: 'rgb(239,68,68)' }], rangeLabels('7d')), 50) } else if (dashTab === 'gpu-util') { const gT = N.filter(n => n.type === 'gpu').reduce((a, n) => a + n.gpu_count, 0), gA = N.filter(n => n.type === 'gpu' && n.state === 'customer_assigned').reduce((a, n) => a + n.gpu_count, 0), u = gT ? (gA / gT * 100) : 0; b.innerHTML = `<div class="dash-grid"><div class="dash-card"><div class="dash-card-title">GPU</div>${mkRing('du1', u, 'Assigned', u >= 70 ? '#22c55e' : '#f59e0b', 140)}</div><div class="dash-card"><div class="dash-card-title">Trend</div><div class="chart-container" id="dc-gu"></div><div class="chart-legend" id="dcl-gu"></div></div></div>`; setTimeout(() => { animRing($('#du1'), u, u >= 70 ? '#22c55e' : '#f59e0b'); drawChart($('#dc-gu'), $('#dcl-gu'), [{ label: 'GPU %', data: mockRange(u, 8, '7d'), color: 'rgb(6,182,212)' }], rangeLabels('7d')) }, 50) } else if (dashTab === 'power') { const pw = N.reduce((a, n) => a + (n.power_draw_kw || 0), 0); b.innerHTML = `<div class="dash-grid"><div class="dash-card"><div class="dash-card-title">Power</div>${mkRing('dp1', pw / 600 * 100, pw.toFixed(0) + ' kW', '#8b5cf6', 140)}</div><div class="dash-card"><div class="dash-card-title">Trend</div><div class="chart-container" id="dc-pt"></div><div class="chart-legend" id="dcl-pt"></div></div></div>`; setTimeout(() => { animRing($('#dp1'), pw / 600 * 100, '#8b5cf6'); drawChart($('#dc-pt'), $('#dcl-pt'), [{ label: 'kW', data: mockRange(pw, 25, '7d'), color: 'rgb(139,92,246)' }], rangeLabels('7d')) }, 50) } else if (dashTab === 'incidents-dash') { b.innerHTML = `<div class="dash-grid"><div class="dash-card"><div class="dash-card-title">Volume</div><div class="chart-container" id="dc-iv"></div><div class="chart-legend" id="dcl-iv"></div></div><div class="dash-card"><div class="dash-card-title">MTTR</div><div class="chart-container" id="dc-mt"></div><div class="chart-legend" id="dcl-mt"></div></div></div>`; setTimeout(() => { drawChart($('#dc-iv'), $('#dcl-iv'), [{ label: 'New', data: mockRange(2, 1.5, '7d').map(v => Math.max(0, Math.round(v))), color: 'rgb(239,68,68)' }, { label: 'Resolved', data: mockRange(1.5, 1, '7d').map(v => Math.max(0, Math.round(v))), color: 'rgb(34,197,94)' }], rangeLabels('7d')); drawChart($('#dc-mt'), $('#dcl-mt'), [{ label: 'MTTR (h)', data: mockRange(4, 2, '7d').map(v => Math.max(.5, v)), color: 'rgb(245,158,11)' }], rangeLabels('7d')) }, 50) } else if (dashTab === 'ext-grafana') { const url = localStorage.getItem('grafana_url') || ''; b.innerHTML = `<div class="dash-card"><div class="dash-card-title">External Grafana</div><div style="display:flex;gap:8px;margin-bottom:12px"><input id="g-url" class="f-input" style="flex:1" placeholder="http://grafana:3000/d/..." value="${url}"><button class="action-btn" onclick="localStorage.setItem('grafana_url',document.getElementById('g-url').value);renderDash()">Connect</button></div>${url ? `<iframe src="${url}&kiosk=tv" class="grafana-iframe" allowfullscreen></iframe>` : '<div class="empty-state" style="height:200px">Enter Grafana URL</div>'}</div>` } }
    function loadHelp() { const personas = [{ icon: 'E', name: 'Executive', desc: 'SLA compliance, fleet KPIs, reporting', color: '#f59e0b', flows: [{ s: 'View Global fleet KPIs & SLAs', l: 'global' }, { s: 'Check SLA by environment', l: 'capacity' }, { s: 'Review incident MTTR trends', l: 'incidents' }, { s: 'Power & utilization overview', l: 'global' }] }, { icon: 'O', name: 'Operator', desc: 'Daily monitoring, health checks', color: '#3b82f6', flows: [{ s: 'Check Global View KPIs', l: 'global' }, { s: 'Review degraded nodes', l: 'health' }, { s: 'Check firmware drift', l: 'health' }, { s: 'Monitor incidents', l: 'incidents' }] }, { icon: 'C', name: 'Capacity Planner', desc: 'Utilization, allocation, forecasting', color: '#8b5cf6', flows: [{ s: 'View Capacity Overview', l: 'capacity' }, { s: 'Compare by environment/SKU/AZ', l: 'capacity' }, { s: 'Export fleet data', l: 'capacity' }, { s: 'Check power trends', l: 'capacity' }] }, { icon: 'S', name: 'SRE / On-Call', desc: 'Incident response, root cause analysis', color: '#ef4444', flows: [{ s: 'Check active incidents', l: 'incidents' }, { s: 'Review pattern analysis', l: 'incidents' }, { s: 'View node diagram', l: 'health' }, { s: 'Review changes & audit log', l: 'incidents' }] }, { icon: 'T', name: 'Tenant-Facing Teams', desc: 'Node assignment, drain scheduling', color: '#06b6d4', flows: [{ s: 'Check available nodes', l: 'health' }, { s: 'View node assignment status', l: 'capacity' }, { s: 'Review drain queue', l: 'capacity' }, { s: 'Pick new node for tenant', l: 'capacity' }] }, { icon: 'A', name: 'Platform Admin', desc: 'BOM, firmware, lifecycle management', color: '#22c55e', flows: [{ s: 'Audit BOM', l: 'capacity' }, { s: 'Check firmware compliance', l: 'health' }, { s: 'Review SLAs', l: 'capacity' }, { s: 'Check dashboards', l: 'health' }] }]; $('#help-body').innerHTML = `<div class="persona-grid">${personas.map(p => `<div class="persona-card" style="--pc:${p.color}"><div class="persona-header"><span class="persona-icon-letter" style="background:${p.color}">${p.icon}</span><div><div class="persona-name">${p.name}</div><div class="persona-desc">${p.desc}</div></div></div><div class="persona-flows">${p.flows.map((f, i) => `<div class="persona-step" onclick="switchView('${f.l}');$$('.nav-tab').forEach(x=>x.classList.toggle('active',x.dataset.view==='${f.l}'))"><span class="step-num">${i + 1}</span><span class="step-text">${f.s}</span><span class="step-arrow">></span></div>`).join('')}</div></div>`).join('')}</div><div class="help-extras"><div class="help-section"><h3>Keyboard Shortcuts</h3><div class="help-keys">${[['Cmd+K or /', 'Search'], ['Esc', 'Close panel'], ['G then G', 'Global View'], ['G then C', 'Capacity'], ['G then H', 'Health'], ['G then I', 'Incidents']].map(([k, d]) => `<div class="hk"><kbd>${k}</kbd><span>${d}</span></div>`).join('')}</div></div><div class="help-section"><h3>Integrations</h3><p><b>Prometheus:</b> <code class="accent">/metrics</code></p><p><b>API Docs:</b> <code class="accent">/docs</code></p></div></div>` }
    window._showDP = async function (id) { const n = await g(API + '/nodes/' + id); const bom = await g(API + '/nodes/' + id + '/bom'); $('#dp-title').textContent = n.id; $('#dp-sub').innerHTML = `<span class="pill s-${n.state}">${n.state.replace(/_/g, ' ')}</span> ${n.environment} / ${n.sku}`; let tab = 'overview'; const rt = () => { if (tab === 'overview') { $('#dp-body').innerHTML = [['FQDN', n.fqdn], ['Health', n.health_score.toFixed(2)], ['SKU', n.sku], ['Serial', n.serial], ['GPU', n.gpu_model + ' x' + n.gpu_count], ['CPU', n.cpu_model], ['RAM', n.ram_gb + 'GB'], ['Power', (n.power_draw_kw || 0).toFixed(1) + ' kW'], ['AZ', (n.az || '').toUpperCase()], ['Rack', n.rack + ' U' + n.position], ['Cordon', n.cordon?.active ? n.cordon.owner + ' (' + n.cordon.priority + '): ' + n.cordon.reason : '—']].map(([k, v]) => `<div class="dp-row"><span class="k">${k}</span><span class="v">${v}</span></div>`).join('') } else if (tab === 'bom') { $('#dp-body').innerHTML = `<table class="dt"><thead><tr><th>Part</th><th>Name</th><th>Qty</th><th>FW</th></tr></thead><tbody>${bom.components.map(c => `<tr><td class="accent bold uc">${c.category}</td><td>${c.part_name}</td><td>${c.quantity}</td><td class="mono ${c.firmware_version ? 'ok' : 'dim'}">${c.firmware_version || '—'}</td></tr>`).join('')}</tbody></table>` } else { $('#dp-body').innerHTML = Object.entries(n.firmware).filter(([, v]) => v).map(([k, v]) => `<div class="dp-row"><span class="k">${k}</span><span class="v mono">${v}</span></div>`).join('') } }; rt(); $$('.dp-tab').forEach(t => { t.classList.toggle('active', t.dataset.tab === tab); t.onclick = () => { tab = t.dataset.tab; $$('.dp-tab').forEach(x => x.classList.toggle('active', x.dataset.tab === tab)); rt() } }); $('#detail-panel').classList.add('open') };
    $('#dp-close-btn').onclick = () => { $('#detail-panel').classList.remove('open'); setBreadcrumb(null) };
    async function init() { try { N = await g(API + '/nodes'); loadGlobal(); initParticles(); toast('Connected — ' + N.length + ' nodes', 'success'); addNotif('Loaded ' + N.length + ' nodes', 'info'); const c = N.filter(n => n.cordon?.active); if (c.length) addNotif(c.length + ' nodes cordoned', 'warning') } catch (e) { console.error(e) } }
    setInterval(async () => { if (authH) { try { N = await g(API + '/nodes'); if (cView === 'global') loadGlobal() } catch { } } }, 15000);
    showLogin(); window.switchView = switchView; window.setBreadcrumb = setBreadcrumb;
})();
