'use strict';
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const S = {hist: [], latest: null, lastValid: null, risk: null, base: null, alerts: {}, control: {}, status: {state: 'IDLE'}, metrics: {}, ledger: {},
  notes: [], notifs: [], checkins: {}, cg: [], acting: 'c1', skew: 0, judge: null, cfg: {}, replay: null, muted: false, audio: false, tab: 'live', patient: {}};
const nowS = () => Date.now() / 1000 + S.skew;
const TIER_RANK = {Critical: 3, Warning: 2, Info: 1};
const VD = [{k: 'temp', label: 'Temperature', unit: '°C', dec: 1, color: '#fb923c', sk: 'temp'},
  {k: 'hr', label: 'Heart rate', unit: 'bpm', dec: 0, color: '#f472b6', sk: 'hr'},
  {k: 'sbp', label: 'Blood pressure', unit: 'mmHg', dec: 0, color: '#60a5fa', sk: 'sbp'},
  {k: 'spo2', label: 'SpO₂', unit: '%', dec: 0, color: '#34d399', sk: 'spo2'}];

async function api(path, method = 'POST', body) {
  try { const r = await fetch(path, {method, headers: {'Content-Type': 'application/json'}, body: body ? JSON.stringify(body) : undefined}); return await r.json(); }
  catch (e) { return null; }
}

/* ---------------------------------------------------------------- state ingestion */
function applyState(st) {
  S.patient = st.patient; S.cg = st.caregivers; S.control = st.control; S.status = st.status; S.skew = st.status.server_now - Date.now() / 1000;
  S.hist = st.history.map(h => ({...h, valid: !!h.valid})); S.metrics = st.metrics; S.ledger = st.ledger; S.notes = st.notes; S.checkins = st.checkins || {};
  S.cfg = st.config; S.judge = st.judge; S.alerts = {}; st.alerts.forEach(a => S.alerts[a.id] = a);
  S.latest = st.latest; S.lastValid = st.latest && st.latest.valid ? st.latest : null;
  S.risk = st.risk || null;
  S.base = st.latest ? st.latest.baseline : null;
  if (!$('#acting').options.length) {
    $('#acting').innerHTML = S.cg.map(c => `<option value="${c.id}">${esc(c.name)} — ${esc(c.role)}</option>`).join('');
    $('#acting').value = S.acting;
  }
}
function onMsg(m) {
  switch (m.type) {
    case 'hello': applyState(m.state); break;
    case 'reading': {
      const r = m.reading;
      S.hist.push({ts: r.ts, temp: r.temp, hr: r.hr, sbp: r.sbp, dbp: r.dbp, spo2: r.spo2, valid: m.valid, news2: m.news2 ? m.news2.total : null,
        risk_prob: m.risk ? m.risk.prob : null, risk_band: m.risk ? m.risk.band : null});
      if (S.hist.length > 160) S.hist.shift();
      S.latest = m; if (m.valid) S.lastValid = m; if (m.risk) S.risk = m.risk; if (m.baseline) S.base = m.baseline; S.ledger = m.ledger; break;
    }
    case 'alert': S.alerts[m.alert.id] = m.alert; break;
    case 'notification': S.notifs.unshift(m); S.notifs = S.notifs.slice(0, 40); toast(m); break;
    case 'status': S.status = m.status; S.metrics = m.metrics; S.ledger = m.ledger; S.checkins = m.checkins; S.skew = m.status.server_now - Date.now() / 1000; break;
    case 'control': S.control = m.control; break;
    case 'replay': S.replay = m; break;
    case 'note': S.notes.unshift(m.note); S.notes = S.notes.slice(0, 8); break;
    case 'checkin': S.checkins = m.checkins; break;
    case 'judge': S.judge = m; break;
    case 'reset': fetch('/api/state').then(r => r.json()).then(applyState).then(() => { S.notifs = []; S.risk = null; render(); }); return;
  }
  schedule();
}
let pending = false;
function schedule() { if (!pending) { pending = true; requestAnimationFrame(() => { pending = false; render(); }); } }

