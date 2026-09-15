// หน้าตาและการทำงานทั้งหมดของเว็บ — ตรรกะคำนวณอยู่ใน calc.js / search.js
import * as D from './data.js';
import * as C from './calc.js';
import { searchItems, itemCategory, normSearch, SEARCH_MIN_SCORE } from './search.js';
import { readSheet, writeSheet } from './api.js';

const $ = (id) => document.getElementById(id);
const STORE = 'darkstory-codex';

const state = {
  items: [],
  rate: 0.008,
  dirty: false,        // มีของที่แก้แล้วยังไม่ได้ส่งขึ้นชีต
  busy: false,
};

// ───────────────────────── ตัวช่วยเล็กๆ ─────────────────────────

const money = (v) => Number(v).toLocaleString('th-TH', {
  minimumFractionDigits: 1, maximumFractionDigits: 1,
});
const count = (v) => Number(v).toLocaleString('th-TH');

/** อ่านตัวเลขจากข้อความ รองรับคอมมาคั่นหลัก คืน null ถ้าไม่ใช่ตัวเลข */
function parseNum(text) {
  const s = String(text ?? '').replace(/,/g, '').trim();
  if (!s) return null;
  const v = Number(s);
  return Number.isFinite(v) ? v : null;
}

function setStatus(text, kind = '') {
  const el = $('status');
  el.textContent = text;
  el.className = 'status ' + kind;
  el.hidden = !text;
}

/** ราคา "หินดั้งเดิม" จากรายการไอเทม — เทียบชื่อแบบเดียวกับช่องค้นหา */
function stonePrice() {
  const target = normSearch(D.BLUE_LADDER[1].name);
  for (const item of state.items) {
    if (normSearch(item.name) === target) {
      const price = parseNum(item.price);
      if (price > 0) return price;
    }
  }
  return 0;
}

function noPriceReason() {
  return state.items.length
    ? `กรุณาเช็คราคา ${D.BLUE_LADDER[1].name} และอัปเดตในแท็บไอเทมก่อนใช้งาน`
    : 'กรุณากดปุ่ม 🔄 โหลดข้อมูล ก่อนทำการคำนวณ';
}

// ───────────────────────── เก็บข้อมูลในเครื่อง ─────────────────────────

function saveLocal() {
  try {
    localStorage.setItem(STORE, JSON.stringify({
      rate: state.rate, items: state.items, dirty: state.dirty,
    }));
  } catch { /* โหมดส่วนตัวของเบราว์เซอร์เขียนไม่ได้ ไม่ใช่เรื่องคอขาดบาดตาย */ }
}

function loadLocal() {
  try {
    const raw = JSON.parse(localStorage.getItem(STORE) || '{}');
    if (raw.rate > 0) state.rate = raw.rate;
    if (Array.isArray(raw.items)) state.items = raw.items;
    state.dirty = !!raw.dirty;
  } catch { /* ข้อมูลเก่าพัง ก็เริ่มใหม่ */ }
}

// ───────────────────────── แท็บ ─────────────────────────

function showPage(name) {
  for (const page of document.querySelectorAll('.page')) {
    page.hidden = page.id !== 'page-' + name;
  }
  for (const btn of document.querySelectorAll('.tabbar button')) {
    btn.classList.toggle('active', btn.dataset.page === name);
  }
}

// ───────────────────────── แท็บตีบวก ─────────────────────────

function fillSelect(el, values, selected) {
  el.innerHTML = '';
  for (const v of values) {
    const opt = document.createElement('option');
    opt.value = v;
    opt.textContent = v;
    el.appendChild(opt);
  }
  if (selected !== undefined) el.value = selected;
}

/** อ่านตัวเลือกทั้งหมดแล้วคิดว่าต้องใช้อะไรบ้าง — แหล่งความจริงเดียวของหน้านี้ */
function planNow() {
  const start = Number($('st').value);
  const end = Number($('en').value);
  const grade = D.GRADES.indexOf($('gr').value);
  const mode = $('inh').value;
  const targetName = $('tgr').value;
  const target = D.GRADES.includes(targetName) ? D.GRADES.indexOf(targetName) : grade;

  if (mode === D.INHERIT_MODE_HIGHER) {
    const plan = C.upgradePlan(grade, start, target, end);
    return { start, end, grade, mode, target, pieces: plan.pieces, inherit: plan.gold, plan };
  }
  return {
    start, end, grade, mode, target,
    pieces: C.upgradePieces(start, end, grade),
    inherit: C.inheritCost(mode, end, grade, target),
    plan: null,
  };
}

