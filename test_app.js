// Runs the app's real inline script against a minimal DOM stub, then drives the
// filters the way a user would and checks the rendered rows.
//
//   node test_app.js
//
// This exists because the filter logic is the part that can be quietly wrong:
// a mis-set flag hides plazas rather than throwing, so only asserting on
// rendered output catches it.

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const dir = __dirname;
const html = fs.readFileSync(path.join(dir, 'docs/index.html'), 'utf8');
const dataJs = fs.readFileSync(path.join(dir, 'docs/data.js'), 'utf8');
const appJs = html.match(/<script>([\s\S]*?)<\/script>/)[1];

// ---- DOM stub ---------------------------------------------------------------
function makeEl(id, tag = 'div') {
  const el = {
    id, tagName: tag, dataset: {}, style: {}, children: [],
    _html: '', _text: '', value: '', hidden: false, attrs: {},
    get innerHTML() { return this._html; },
    set innerHTML(v) { this._html = String(v); this.children = parseButtons(this._html); },
    get textContent() { return this._text; },
    set textContent(v) { this._text = String(v); },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k]; },
    querySelectorAll(sel) {
      if (sel === 'th') return this.children.filter(c => c.tagName === 'th');
      if (sel === 'button') return this.children.filter(c => c.tagName === 'button');
      return [];
    },
    closest() { return null },
    appendChild() {}, click() {},
  };
  return el;
}

// The app re-reads <th data-key> and <button data-v> out of innerHTML it just
// wrote, so the stub has to surface those back as elements.
function parseButtons(htmlStr) {
  const out = [];
  for (const m of htmlStr.matchAll(/<(th|button)\b([^>]*)>/g)) {
    const el = makeEl(null, m[1]);
    const key = /data-key="([^"]*)"/.exec(m[2]);
    const v = /data-v="([^"]*)"/.exec(m[2]);
    if (key) el.dataset.key = key[1];
    if (v) el.dataset.v = v[1];
    out.push(el);
  }
  return out;
}

const els = {};

