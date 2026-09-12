// ค้นหาชื่อไอเทมแบบเดาให้ — แปลงมาจาก Darkstory_Calculator.py
//
// ตัววัดความคล้ายเป็นอัลกอริทึม Ratcliff/Obershelp ตัวเดียวกับที่
// difflib.SequenceMatcher ของ Python ใช้ แปลงมาทั้งดุ้นแทนที่จะคิดสูตรใหม่
// เพื่อให้ผลการค้นบนเว็บกับบนคอมออกมาเหมือนกันเป๊ะ ไม่ใช่แค่ใกล้เคียง
import { ITEM_CATEGORIES, ITEM_CATEGORY_DEFAULT } from './data.js';

// วรรณยุกต์ ไม้ไต่คู้ การันต์ นิคหิต — ตกหรือใส่เกินบ่อยที่สุด
const THAI_MARKS = Array.from({ length: 8 }, (_, i) => String.fromCharCode(0x0e47 + i)).join('');
const SEARCH_DROP = new Set((THAI_MARKS + ' \t -_.,()[]{}/\'"+*').split(''));

export const SEARCH_MIN_SCORE = 45;
const SEARCH_GUESSES = 5;

export function normSearch(text) {
  return String(text ?? '').toLowerCase().split('')
    .filter((ch) => !SEARCH_DROP.has(ch))
    .join('');
}

/** ช่วงที่ตรงกันยาวที่สุดของ a[alo:ahi] กับ b[blo:bhi] — ตามสูตรของ difflib */
function longestMatch(a, b, b2j, alo, ahi, blo, bhi) {
  let besti = alo;
  let bestj = blo;
  let bestsize = 0;
  let j2len = new Map();

  for (let i = alo; i < ahi; i += 1) {
    const newj2len = new Map();
    for (const j of b2j.get(a[i]) || []) {
      if (j < blo) continue;
      if (j >= bhi) break;
      const k = (j2len.get(j - 1) || 0) + 1;
      newj2len.set(j, k);
      if (k > bestsize) {
        besti = i - k + 1;
        bestj = j - k + 1;
        bestsize = k;
      }
    }
    j2len = newj2len;
  }

  while (besti > alo && bestj > blo && a[besti - 1] === b[bestj - 1]) {
    besti -= 1; bestj -= 1; bestsize += 1;
  }
  while (besti + bestsize < ahi && bestj + bestsize < bhi
         && a[besti + bestsize] === b[bestj + bestsize]) {
    bestsize += 1;
  }
  return [besti, bestj, bestsize];
}

/** สัดส่วนความเหมือน 0..1 เท่ากับ difflib.SequenceMatcher(None, a, b).ratio() */
export function ratio(a, b) {
  if (!a.length && !b.length) return 1;
  const b2j = new Map();
  for (let j = 0; j < b.length; j += 1) {
    if (!b2j.has(b[j])) b2j.set(b[j], []);
    b2j.get(b[j]).push(j);
  }

  let matches = 0;
  const queue = [[0, a.length, 0, b.length]];
  while (queue.length) {
    const [alo, ahi, blo, bhi] = queue.pop();
    const [i, j, k] = longestMatch(a, b, b2j, alo, ahi, blo, bhi);
    if (!k) continue;
    matches += k;
    if (alo < i && blo < j) queue.push([alo, i, blo, j]);
    if (i + k < ahi && j + k < bhi) queue.push([i + k, ahi, j + k, bhi]);
  }
  return (2 * matches) / (a.length + b.length);
}

/** ตัวอักษรของ short โผล่ครบตามลำดับใน longText ไหม — รองรับการพิมพ์ย่อ */
function isSubsequence(short, longText) {
  let at = 0;
  for (const ch of short) {
    at = longText.indexOf(ch, at) + 1;
    if (at === 0) return false;
  }
  return true;
}

/** ความใกล้เคียงของชื่อกับคำค้น 0-100 (0 = ไม่เกี่ยวกันเลย) */
export function matchScore(query, name) {
  const q = normSearch(query);
  const n = normSearch(name);
  if (!q) return 100;
  if (!n) return 0;
  if (q === n) return 100;
  if (n.startsWith(q)) return 96;
  if (n.includes(q)) return 85 + (10 * q.length) / n.length;

  let best = ratio(q, n);
  // เทียบกับทุกช่วงของชื่อที่ยาวเท่าคำค้นด้วย ไม่งั้นชื่อยาวเสียเปรียบ
  if (n.length > q.length) {
    for (let i = 0; i <= n.length - q.length; i += 1) {
      best = Math.max(best, ratio(q, n.slice(i, i + q.length)));
    }
  }
  let score = best * 82;
  if (isSubsequence(q, n)) score = Math.max(score, 62);
  return score;
}

/** คืน [{index, score}] เรียงจากใกล้สุด — index คือตำแหน่งจริงใน items */
export function searchItems(items, query) {
  if (!normSearch(query)) return items.map((_, i) => ({ index: i, score: 100 }));

  const scored = items.map((item, i) => ({ index: i, score: matchScore(query, item.name) }));
  // คะแนนเท่ากันให้เรียงตามรหัสตัวอักษร ไม่ใช่ localeCompare
  // เพราะฝั่ง Python เรียงแบบรหัส ถ้าใช้คนละแบบลำดับผลค้นจะไม่ตรงกัน
  scored.sort((x, y) => {
    if (y.score !== x.score) return y.score - x.score;
    const a = String(items[x.index].name);
    const b = String(items[y.index].name);
    if (a < b) return -1;
    return a > b ? 1 : 0;
  });

  const hits = scored.filter((s) => s.score >= SEARCH_MIN_SCORE);
  if (hits.length) return hits;
  // ไม่มีอะไรเข้าเกณฑ์ — ยังเดาให้ดูว่าน่าจะหมายถึงอันไหน ดีกว่าโชว์ตารางเปล่า
  return scored.slice(0, SEARCH_GUESSES).filter((s) => s.score > 0);
}

/** หมวดของไอเทม — ของเก่าที่ยังไม่มีหมวด ถือเป็น "อื่นๆ" */
export function itemCategory(item) {
  const name = String(item?.category ?? '').trim();
  return ITEM_CATEGORIES.includes(name) ? name : ITEM_CATEGORY_DEFAULT;
}