/** จำกัดเกรดเป้าหมายตามโหมด — เลือกค่าที่ไม่มีข้อมูลไม่ได้ตั้งแต่แรก */
function onModeChange() {
  const mode = $('inh').value;
  const grade = D.GRADES.indexOf($('gr').value);
  const tgr = $('tgr');

  let choices;
  if (mode === D.INHERIT_MODE_SAME) choices = [D.GRADES[grade]];
  else if (mode === D.INHERIT_MODE_HIGHER) choices = D.GRADES.slice(grade + 1);
  else choices = [D.GRADES[grade]];

  if (!choices.length) choices = [D.GRADES[grade]];
  const keep = choices.includes(tgr.value) ? tgr.value : choices[0];
  fillSelect(tgr, choices, keep);
  tgr.disabled = choices.length < 2;
}

function updChance() {
  const have = parseNum($('have').value) ?? 0;
  let needed = null;
  let reason = '';
  try {
    needed = planNow().pieces;
  } catch (err) {
    reason = err instanceof C.CalcError ? err.message : 'เลือกค่าให้ครบก่อน';
  }

  const show = (pct, detail) => {
    $('chance').textContent = pct === null ? '—' : pct.toFixed(4) + ' %';
    $('bar-fill').style.width = (pct || 0) + '%';
    $('chance-detail').textContent = detail;
  };

  if (needed === null) return show(null, reason);
  if (needed === 0) return show(null, 'ไม่ต้องใช้ชิ้นส่วน มีแต่ค่าสืบทอด');

  const pct = C.successChance(have, needed);
  let detail = `มี ${count(have)} / ต้องใช้ ${count(needed)} ชิ้นส่วน`;
  if (have < needed) detail += `  •  ขาดอีก ${count(needed - have)}`;
  else if (have > needed) detail += `  •  เหลือ ${count(have - needed)}`;
  else detail += '  •  พอดีเป๊ะ';
  show(pct, detail);
}

function clearDetails(note) {
  for (const id of ['use-upgrade', 'use-inherit', 'need-pieces', 'cost-mat',
                    'cost-inherit', 'cost-total']) $(id).textContent = '—';
  for (const id of ['use-upgrade-why', 'use-inherit-why', 'need-melt',
                    'cost-thb']) $(id).textContent = '';
  $('calc-note').textContent = note || '';
}

function calcAll() {
  let info;
  try {
    info = planNow();
  } catch (err) {
    return clearDetails(err instanceof C.CalcError ? err.message : 'เลือกค่าให้ครบก่อน');
  }

  const base = stonePrice();
  const [stones, leftover] = C.melt(info.pieces, D.MATERIAL_BLUE_RATIO);
  const materialGold = C.piecesValue(info.pieces, base, D.MATERIAL_BLUE_RATIO);
  const total = materialGold + info.inherit;

  const ups = [];
  const inhs = [];
  if (info.plan) {
    for (const step of info.plan.steps) {
      if (step.kind === 'upgrade') ups.push(`ระดับ${D.GRADES[step.grade]} +${step.from}→+${step.to}`);
      else inhs.push(`${D.GRADES[step.grade]}→${D.GRADES[step.toGrade]}`);
    }
  } else {
    if (info.pieces > 0) ups.push(`ระดับ${D.GRADES[info.grade]} +${info.start}→+${info.end}`);
    if (info.inherit > 0) inhs.push(`${D.GRADES[info.grade]} ระดับเดียวกัน`);
  }

  $('use-upgrade').textContent = money(materialGold) + ' เหรียญทอง';
  $('use-inherit').textContent = money(info.inherit) + ' เหรียญทอง';
  $('use-upgrade-why').textContent = ups.length ? `(${ups.join(', ')})` : '';
  $('use-inherit-why').textContent = inhs.length ? `(${inhs.join(', ')})` : '';

  $('need-pieces').textContent = `ใช้ ${count(info.pieces)} ชิ้นส่วน`;
  $('need-melt').textContent = info.pieces
    ? `(${count(stones)} ${D.BLUE_LADDER[1].unit}${leftover ? ` + เศษ ${leftover} ชิ้น` : ''})`
    : '';
  $('cost-mat').textContent = money(materialGold) + ' เหรียญทอง';
  $('cost-inherit').textContent = money(info.inherit) + ' เหรียญทอง';
  $('cost-total').textContent = money(total) + ' เหรียญทอง';
  $('cost-thb').textContent = money(total * state.rate) + ' บาท';

  const notes = [];
  if (info.plan && info.plan.overshoot) {
    notes.push(`⚠ สืบทอดแล้วได้ +${info.plan.finalLevel} ซึ่งสูงกว่า +${info.end} ที่ตั้งไว้`);
  }
  if (base <= 0) notes.push(noPriceReason());
  $('calc-note').textContent = notes.join('\n');

  updChance();
}