function connect() {
  const ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws');
  ws.onopen = () => $('#offline').classList.add('hidden');
  ws.onmessage = e => onMsg(JSON.parse(e.data));
  ws.onclose = () => { $('#offline').classList.remove('hidden'); setTimeout(connect, 1500); };
}

/* ---------------------------------------------------------------- charts */
function spark(vals, band, color) {
  const W = 300, H = 64, P = 4, clean = vals.filter(v => v != null);
  if (clean.length < 2) return '';
  let lo = Math.min(...clean, band ? band[0] : Infinity), hi = Math.max(...clean, band ? band[1] : -Infinity);
  const pad = (hi - lo) * 0.15 || 1; lo -= pad; hi += pad;
  const x = i => P + (W - 2 * P) * i / Math.max(1, vals.length - 1), y = v => H - P - (H - 2 * P) * (v - lo) / (hi - lo);
  let d = ''; vals.forEach((v, i) => { if (v != null) d += (d && vals[i - 1] != null ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1); });
  const last = vals.map((v, i) => [v, i]).filter(a => a[0] != null).pop();
  const gaps = vals.map((v, i) => v == null ? `<rect x="${x(i) - 1.5}" y="0" width="3" height="${H}" fill="#f59e0b33"/>` : '').join('');
  const b = band ? `<rect x="0" y="${y(band[1]).toFixed(1)}" width="${W}" height="${Math.max(1, y(band[0]) - y(band[1])).toFixed(1)}" fill="#2dd4bf" opacity=".13"/>
    <line x1="0" x2="${W}" y1="${y((band[0] + band[1]) / 2).toFixed(1)}" y2="${y((band[0] + band[1]) / 2).toFixed(1)}" stroke="#2dd4bf" stroke-width=".6" stroke-dasharray="3 3" opacity=".5"/>` : '';
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${b}${gaps}<path d="${d}" fill="none" stroke="${color}" stroke-width="2" vector-effect="non-scaling-stroke"/>
    <circle cx="${x(last[1]).toFixed(1)}" cy="${y(last[0]).toFixed(1)}" r="3.5" fill="${color}"/></svg>`;
}
const COL = {Low: '#22c55e', Medium: '#f59e0b', High: '#ef4444'};
function gauge(p) {
  const cx = 110, cy = 100, r = 82, pt = a => [cx + r * Math.cos(a), cy - r * Math.sin(a)];
  const arc = (p0, p1, c) => { const a = pt(Math.PI * (1 - p0)), b = pt(Math.PI * (1 - p1)); return `<path d="M${a[0].toFixed(1)} ${a[1].toFixed(1)} A${r} ${r} 0 0 1 ${b[0].toFixed(1)} ${b[1].toFixed(1)}" stroke="${c}" stroke-width="16" fill="none" opacity=".85"/>`; };
  const n = pt(Math.PI * (1 - Math.max(0, Math.min(1, p))));
  return `<svg class="gauge" viewBox="0 0 220 118">${arc(0, .30, '#22c55e')}${arc(.305, .65, '#f59e0b')}${arc(.655, 1, '#ef4444')}
    <line x1="${cx}" y1="${cy}" x2="${(cx + (n[0] - cx) * .92).toFixed(1)}" y2="${(cy + (n[1] - cy) * .92).toFixed(1)}" stroke="#fff" stroke-width="3.5" stroke-linecap="round"/><circle cx="${cx}" cy="${cy}" r="7" fill="#fff"/></svg>`;
}
function trendChart() {
  const h = S.hist.slice(-96); if (h.length < 3) return '<div class="mut">Collecting data…</div>';
  const W = 600, H = 96, n = h.length, x = i => 6 + (W - 12) * i / (n - 1), y = p => H - 8 - (H - 16) * p;
  const bars = h.map((r, i) => r.news2 == null ? '' : `<rect x="${(x(i) - 2).toFixed(1)}" y="${(H - 8 - (H - 16) * Math.min(1, r.news2 / 9)).toFixed(1)}" width="4" height="${((H - 16) * Math.min(1, r.news2 / 9)).toFixed(1)}" fill="#64748b" opacity=".55"/>`).join('');
  let d = ''; h.forEach((r, i) => { if (r.risk_prob != null) d += (d ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(r.risk_prob).toFixed(1); });
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><line x1="0" x2="${W}" y1="${y(.30)}" y2="${y(.30)}" stroke="#f59e0b" stroke-dasharray="4 4" opacity=".6"/>
    <line x1="0" x2="${W}" y1="${y(.65)}" y2="${y(.65)}" stroke="#ef4444" stroke-dasharray="4 4" opacity=".6"/>${bars}
    <path d="${d}" fill="none" stroke="#2dd4bf" stroke-width="2.5" vector-effect="non-scaling-stroke"/></svg>`;
}

