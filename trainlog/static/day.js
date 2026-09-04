function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(t._h);
  t._h = setTimeout(() => { t.hidden = true; }, 2600);
}

async function post(url, body) {
  const r = await fetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  const d = await r.json();
  if (!d.ok) { toast(d.error || 'Something went wrong'); throw new Error(d.error); }
  return d;
}

const num = v => (v === '' || v === null ? null : Number(v));

function debounce(fn, ms) {
  let h;
  return (...a) => { clearTimeout(h); h = setTimeout(() => fn(...a), ms); };
}

function markOverride(input) {
  const t = input.dataset.target;
  if (t === undefined || t === '') return;
  input.classList.toggle('override', String(input.value) !== String(t));
}

async function sendSet(exEl, rowEl, completed) {
  const reps = rowEl.querySelector('.reps');
  const load = rowEl.querySelector('.load');
  const d = await post('/api/set', {
    date: DAY_DATE,
    exercise_id: exEl.dataset.ex,
    set_index: Number(rowEl.dataset.idx),
    is_backoff: rowEl.dataset.bo === '1',
    actual_reps: num(reps ? reps.value : null),
    actual_load: num(load ? load.value : null),
    completed: completed
  });
  if (completed) startTimer(d.rest_seconds);
  return d;
}

document.querySelectorAll('.ex').forEach(exEl => {
  exEl.querySelectorAll('.setrow').forEach(rowEl => {
    const cb = rowEl.querySelector('.setdone');
    if (cb) {
      cb.addEventListener('change', async () => {
        try {
          await sendSet(exEl, rowEl, cb.checked);
        } catch (e) {
          cb.checked = !cb.checked;
        }
      });
    }
    rowEl.querySelectorAll('.reps, .load').forEach(inp => {
      inp.addEventListener('input', () => markOverride(inp));
      inp.addEventListener('input', debounce(() => {
        if (cb && cb.checked) sendSet(exEl, rowEl, true).catch(() => {});
      }, 400));
      inp.addEventListener('keydown', e => {
        if (e.key === 'Enter' && cb) {
          cb.checked = true;
          cb.dispatchEvent(new Event('change'));
        }
      });
      markOverride(inp);
    });
  });

  exEl.querySelectorAll('[data-metric]').forEach(inp => {
    const send = debounce(async () => {
      const isNum = inp.tagName === 'INPUT' && inp.type === 'number';
      await post('/api/metric', {
        date: DAY_DATE,
        exercise_id: exEl.dataset.ex,
        field_key: inp.dataset.metric,
        value_num: isNum ? num(inp.value) : null,
        value_text: isNum ? null : inp.value
      });
    }, 400);
    inp.addEventListener('input', send);
    inp.addEventListener('change', send);
  });
});

async function exDone(id) {
  try {
    await post('/api/exercise/done', {date: DAY_DATE, exercise_id: id});
    location.reload();
  } catch (e) {}
}

function anchorFields(el) {
  const f = {};
  el.querySelectorAll('[data-field]').forEach(i => {
    f[i.dataset.field] = i.type === 'number' ? num(i.value) : i.value;
  });
  return f;
}

document.querySelectorAll('[data-anchor]').forEach(el => {
  const cb = el.querySelector('.anchor-done');
  const send = completed => post('/api/anchor', {
    date: DAY_DATE,
    item_key: el.dataset.anchor,
    fields: anchorFields(el),
    completed: completed
  });
  if (cb) {
    cb.addEventListener('change', async () => {
      try {
        await send(cb.checked);
        el.classList.toggle('done', cb.checked);
      } catch (e) {
        cb.checked = !cb.checked;
      }
    });
  }
  el.querySelectorAll('[data-field]').forEach(i => {
    i.addEventListener('input', debounce(() => {
      send(cb ? cb.checked : false).catch(() => {});
    }, 400));
  });
});

async function anchorAll() {
  try {
    await post('/api/anchor/done_all', {date: DAY_DATE});
    location.reload();
  } catch (e) {}
}

const notes = document.getElementById('notes');
if (notes) {
  notes.addEventListener('input', debounce(() => {
    post('/api/day/notes', {date: DAY_DATE, notes: notes.value}).catch(() => {});
  }, 600));
}

const dd = document.getElementById('daydone');
if (dd) {
  dd.addEventListener('click', async () => {
    try {
      const d = await post('/api/day/complete',
        {date: DAY_DATE, complete: !DAY_DONE});
      toast(d.message);
      setTimeout(() => location.reload(), 900);
    } catch (e) {}
  });
}

async function applyAdj(id) {
  try { await post('/api/adjustment/' + id + '/apply', {}); location.reload(); }
  catch (e) {}
}

async function ignoreAdj(id) {
  try { await post('/api/adjustment/' + id + '/ignore', {}); location.reload(); }
  catch (e) {}
}

async function dismissBanner() {
  try { await post('/api/state/dismiss_banner', {}); location.reload(); }
  catch (e) {}
}

const dp = document.getElementById('datepick');
if (dp) {
  dp.addEventListener('change', () => {
    if (dp.value) location.href = '/day/' + dp.value;
  });
}