// ───────────────────────── แท็บไอเทม ─────────────────────────

function renderItems() {
  const query = $('item-search').value;
  const chosen = $('item-filter').value;
  const list = $('item-list');

  const pool = state.items
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => chosen === D.ITEM_CATEGORY_ALL || itemCategory(item) === chosen);

  const matches = searchItems(pool.map((p) => p.item), query)
    .map((hit) => pool[hit.index]);

  list.innerHTML = '';
  if (!matches.length) {
    list.innerHTML = '<div class="empty">ไม่เจอรายการที่ค้นหา</div>';
  }
  for (const { item, index } of matches) {
    const btn = document.createElement('button');
    btn.className = 'item';
    btn.innerHTML = `
      <span class="name"></span>
      <span class="cat"></span>
      <span class="price"><b></b><span></span></span>`;
    btn.querySelector('.name').textContent = item.name;
    btn.querySelector('.cat').textContent = itemCategory(item);
    btn.querySelector('.price b').textContent = money(item.price) + ' ทอง';
    btn.querySelector('.price span').textContent = money(item.price * state.rate) + ' บาท';
    btn.addEventListener('click', () => openDialog(index));
    list.appendChild(btn);
  }

  const suffix = state.dirty ? ' • ยังไม่ได้บันทึก' : '';
  const total = state.items.length;
  let text;
  if (!normSearch(query)) {
    text = chosen === D.ITEM_CATEGORY_ALL
      ? `${total} รายการ${suffix}`
      : `${chosen} ${matches.length} จาก ${total} รายการ${suffix}`;
  } else if (!matches.length) {
    text = `ไม่เจอ '${query.trim()}'${suffix}`;
  } else {
    const best = searchItems(pool.map((p) => p.item), query)[0];
    text = best && best.score < SEARCH_MIN_SCORE
      ? `ไม่เจอที่ตรง — เดาว่าน่าจะเป็น ${matches.length} รายการนี้${suffix}`
      : `เจอ ${matches.length} จาก ${total} รายการ${suffix}`;
  }
  $('item-count').textContent = text;
}

let editingIndex = null;

function openDialog(index) {
  editingIndex = index;
  const item = index === null
    ? { name: '', price: '', category: D.ITEM_CATEGORY_DEFAULT }
    : state.items[index];
  $('dialog-title').textContent = index === null ? 'เพิ่มไอเทม' : 'แก้ไอเทม';
  $('d-name').value = item.name || '';
  $('d-price').value = index === null ? '' : item.price;
  fillSelect($('d-category'), D.ITEM_CATEGORIES, itemCategory(item));
  $('d-delete').hidden = index === null;
  $('d-hint').textContent = '';
  $('item-dialog').showModal();
}

function applyDialog(action) {
  if (action === 'cancel') return;
  if (action === 'delete') {
    if (editingIndex !== null) state.items.splice(editingIndex, 1);
  } else {
    const name = $('d-name').value.trim();
    const price = parseNum($('d-price').value);
    if (!name || price === null || price < 0) {
      $('d-hint').textContent = 'กรอกชื่อและราคาให้ถูกต้อง';
      $('item-dialog').showModal();
      return;
    }
    const next = { name, price, category: $('d-category').value };
    if (editingIndex === null) state.items.push(next);
    else state.items[editingIndex] = next;
  }
  state.dirty = true;
  saveLocal();
  renderItems();
  calcAll();
  setStatus('แก้ไขแล้ว ยังไม่ได้ส่งขึ้นชีต — กด 🔄 ค้างไว้เพื่อบันทึก', 'warn');
}

// ───────────────────────── แท็บแปลงเงิน ─────────────────────────

