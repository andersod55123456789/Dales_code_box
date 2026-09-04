const g = id => document.getElementById(id);
const numOrNull = v => (v === '' ? null : Number(v));

function radio(name) {
  const el = document.querySelector('input[name="' + name + '"]:checked');
  return el ? el.value : 'ok';
}

g('savecheckin').addEventListener('click', async () => {
  const body = {
    date: CHECKIN_DATE,
    sleep_hours: numOrNull(g('sleep_hours').value),
    sleep_quality: Number(g('sleep_quality').value),
    energy: Number(g('energy').value),
    soreness: Number(g('soreness').value),
    mood: Number(g('mood').value),
    resting_hr: numOrNull(g('resting_hr').value),
    pec_status: radio('pec_status'),
    knee_status: radio('knee_status'),
    shoulder_status: radio('shoulder_status'),
    notes: g('notes').value
  };
  const r = await fetch('/api/checkin', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  const d = await r.json();
  if (!d.ok) { alert(d.error || 'Save failed'); return; }

  const box = g('warnbox');
  box.innerHTML = '';
  const pending = (d.warnings || []).filter(w => w.status === 'pending');
  pending.forEach(w => {
    const div = document.createElement('div');
    div.className = 'card warning sev-' + (w.severity || 'warning');
    const title = document.createElement('p');
    title.className = 'wtitle';
    title.textContent = '⚠ ' + (w.severity || 'warning').toUpperCase();
    const msg = document.createElement('p');
    msg.textContent = w.message;
    const sug = document.createElement('p');
    sug.className = 'sug';
    sug.textContent = 'Suggested: ' + w.suggestion;
    const link = document.createElement('a');
    link.className = 'btn';
    link.href = '/day/today';
    link.textContent = 'Go to today';
    div.append(title, msg, sug, link);
    box.appendChild(div);
  });

  const t = g('toast');
  t.textContent = 'Check-in saved' +
    (pending.length ? ' - guardrail warnings below' : '');
  t.hidden = false;
  setTimeout(() => { t.hidden = true; }, 3000);
});
