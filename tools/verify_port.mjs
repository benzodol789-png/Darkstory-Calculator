// เทียบผลลัพธ์ฝั่ง JavaScript กับคำตอบที่ Python คำนวณไว้ ทีละเคส
// รัน:  node tools/verify_port.mjs <path ของ expected.json>
import fs from 'fs';
import * as calc from '../docs/js/calc.js';
import { MATERIAL_BLUE_RATIO, LADDERS } from '../docs/js/data.js';

const expected = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));

let checked = 0;
const failures = [];

/** เรียกแล้วห่อผลให้อยู่ในรูปเดียวกับฝั่ง Python */
function call(fn, ...args) {
  try {
    return ['ok', fn(...args)];
  } catch (err) {
    if (err instanceof calc.CalcError) return ['err'];
    throw err;
  }
}

function compare(label, got, want) {
  checked += 1;
  if (JSON.stringify(got) !== JSON.stringify(want)) {
    if (failures.length < 12) {
      failures.push(`${label}\n      ได้    ${JSON.stringify(got)}\n      ควรได้ ${JSON.stringify(want)}`);
    } else if (failures.length === 12) {
      failures.push('... (ตัดที่ 12 รายการแรก)');
    }
  }
}

for (const [start, end, grade, want] of expected.upgrade_pieces) {
  compare(`upgradePieces(${start}, ${end}, ${grade})`,
    call(calc.upgradePieces, start, end, grade), want);
}

for (const [mode, level, grade, target, want] of expected.inherit_cost) {
  compare(`inheritCost(${mode}, ${level}, ${grade}, ${target})`,
    call(calc.inheritCost, mode, level, grade, target), want);
}

for (const [sg, sl, tg, tl, want] of expected.upgrade_plan) {
  const raw = call(calc.upgradePlan, sg, sl, tg, tl);
  const got = raw[0] === 'ok'
    ? ['ok', {
      pieces: raw[1].pieces,
      gold: raw[1].gold,
      final_level: raw[1].finalLevel,
      overshoot: raw[1].overshoot,
      steps: raw[1].steps.length,
    }]
    : raw;
  compare(`upgradePlan(${sg}, ${sl}, ${tg}, ${tl})`, got, want);
}

for (const [line, n, want] of expected.split_down) {
  compare(`splitDown(${line}, ${n})`, calc.splitDown(LADDERS[line], n), want);
}

for (const [line, n, want] of expected.to_pieces) {
  const rows = LADDERS[line];
  compare(`toPieces(${line}, ${n})`, calc.toPieces(rows, calc.splitDown(rows, n)), want);
}

for (const [have, needed, want] of expected.success_chance) {
  compare(`successChance(${have}, ${needed})`, calc.successChance(have, needed), want);
}

for (const [n, want] of expected.melt) {
  compare(`melt(${n})`, calc.melt(n, MATERIAL_BLUE_RATIO), want);
}

for (const [n, price, want] of expected.pieces_value) {
  compare(`piecesValue(${n}, ${price})`,
    calc.piecesValue(n, price, MATERIAL_BLUE_RATIO), want);
}

console.log(`เทียบทั้งหมด ${checked.toLocaleString()} เคส`);
if (failures.length) {
  console.log(`\n*** ไม่ตรงกัน ${failures.length} จุด:`);
  failures.forEach((f) => console.log('   ' + f));
  process.exit(1);
}
console.log('*** ตรงกับฝั่ง Python ทุกเคส');
