let _t = null, _left = 0;

function stopTimer() {
  if (_t) clearInterval(_t);
  _t = null;
  const b = document.getElementById('rest');
  if (b) { b.hidden = true; b.classList.remove('zero'); }
}

function startTimer(secs) {
  if (!secs || secs <= 0) return;
  const box = document.getElementById('rest');
  const lbl = document.getElementById('restlbl');
  if (!box || !lbl) return;
  if (_t) clearInterval(_t);
  _left = secs;
  box.hidden = false;
  box.classList.remove('zero');
  const draw = () => {
    const m = Math.floor(_left / 60), s = _left % 60;
    lbl.textContent = 'Rest ' + m + ':' + String(s).padStart(2, '0');
  };
  draw();
  _t = setInterval(() => {
    _left -= 1;
    if (_left <= 0) {
      clearInterval(_t);
      _t = null;
      lbl.textContent = 'Rest done';
      box.classList.add('zero');
      setTimeout(stopTimer, 4000);
    } else {
      draw();
    }
  }, 1000);
}