/* ---------------------------------------------------------------- render */
function fmtSim(ts) { if (!ts) return '—'; const d = new Date(ts); return isNaN(d) ? ts : d.toLocaleString('en-IN', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false}); }
function renderTop() {
  $('#ptName').textContent = S.patient.name || '—'; $('#ptSub').textContent = S.patient.name ? `${S.patient.age} y · synthetic patient · bedside-01` : '—';
  const last = S.hist[S.hist.length - 1]; $('#simClock').textContent = last ? fmtSim(last.ts) + ' (sim)' : '—';
  const l = S.latest && S.latest.reading; $('#devInfo').textContent = l ? `battery ${Math.round(l.battery)}% · ${l.power === 'mains' ? 'mains power' : 'ON BATTERY'} · signal ${(l.quality * 100) | 0}%` : 'device —';
  const st = S.status || {state: 'IDLE'}; let t = {LIVE: 'LIVE', IDLE: 'Waiting for device…', SENSOR_FAULT: 'SENSOR FAULT — readings excluded'}[st.state];
  if (st.state === 'NO_DATA') t = `NO DATA — UNMONITORED (${Math.round(nowS() - (st.server_now - (st.age || 0)))}s)`;
  if (st.state === 'REPLAYING') t = `REPLAYING ${S.replay ? S.replay.count : ''} BUFFERED READINGS`;
  const p = $('#statusPill'); p.className = 'pill ' + st.state; $('#statusTxt').textContent = t;
  const jb = $('#judgebar'), j = S.judge;
  if (j && (j.running || j.step === 9)) { jb.classList.remove('hidden'); $('#judgeCap').textContent = (j.running ? `Step ${j.step}/${j.total} · ` : '') + j.caption;
    $('#judgeSteps').innerHTML = Array.from({length: j.total}, (_, i) => `<i class="${i < j.step ? 'd' : ''}"></i>`).join(''); } else jb.classList.add('hidden');
}
function renderVitals() {
  const lv = [...S.hist].reverse().find(h => h.valid), subs = S.lastValid && S.lastValid.news2 ? S.lastValid.news2.subs : {};
  const st = S.status.state, stale = st === 'NO_DATA', sig = S.latest && !S.latest.valid, age = S.status.age;
  let html = VD.map(v => {
    const val = lv ? lv[v.k] : null, b = S.base && S.base[v.k], sc = subs[v.sk] || 0;
    const band = b ? [b.median - 2 * b.sd, b.median + 2 * b.sd] : null, vals = S.hist.slice(-96).map(h => h.valid ? h[v.k] : null);
    const d = val != null && b ? val - b.median : null, dtxt = d == null ? 'learning baseline…' : `${d >= 0 ? '+' : ''}${d.toFixed(v.dec ? 1 : 0)} ${v.unit} vs own baseline (${b.median.toFixed(v.dec ? 1 : 0)})`;
    const main = v.k === 'sbp' ? (lv ? `${Math.round(lv.sbp)}<small>/${Math.round(lv.dbp)} mmHg</small>` : '—') : (val != null ? `${val.toFixed(v.dec)}<small>${v.unit}</small>` : '—');
    const tag = stale ? `<span class="tag bad">LAST KNOWN${age ? ' · ' + Math.round(nowS() - (S.status.server_now - age)) + 's' : ''}</span>` : (sig ? '<span class="tag amb">SIGNAL LOST</span>' : '');
    return `<div class="card vital s${sc} ${stale ? 'stale' : ''}"><h3><span>${v.label}</span>${sc ? `<span class="chip s${sc}">score +${sc}</span>` : ''}</h3>${tag}<div class="val">${main}</div><div class="dl">${dtxt}</div>${spark(vals, band, v.color)}</div>`;
  }).join('');
  const n2 = S.lastValid && S.lastValid.news2 ? S.lastValid.news2.total : null;
  html += `<div class="card vital s${n2 >= 7 ? 3 : n2 >= 5 ? 2 : n2 >= 1 ? 1 : 0}"><h3><span>Early-warning score</span></h3><div class="val">${n2 == null ? '—' : n2}<small>/ 12 (partial)</small></div>
   <div class="dl">NEWS2-style safety floor · illustrative</div><div class="dl" style="margin-top:8px">Any single red value (+3) or total ≥ 7 → <b>Critical</b>, always, regardless of the model.</div></div>`;
  $('#vitals').innerHTML = html;
}
function renderRisk() {
  const r = S.risk;
  if (!r) { $('#risk').innerHTML = '<div class="mut">Learning this patient’s baseline from the first 48 simulated hours…</div>'; $('#riskSub').textContent = ''; $('#trend').innerHTML = trendChart(); return; }
  const mx = Math.max(0.5, ...(r.top || []).map(t => t.contribution));
  const why = (r.top || []).map(t => `<li>${esc(t.text)}<div class="bar" style="width:${Math.max(6, 100 * t.contribution / mx)}%"></div></li>`).join('')
    || '<li class="mut">No concerning pattern vs. this patient’s own baseline.</li>';
  const notes = (r.notes || []).map(n => `<span class="note-chip">📝 caregiver note: ${esc(n)}</span>`).join('');
  $('#risk').innerHTML = `<div class="risk"><div>${gauge(r.prob)}<div class="band ${r.band}">${r.band.toUpperCase()}</div><div class="mut" style="text-align:center">probability ${(r.prob * 100).toFixed(0)}% · experimental</div></div>
   <div class="why"><b>Why?</b> <span class="mut">(top contributing factors)</span><ul>${why}</ul>${notes}${r.nudge ? `<div class="mut" style="font-size:12px;margin-top:6px">Notes add +${r.nudge.toFixed(1)} to the model’s log-odds.</div>` : ''}</div></div>`;
  $('#riskSub').textContent = 'personal baseline + trend model (synthetic-data)'; $('#trend').innerHTML = trendChart();
}
const secs = t => `+${Math.round(t)}s`;
function alertCard(a) {
  const done = a.state === 'RESOLVED' || a.state === 'CLOSED', c0 = a.created, ev = [];
  (a.notified || []).forEach((n, i) => ev.push(`<span class="${i > 0 ? 'x' : ''}">${i > 0 ? '⚠ escalated → ' : '📲 notified '}${esc(n.who)} ${secs(n.wall - c0)}</span>`));
  if (a.acked) ev.push(`<span class="g">✔ ${esc(a.acked_by)} acknowledged ${secs(a.acked - c0)}</span>`);
  if (a.responding) ev.push(`<span class="g">🚶 responding ${secs(a.responding - c0)}</span>`);
  if (a.resolved) ev.push(`<span class="g">✅ resolved by ${esc(a.resolved_by)} ${secs(a.resolved - c0)}</span>`);
  let esc_ = '';
  if (a.state === 'NOTIFIED' && a.deadline) { const T = a.tier === 'Critical' ? S.cfg.ack_timeout_critical : S.cfg.ack_timeout_warning, left = Math.max(0, a.deadline - nowS());
    esc_ = `<div class="esc">⏱ No acknowledgment from ${esc(a.to)} — escalating to <b>${esc(a.next_to)}</b> in ${left.toFixed(0)}s</div><div class="prog"><i style="width:${100 * left / T}%"></i></div>`; }
  else if (a.state === 'NOTIFIED') esc_ = `<div class="esc">⏱ Emergency contact notified — awaiting acknowledgment</div>`;
  const stl = {INFO: 'INFO', NOTIFIED: 'AWAITING ACK', ACKNOWLEDGED: 'ACKNOWLEDGED', RESPONDING: 'RESPONDING', RESOLVED: 'RESOLVED', CLOSED: 'AUTO-CLOSED'}[a.state];
  const who = (S.cg.find(c => c.id === S.acting) || {name: 'Caregiver'}).name, act = a.tier !== 'Info' && !done;
  const btn = (k, label, ok) => `<button class="btn sm" data-a="${k}" data-id="${a.id}" ${ok ? '' : 'disabled'}>${label}</button>`;
  return `<div class="alert t-${a.tier} s-${a.state} ${done ? 'done' : ''}"><div class="ah"><span class="badge">${a.tier.toUpperCase()}</span><b>${esc(a.title)}</b><span class="st">${stl}</span></div>
   <div class="mut" style="font-size:12px">sim ${esc(fmtSim(a.sim_ts))} · seen ×${a.occurrences}${a.condition_active ? '' : ' · condition cleared'}</div>
   <ul>${(a.reasons || []).map(r => `<li>${esc(r)}</li>`).join('')}</ul>${a.tier !== 'Info' ? `<div class="tl">${ev.join('')}</div>` : ''}${esc_}
   ${act ? `<div class="acts">${btn('ack', `Acknowledge as ${esc(who)}`, a.state === 'NOTIFIED')}${btn('respond', 'Responding', ['NOTIFIED', 'ACKNOWLEDGED'].includes(a.state))}${btn('resolve', 'Resolve', true)}</div>` : ''}</div>`;
}
function renderAlerts() {
  const list = Object.values(S.alerts).sort((a, b) => ((b.state === 'RESOLVED' || b.state === 'CLOSED') ? 0 : 1) - ((a.state === 'RESOLVED' || a.state === 'CLOSED') ? 0 : 1) || TIER_RANK[b.tier] - TIER_RANK[a.tier] || b.id - a.id).slice(0, 12);
  const open = list.filter(a => !['RESOLVED', 'CLOSED'].includes(a.state)).length;
  $('#alertCount').textContent = open ? `${open} open` : 'all clear';
  $('#alerts').innerHTML = list.length ? list.map(alertCard).join('') : '<div class="mut">No alerts. The system is watching — and will tell you if it can’t see.</div>';
}
function renderSide() {
  const m = S.metrics || {}, L = S.ledger || {};
  $('#metrics').innerHTML = [['Alerts', m.total ?? 0], ['Critical', m.critical ?? 0], ['Unacked', m.unacked ?? 0], ['Mean time to ack', m.mean_tta != null ? m.mean_tta + 's' : '—'], ['Mean time to resolve', m.mean_ttr != null ? m.mean_ttr + 's' : '—'], ['Missed escalations', m.missed_escalations ?? 0]]
    .map(([k, v]) => `<div class="m"><b>${v}</b><span>${k}</span></div>`).join('');
  $('#ledger').innerHTML = `<div class="big">${L.raw_hits ?? 0} raw threshold hits → ${L.alerts_raised ?? 0} alerts raised</div>
   <div><span>Blocked by signal-quality gate</span><b>${L.gated_quality ?? 0}</b></div><div><span>Held back by persistence rule</span><b>${L.persistence ?? 0}</b></div>
   <div><span>Merged by de-duplication</span><b>${L.dedupe ?? 0}</b></div><div><span>Held by cooldown</span><b>${L.cooldown ?? 0}</b></div>
   <div class="mut" style="font-size:11.5px;border:0">“Raw hit” = what a naive fixed-threshold monitor would have alarmed on.</div>`;
  $('#notes').innerHTML = S.notes.slice(0, 4).map(n => `<div style="margin-top:6px">📝 <i>${esc(n.text)}</i> <span class="mut">[${esc(n.lang)}]</span> ${(n.labels || n.flags || []).map(f => `<span class="note-chip">${esc(f)}</span>`).join('')}</div>`).join('');
  const c = S.control || {};
  $$('[data-k]').forEach(b => { const [k, v] = b.dataset.k.split(':'); b.classList.toggle('on', c[k] === v); });
  $('#bFault').classList.toggle('on', c.fault === 'probe_off'); $('#bFlat').classList.toggle('on', c.fault === 'flatline');
  $('#bLink').classList.toggle('on', c.link_up === false); $('#bLink').textContent = c.link_up === false ? 'Restore network' : 'Simulate network outage';
  $('#bPower').classList.toggle('on', !!c.power_loss); $$('[data-sp]').forEach(b => b.classList.toggle('on', +b.dataset.sp === c.speed));
  const run = S.judge && S.judge.running; $('#bJudge').textContent = run ? '■ Stop Judge Mode' : '▶ Judge Mode (auto demo)';
}
function renderCaregiver() {
  const me = S.cg.find(c => c.id === S.acting); if (!me) return; $('#phoneWho').textContent = `${me.name} (${me.role})`;
  const mine = Object.values(S.alerts).filter(a => (a.notified || []).some(n => n.who === me.name) && a.tier !== 'Info').sort((a, b) => b.id - a.id);
  $('#phone').innerHTML = `<button class="btn sm" id="bCheckin" style="width:100%;margin-bottom:10px">📍 Check in for shift</button>` +
    (mine.length ? mine.map(alertCard).join('') : '<div class="mut" style="text-align:center;margin-top:60px">No notifications for you yet.<br>Start a scenario on the Live tab.</div>');
  const ago = t => { if (!t) return 'not checked in'; const s = Math.round(nowS() - t); return s < 90 ? `checked in ${s}s ago` : `checked in ${Math.round(s / 60)}m ago`; };
  const by = (S.metrics && S.metrics.acks_by) || {};
  $('#attend').innerHTML = `<table><tr><th>Caregiver</th><th>Role</th><th>Attendance</th><th>Alerts acknowledged</th></tr>${S.cg.map(c => `<tr><td><b>${esc(c.name)}</b></td><td>${esc(c.role)}</td><td>${ago(S.checkins[c.id])}</td><td>${by[c.name] || 0}</td></tr>`).join('')}</table>`;
}