// Elements declared `hidden` in the markup must start hidden, or the stub would
// report a banner as visible when the real page has it collapsed.
const INITIALLY_HIDDEN = new Set(
  [...html.matchAll(/<[a-z]+\b([^>]*\bid="([^"]+)"[^>]*)>/g)]
    .filter(m => /\bhidden\b/.test(m[1]))
    .map(m => m[2])
);

const SEG_BUTTONS = {
  fVac: ['all', 'yes', 'no'],
  fIti: ['all', 'no', 'yes'],
  fJor: ['all', 'full', 'J', 'H'],
};

const document = {
  getElementById(id) {
    if (!els[id]) {
      els[id] = makeEl(id);
      els[id].hidden = INITIALLY_HIDDEN.has(id);
      if (SEG_BUTTONS[id]) {
        els[id].children = SEG_BUTTONS[id].map(v => {
          const b = makeEl(null, 'button');
          b.dataset.v = v;
          return b;
        });
      }
    }
    return els[id];
  },
  createElement: tag => makeEl(null, tag),
};

const sandbox = {
  window: {}, document, console,
  setTimeout: (fn) => fn(),   // run the search debounce immediately
  clearTimeout: () => {},
  URL: { createObjectURL: () => 'blob:x', revokeObjectURL: () => {} },
  Blob: function (parts) { this.parts = parts; },
};
sandbox.globalThis = sandbox;

const ctx = vm.createContext(sandbox);
vm.runInContext(dataJs, ctx);
vm.runInContext(appJs, ctx);

// ---- helpers ----------------------------------------------------------------
const rowCount = () => (sandbox.window.__visible || []).length;
const visible = () => sandbox.window.__visible || [];
const el = id => document.getElementById(id);

function clickSeg(id, value) {
  const box = el(id);
  const btn = box.children.find(b => b.dataset.v === value);
  if (!btn) throw new Error(`no ${value} button in ${id}`);
  box.onclick({ target: { closest: () => btn } });
}
function setSlider(minutes) {
  el('fMin').value = String(minutes);
  el('fMin').oninput();
}
function setEsp(value) { el('fEsp').value = value; el('fEsp').onchange(); }
function search(text) { el('fQ').oninput({ target: { value: text } }); }
function sortBy(key) {
  const th = el('head').children.find(c => c.dataset.key === key);
  th.onclick();
}

// ---- assertions -------------------------------------------------------------
let pass = 0, fail = 0;
function check(name, cond, detail = '') {
  if (cond) { pass++; console.log(`  ok   ${name}`); }
  else { fail++; console.log(`  FAIL ${name} ${detail}`); }
}

const DATA = sandbox.window.OFERTA;
const all = DATA.rows;
const infantil = all.filter(r => r.cuerpo === '0597' && r.especialidad === '031');

console.log('data: %d rows, %d especialidades', all.length, DATA.especialidades.length);

console.log('\ndefault state (Educación Infantil, <=90 min):');
const inf90 = infantil.filter(r => r.minutes <= 90);
check('defaults to Educación Infantil within 90 min', rowCount() === inf90.length,
      `got ${rowCount()} want ${inf90.length}`);
check('sorted ascending by drive time',
      visible().every((r, i, a) => i === 0 || a[i - 1].minutes <= r.minutes));
check('every visible row is Educación Infantil',
      visible().every(r => r.cuerpo === '0597' && r.especialidad === '031'));

console.log('\nslider:');
setSlider(150);
check('150 min shows all 303 Infantil plazas', rowCount() === infantil.length,
      `got ${rowCount()} want ${infantil.length}`);
setSlider(30);
const inf30 = infantil.filter(r => r.minutes <= 30);
check('30 min matches expected subset', rowCount() === inf30.length,
      `got ${rowCount()} want ${inf30.length}`);
check('no row over 30 min', visible().every(r => r.minutes <= 30));

console.log('\nvacante (V):');
clickSeg('fVac', 'yes');
check('sólo V → every row vacante', visible().every(r => r.vacante) && rowCount() > 0);
check('sólo V count', rowCount() === inf30.filter(r => r.vacante).length);
clickSeg('fVac', 'no');
check('sin V → no row vacante', visible().every(r => !r.vacante) && rowCount() > 0);
check('V + sin V partition the set',
      inf30.filter(r => r.vacante).length + rowCount() === inf30.length);
clickSeg('fVac', 'all');

console.log('\nitinerante (Iti):');
clickSeg('fIti', 'no');
check('no itinerante → all N', visible().every(r => !r.itinerante) && rowCount() > 0);
clickSeg('fIti', 'yes');
check('sí itinerante → all S', visible().every(r => r.itinerante));
clickSeg('fIti', 'all');

console.log('\njornada:');
clickSeg('fJor', 'full');
check('completa → jornada empty', visible().every(r => !r.jornada) && rowCount() > 0);
clickSeg('fJor', 'J');
check('J → jornada J only', visible().every(r => r.jornada === 'J') && rowCount() > 0);
clickSeg('fJor', 'H');
check('H → jornada H only (Infantil has none, so empty)',
      visible().every(r => r.jornada === 'H'));
clickSeg('fJor', 'all');

console.log('\ncombined filters (the actual question asked):');
setSlider(30);
clickSeg('fVac', 'yes');
clickSeg('fIti', 'no');
clickSeg('fJor', 'full');
const expected = infantil.filter(r => r.minutes <= 30 && r.vacante && !r.itinerante && !r.jornada);
check('V + no itinerante + completa + <=30min', rowCount() === expected.length,
      `got ${rowCount()} want ${expected.length}`);
check('combined result is non-empty', rowCount() > 0);
console.log(`       → ${rowCount()} plazas, closest ${visible()[0].minutes} min (${visible()[0].localidad})`);

console.log('\nsearch:');
el('bReset').onclick();
search('oviedo');
check('search narrows to Oviedo', rowCount() > 0 &&
      visible().every(r => (r.centre_name + r.localidad + r.concejo).toLowerCase().includes('oviedo')));
search('zzzznope');
check('no match → empty and empty-state shown', rowCount() === 0 && el('empty').hidden === false);

console.log('\nreset:');
el('bReset').onclick();
check('reset restores default count', rowCount() === inf90.length,
      `got ${rowCount()} want ${inf90.length}`);
check('reset clears search box', el('fQ').value === '');

console.log('\nsorting:');
sortBy('km');
check('sort by km ascending',
      visible().every((r, i, a) => i === 0 || a[i - 1].km <= r.km));
sortBy('km');
check('second click reverses',
      visible().every((r, i, a) => i === 0 || a[i - 1].km >= r.km));
sortBy('localidad');
check('sort by localidad is alphabetical',
      visible().every((r, i, a) => i === 0 ||
        a[i - 1].localidad.localeCompare(r.localidad, 'es') <= 0));

console.log('\nespecialidad switch:');
setEsp('all');
check('all especialidades within 90 min',
      rowCount() === all.filter(r => r.minutes <= 90).length);
setEsp('0597|038');
check('Educación Primaria only',
      rowCount() > 0 && visible().every(r => r.especialidad === '038'));
check('jornada H exists outside Infantil',
      all.some(r => r.jornada === 'H'));

console.log('\nvintage banner:');
check('meta carries the PDF date', DATA.meta && /^\d{4}-\d{2}-\d{2}$/.test(DATA.meta.source_date),
      JSON.stringify(DATA.meta));
check('vintage pill names the month in Spanish',
      /datos de .*(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)/
        .test(el('vintage').textContent), el('vintage').textContent);
const ageDays = Math.floor((Date.now() - new Date(DATA.meta.source_date + 'T00:00:00')) / 86400000);
check('stale warning matches the data age (>30 days ⇒ shown)',
      el('staleWarn').hidden === (ageDays <= 30),
      `age ${ageDays}d, hidden=${el('staleWarn').hidden}`);
console.log(`       → data is ${ageDays} day(s) old, warning ${el('staleWarn').hidden ? 'hidden' : 'shown'}`);

console.log('\ncsv export:');
el('bReset').onclick();
setSlider(30);
let csv = null;
sandbox.Blob = function (parts) { csv = parts[0]; };
el('bCsv').onclick();
const lines = csv.trim().split('\n');
check('csv has header + one line per visible row', lines.length === rowCount() + 1,
      `got ${lines.length - 1} want ${rowCount()}`);
check('csv header is semicolon separated', lines[0].startsWith('minutes;km;localidad'));
check('csv quotes centre names containing the separator',
      !lines.slice(1).some(l => l.split(';').length < 14));

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