function updRate() {
  const value = parseNum($('rate').value);
  if (value === null || value <= 0) {
    $('rate-hint').textContent = 'เรตต้องเป็นตัวเลขมากกว่า 0';
    return;
  }
  state.rate = value;
  $('rate-hint').textContent = `1,000 ทอง = ${money(1000 * value)} บาท`;
  saveLocal();
  goldToThb();
  renderItems();
  calcAll();
}

function goldToThb() {
  const gold = parseNum($('gold').value);
  $('thb').value = gold === null ? '' : money(gold * state.rate);
}

function thbToGold() {
  const thb = parseNum($('thb').value);
  $('gold').value = thb === null || !state.rate ? '' : money(thb / state.rate);
}

// เครื่องคิดเลข — กดปุ่มทีละตัว ไม่ใช้ eval กับสิ่งที่ผู้ใช้พิมพ์
const calc = { acc: null, op: null, fresh: true };

function calcShow(text) {
  $('calc-display').textContent = text;
  const value = parseNum(text);
  $('calc-hint').textContent = (value === null || Math.abs(value) < 1000)
    ? '' : value.toLocaleString('th-TH', { maximumFractionDigits: 4 });
}

function calcApply(a, op, b) {
  if (op === '+') return a + b;
  if (op === '−') return a - b;
  if (op === '×') return a * b;
  if (b === 0) throw new Error('zero');
  return a / b;
}

function calcFmt(v) {
  if (!Number.isFinite(v)) return 'คำนวณไม่ได้';
  return String(Number(v.toPrecision(12)));
}

function calcKey(key) {
  const text = $('calc-display').textContent;

  if (key === 'C') { calc.acc = calc.op = null; calc.fresh = true; return calcShow('0'); }
  if (key === '←') {
    if (calc.fresh) return;
    const next = text.slice(0, -1);
    calc.fresh = next === '' || next === '-';
    return calcShow(calc.fresh ? '0' : next);
  }
  if (key === '±') {
    if (text.startsWith('-')) return calcShow(text.slice(1));
    if (parseNum(text)) return calcShow('-' + text);
    return;
  }
  if (/^\d$/.test(key)) {
    calcShow((calc.fresh || text === '0') ? key : text + key);
    calc.fresh = false;
    return;
  }
  if (key === '.') {
    if (calc.fresh) { calcShow('0.'); calc.fresh = false; }
    else if (!text.includes('.')) calcShow(text + '.');
    return;
  }
  if (key === '%') {
    let value = parseNum(text) ?? 0;
    // แบบเครื่องคิดเลขทั่วไป: 200 + 10% คือบวกด้วย 10% ของ 200
    value = (calc.op === '+' || calc.op === '−') && calc.acc !== null
      ? (calc.acc * value) / 100 : value / 100;
    calcShow(calcFmt(value));
    calc.fresh = false;
    return;
  }

  let value = parseNum(text) ?? 0;
  if (calc.op !== null && calc.acc !== null) {
    try {
      value = calcApply(calc.acc, calc.op, value);
    } catch {
      calc.acc = calc.op = null; calc.fresh = true;
      return calcShow('หารด้วยศูนย์ไม่ได้');
    }
  }
  calcShow(calcFmt(value));
  calc.acc = value;
  calc.op = key === '=' ? null : key;
  calc.fresh = true;
}

// ───────────────────────── ซิงก์กับชีต ─────────────────────────

async function loadFromServer() {
  if (state.busy) return;
  state.busy = true;
  setStatus('กำลังโหลดข้อมูลจากชีต...');

  const [currency, items] = await Promise.all([readSheet('currency'), readSheet('items')]);
  const failed = [];

  if (currency.error) failed.push('เรต');
  else {
    const row = (currency.rows || []).find((r) => r.key === 'rate_gold_to_thb');
    const value = row && parseNum(row.value);
    if (value > 0) { state.rate = value; $('rate').value = value; }
  }

  if (items.error) failed.push('ไอเทม');
  else {
    state.items = (items.rows || [])
      .map((r) => ({
        name: String(r.name ?? '').trim(),
        price: parseNum(r.price_gold),
        category: String(r.category ?? '').trim(),
      }))
      .filter((it) => it.name && it.price !== null);
    state.dirty = false;
  }

  state.busy = false;
  saveLocal();
  renderAll();
  setStatus(failed.length
    ? `โหลดไม่สำเร็จ: ${failed.join(', ')} — ${items.error || currency.error}`
    : `โหลดข้อมูลแล้ว ${state.items.length} รายการ`,
  failed.length ? 'warn' : 'ok');
}