function render() {
  renderTop(); renderVitals(); renderRisk(); renderAlerts(); renderSide(); if (S.tab === 'caregiver') renderCaregiver(); siren();
}

/* ---------------------------------------------------------------- siren + toasts */
let ac = null, osc = null, sirenTimer = null;
function startSiren() {
  if (!S.audio || S.muted || osc) return;
  try {
    ac = ac || new (window.AudioContext || window.webkitAudioContext)(); if (ac.resume) ac.resume();
    osc = ac.createOscillator(); const g = ac.createGain(); osc.type = 'sawtooth'; g.gain.value = 0.18; osc.connect(g); g.connect(ac.destination); osc.start();
    let hi = false; const flip = () => { hi = !hi; osc.frequency.setValueAtTime(hi ? 960 : 700, ac.currentTime); }; flip(); sirenTimer = setInterval(flip, 420);
    if (navigator.vibrate) navigator.vibrate([300, 150, 300]);
  } catch (e) { osc = null; }
}
function stopSiren() { if (sirenTimer) clearInterval(sirenTimer); sirenTimer = null; if (osc) { try { osc.stop(); } catch (e) {} osc = null; } }
function siren() {
  const crit = Object.values(S.alerts).filter(a => a.tier === 'Critical' && a.state === 'NOTIFIED').sort((a, b) => b.id - a.id)[0], el = $('#siren');
  if (!crit) { el.classList.add('hidden'); stopSiren(); return; }
  el.classList.remove('hidden'); startSiren();
  $('#sirenWhy').innerHTML = esc((crit.reasons || [])[0] || crit.title);
  const left = crit.deadline ? Math.max(0, crit.deadline - nowS()).toFixed(0) : null;
  $('#sirenEsc').textContent = `Notified: ${crit.to}` + (crit.next_to && left != null ? ` — escalates to ${crit.next_to} in ${left}s` : ' — emergency contact notified');
  $('#sirenAck').dataset.id = crit.id; $('#sirenAck').textContent = `ACKNOWLEDGE as ${(S.cg.find(c => c.id === S.acting) || {name: ''}).name}`;
}
function toast(m) {
  const mine = S.cg.find(c => c.id === S.acting);
  if (window.Notification && Notification.permission === 'granted' && mine && mine.name === m.to.name) { try { new Notification(`[${m.tier}] ${m.title}`, {body: m.body}); } catch (e) {} }
  const d = document.createElement('div'); d.className = 'toast ' + m.tier;
  d.innerHTML = `<small>📲 PUSH → <b>${esc(m.to.name)}</b> (${esc(m.to.role)})</small><div><b>${esc(m.title)}</b></div><small>${esc(m.body)}</small>`;
  $('#toasts').prepend(d); while ($('#toasts').children.length > 4) $('#toasts').lastChild.remove(); setTimeout(() => d.remove(), 9000);
}

/* ---------------------------------------------------------------- tabs: audit / model / safety */
async function loadAudit() {
  const rows = await (await fetch('/api/audit?limit=120')).json();
  $('#auditT').innerHTML = '<tr><th>Time</th><th>Actor</th><th>Action</th><th>Alert</th><th>Detail</th><th>Hash</th></tr>' + rows.map(r =>
    `<tr><td class="mono">${new Date(r.wall * 1000).toLocaleTimeString('en-GB')}</td><td>${esc(r.actor)}</td><td><b>${esc(r.action)}</b></td><td>${r.alert_id ?? ''}</td>
     <td class="mono" style="font-size:11.5px;max-width:520px;word-break:break-word">${esc(JSON.stringify(r.detail))}</td><td class="mono mut">${esc(r.hash)}</td></tr>`).join('');
}
async function loadModel() {
  const c = await (await fetch('/api/model')).json(), m = c.metrics_synthetic, co = Object.entries(c.coefficients).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])), mx = Math.max(...co.map(x => Math.abs(x[1])));
  $('#modelC').innerHTML = `<h3>Risk model card</h3><p>${esc(c.model)}. ${esc(c.trained_on)}.</p>
   <div class="metrics" style="grid-template-columns:repeat(auto-fit,minmax(170px,1fr))">${[['AUROC (synthetic)', m.auroc], ['Early warning raised', m.episodes_with_early_warning], ['Median lead time (h)', m.median_lead_time_hours_before_event],
     ['Non-deteriorating episodes that still alerted', m.episodes_without_deterioration_that_still_raised_alert]].map(([k, v]) => `<div class="m"><b>${v}</b><span>${k}</span></div>`).join('')}</div>
   <p class="mut">Persistence rule: ${esc(m.persistence_rule)}. Bands: Medium ≥ ${c.bands.medium}, High ≥ ${c.bands.high} (illustrative).</p><h3 style="margin-top:14px">Coefficients (standardised features)</h3>
   ${co.map(([k, v]) => `<div class="coef"><span class="mono">${esc(k)}</span><span><i class="${v < 0 ? 'neg' : ''}" style="width:${100 * Math.abs(v) / mx}%"></i></span><span class="mono">${v.toFixed(2)}</span></div>`).join('')}
   <h3 style="margin-top:14px">Honest limitations</h3><ul>${c.limitations.map(l => `<li>${esc(l)}</li>`).join('')}</ul>`;
}
$('#safetyC').innerHTML = `<h3>Safety, assumptions &amp; limitations</h3>
<p><b>This is an experimental software prototype, not a medical device.</b> It uses synthetic data only, makes no diagnosis, and gives no treatment advice or clinical accuracy claims.</p>
<h4>Assumptions</h4><ul><li>Vitals come from a simulator; one reading = 15 simulated minutes; the demo runs faster than real time.</li><li>The safety floor uses a <b>partial, illustrative</b> NEWS2-style structure (SpO₂, systolic BP, pulse, temperature). Respiratory rate, consciousness and supplemental oxygen are not simulated.</li>
<li>The personal baseline is learned from the first 48 simulated hours and is assumed to be a stable period.</li><li>Escalation timeouts are demo-short (seconds); a real deployment would use minutes and be clinically reviewed.</li></ul>
<h4>Limitations</h4><ul><li>The risk model is trained on labels from our own simulator: metrics show the pipeline works, not clinical accuracy.</li><li>The caregiver-note reader is keyword-based (English / Tamil / Hindi) with simple negation handling for English only; it nudges risk, it does not understand text.</li>
<li>Flatline detection needs 6 identical readings. Baseline does not yet adapt to long-term changes. No respiratory rate.</li><li>Single patient, single device, no authentication; push goes to the dashboard (optional ntfy for real push).</li></ul>
<h4>Safety design</h4><ul><li><b>Safety floor</b> always alerts, independent of the model. <b>Signal-quality gate</b>: a bad sensor never raises a clinical alarm. <b>Dead-man's switch</b>: missing data is an alert, never “fine”.</li>
<li>Every alert and action is written to a hash-chained audit log. Every Warning/Critical alert needs a human to resolve it.</li></ul>
<h4>Scaling (design note)</h4><p>Partition by patient_id; MQTT/Kafka between devices and stateless risk workers; per-patient state in Redis/Postgres; edge safety floor on the home gateway so critical values alert even if the cloud is down.</p>`;