async function saveToServer() {
  if (state.busy) return;
  if (!state.items.length) {
    return setStatus('รายการว่าง ไม่บันทึกทับชีต', 'warn');
  }
  if (!confirm(`บันทึกทับชีตด้วยข้อมูล ${state.items.length} รายการที่มีอยู่ตอนนี้?`)) return;

  state.busy = true;
  setStatus('กำลังบันทึกขึ้นชีต...');
  const rows = [['name', 'category', 'price_gold']]
    .concat(state.items.map((it) => [it.name, itemCategory(it), it.price]));
  const { error } = await writeSheet('items', rows);
  state.busy = false;

  if (error) return setStatus('บันทึกไม่สำเร็จ: ' + error, 'warn');
  state.dirty = false;
  saveLocal();
  renderItems();
  setStatus(`บันทึกขึ้นชีตแล้ว ${state.items.length} รายการ`, 'ok');
}

// ───────────────────────── เริ่มต้น ─────────────────────────

function renderAll() {
  $('rate').value = state.rate;
  updRate();
  renderItems();
  calcAll();
}

function init() {
  loadLocal();

  const range = (from) => Array.from(
    { length: D.MAX_LEVEL - from + 1 }, (_, i) => String(from + i));
  const levels = range(D.MIN_LEVEL);
  // ระดับตอนนี้ต้องเลือก +0 ได้ ไม่งั้นคิดต้นทุนจากไอเทมใหม่ไม่ได้เลย
  const startLevels = range(D.MIN_START_LEVEL);
  fillSelect($('gr'), D.GRADES, D.GRADES[0]);
  fillSelect($('st'), startLevels, '1');
  fillSelect($('inh'), D.INHERIT_MODES, D.INHERIT_NONE);
  fillSelect($('en'), levels, '10');
  fillSelect($('item-filter'), [D.ITEM_CATEGORY_ALL, ...D.ITEM_CATEGORIES], D.ITEM_CATEGORY_ALL);
  onModeChange();

  for (const id of ['gr', 'inh']) $(id).addEventListener('change', () => { onModeChange(); calcAll(); });
  for (const id of ['st', 'en', 'tgr']) $(id).addEventListener('change', calcAll);
  $('have').addEventListener('input', updChance);

  $('item-search').addEventListener('input', renderItems);
  $('item-filter').addEventListener('change', renderItems);
  $('clear-search').addEventListener('click', () => { $('item-search').value = ''; renderItems(); });
  $('add-item').addEventListener('click', () => openDialog(null));
  $('item-dialog').addEventListener('close', (e) => applyDialog($('item-dialog').returnValue));

  $('rate').addEventListener('input', updRate);
  $('gold').addEventListener('input', goldToThb);
  $('thb').addEventListener('input', thbToGold);

  const keys = ['C', '←', '%', '÷', '7', '8', '9', '×',
                '4', '5', '6', '−', '1', '2', '3', '+', '±', '0', '.', '='];
  for (const key of keys) {
    const btn = document.createElement('button');
    btn.textContent = key;
    if ('÷×−+'.includes(key)) btn.className = 'op';
    if (key === '=') btn.className = 'eq';
    btn.addEventListener('click', () => calcKey(key));
    $('keypad').appendChild(btn);
  }
  calcShow('0');

  for (const btn of document.querySelectorAll('.tabbar button')) {
    btn.addEventListener('click', () => showPage(btn.dataset.page));
  }

  // แตะ = โหลด, แตะค้าง = บันทึกขึ้นชีต (กันกดพลาดทับข้อมูลกิลด์)
  let holdTimer = null;
  const reload = $('reload');
  const startHold = () => { holdTimer = setTimeout(() => { holdTimer = null; saveToServer(); }, 700); };
  const endHold = () => { if (holdTimer) { clearTimeout(holdTimer); holdTimer = null; loadFromServer(); } };
  reload.addEventListener('pointerdown', startHold);
  reload.addEventListener('pointerup', endHold);
  reload.addEventListener('pointerleave', () => { clearTimeout(holdTimer); holdTimer = null; });

  renderAll();
  if (!state.items.length) loadFromServer();

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch(() => {});
  }
}

init();