/* ---------------------------------------------------------------- wiring */
document.addEventListener('click', async e => {
  const t = e.target.closest('button'); if (!t) return;
  if (t.dataset.a) { const who = (S.cg.find(c => c.id === S.acting) || {name: 'Caregiver'}).name; await api(`/api/alerts/${t.dataset.id}/${t.dataset.a}`, 'POST', {who}); }
  else if (t.dataset.c) await api('/api/sim/control', 'POST', JSON.parse(t.dataset.c));
  else if (t.dataset.sp) await api('/api/sim/control', 'POST', {speed: +t.dataset.sp});
  else if (t.dataset.note) { $('#noteTxt').value = t.dataset.note; }
  else if (t.dataset.t) { S.tab = t.dataset.t; $$('nav.tabs button').forEach(b => b.classList.toggle('act', b === t)); ['live', 'caregiver', 'audit', 'model', 'safety'].forEach(n => $('#tab-' + n).classList.toggle('hidden', n !== S.tab));
    if (S.tab === 'audit') loadAudit(); if (S.tab === 'model') loadModel(); render(); }
  else if (t.id === 'bFault') await api('/api/sim/control', 'POST', {fault: S.control.fault === 'probe_off' ? null : 'probe_off'});
  else if (t.id === 'bFlat') await api('/api/sim/control', 'POST', {fault: S.control.fault === 'flatline' ? null : 'flatline'});
  else if (t.id === 'bLink') await api('/api/sim/control', 'POST', {link_up: !S.control.link_up});
  else if (t.id === 'bPower') await api('/api/sim/control', 'POST', {power_loss: !S.control.power_loss});
  else if (t.id === 'bReset') await api('/api/sim/reset');
  else if (t.id === 'bJudge') await api(S.judge && S.judge.running ? '/api/judge/stop' : '/api/judge/start');
  else if (t.id === 'noteAdd') { const v = $('#noteTxt').value.trim(); if (v) { await api('/api/notes', 'POST', {text: v, author: (S.cg.find(c => c.id === S.acting) || {}).name}); $('#noteTxt').value = ''; } }
  else if (t.id === 'bCheckin') await api(`/api/caregivers/${S.acting}/checkin`);
  else if (t.id === 'bVerify') { const r = await (await fetch('/api/audit/verify')).json(); const v = $('#verify'); v.textContent = r.ok ? `✔ chain intact (${r.checked} entries)` : `✖ tampering detected at #${r.broken_at}`; v.className = 'chip ' + (r.ok ? 's0' : 's3'); }
  else if (t.id === 'sirenAck') await api(`/api/alerts/${t.dataset.id}/ack`, 'POST', {who: (S.cg.find(c => c.id === S.acting) || {name: 'Caregiver'}).name});
  else if (t.id === 'muteBtn') { S.muted = !S.muted; t.textContent = S.muted ? '🔇' : '🔊'; if (S.muted) stopSiren(); else siren(); }
  else if (t.id === 'startBtn') { S.audio = true; $('#gate').classList.add('hidden'); try { ac = new (window.AudioContext || window.webkitAudioContext)(); ac.resume(); } catch (er) {}
    if (window.Notification && Notification.permission === 'default') Notification.requestPermission(); }
});
$('#acting').addEventListener('change', e => { S.acting = e.target.value; render(); });
setInterval(() => { render(); if (S.tab === 'audit') loadAudit(); }, 1000);
fetch('/api/state').then(r => r.json()).then(s => { applyState(s); render(); }).catch(() => {});
connect();
