// ตรรกะคำนวณ — แปลงมาจาก game_data.py ให้ได้ผลเหมือนกันเป๊ะ
// ตัวเลขทุกตัวอยู่ใน data.js ซึ่งสร้างจากไฟล์ Python อัตโนมัติ
import {
  GRADES, UPGRADE_RED, INHERIT_SAME, INHERIT_HIGHER, HIGHER_RESULT_LEVEL,
  LADDERS, BLUE_LADDER, MIN_START_LEVEL, MAX_LEVEL, MIN_INHERIT_LEVEL,
  HIGHER_TARGET_OFFSET, INHERIT_NONE, INHERIT_MODE_SAME, INHERIT_MODE_HIGHER,
} from './data.js';

/** ตัวเลือกไม่ถูกต้องหรือไม่มีข้อมูลพอ — ข้อความไทยพร้อมแสดงให้ผู้ใช้ */
export class CalcError extends Error {}

function checkGrade(index) {
  if (!(index >= 0 && index < GRADES.length)) throw new CalcError('เกรดไม่ถูกต้อง');
}

function checkLevelRange(start, end) {
  for (const [name, lv] of [['ระดับ', start], ['ถึง', end]]) {
    if (!(lv >= MIN_START_LEVEL && lv <= MAX_LEVEL)) {
      throw new CalcError(`${name} ต้องอยู่ระหว่าง +${MIN_START_LEVEL} ถึง +${MAX_LEVEL} (ได้ ${lv})`);
    }
  }
  if (start > end) {
    throw new CalcError(`ระดับเริ่มต้น (+${start}) ต้องไม่มากกว่าระดับปลายทาง (+${end})`);
  }
}

/**
 * ชิ้นส่วนที่ต้องใช้เพื่อตีจาก +start ไป +end
 * UPGRADE_RED[lv] คือค่าที่ใช้ "ไปถึง" +lv ระดับต้นทางจึงไม่ต้องจ่ายซ้ำ
 */
export function upgradePieces(start, end, gradeIndex) {
  checkLevelRange(start, end);
  checkGrade(gradeIndex);
  let total = 0;
  for (let lv = start + 1; lv <= end; lv += 1) total += UPGRADE_RED[lv][gradeIndex];
  return total;
}

/** ค่าสืบทอด (ทอง) ที่ระดับ +level — คืน 0 เมื่อไม่สืบทอด */
export function inheritCost(mode, level, gradeIndex, targetIndex) {
  if (mode === INHERIT_NONE) return 0;
  if (mode !== INHERIT_MODE_SAME && mode !== INHERIT_MODE_HIGHER) {
    throw new CalcError(`โหมดสืบทอดไม่ถูกต้อง: ${mode}`);
  }
  checkGrade(gradeIndex);
  checkGrade(targetIndex);

  if (level < MIN_INHERIT_LEVEL) {
    throw new CalcError(
      `ไม่มีข้อมูลค่าสืบทอดต่ำกว่า +${MIN_INHERIT_LEVEL} (เลือก 'ถึง' ตั้งแต่ ` +
      `+${MIN_INHERIT_LEVEL} ขึ้นไป หรือเลือก '${INHERIT_NONE}')`);
  }

  if (mode === INHERIT_MODE_SAME) {
    // "ระดับเดียวกัน" เกรดปลายทางเท่ากับเกรดต้นทางเสมอ
    if (targetIndex !== gradeIndex) {
      throw new CalcError(
        `โหมด '${INHERIT_MODE_SAME}' เกรดเป้าหมายต้องเป็น '${GRADES[gradeIndex]}' เท่ากับเกรดไอเทม`);
    }
    return INHERIT_SAME[level][gradeIndex];
  }

  if (gradeIndex >= GRADES.length - 1) {
    throw new CalcError(`'${GRADES[gradeIndex]}' เป็นเกรดสูงสุดแล้ว ไม่มีเกรดที่สูงกว่าให้สืบทอด`);
  }
  if (targetIndex <= gradeIndex) {
    throw new CalcError(`โหมด '${INHERIT_MODE_HIGHER}' เกรดเป้าหมายต้องสูงกว่า '${GRADES[gradeIndex]}'`);
  }

  const column = targetIndex - HIGHER_TARGET_OFFSET;
  const row = INHERIT_HIGHER[level];
  if (!(column >= 0 && column < row.length)) {
    throw new CalcError(
      `ไม่มีข้อมูลค่าสืบทอดแบบ '${INHERIT_MODE_HIGHER}' สำหรับเกรดเป้าหมาย '${GRADES[targetIndex]}'`);
  }
  return row[column];
}

/** หลอมชิ้นส่วนเป็นก้อน คืน [จำนวนก้อนเต็ม, เศษที่เหลือ] */
export function melt(pieces, ratio) {
  if (pieces <= 0) return [0, 0];
  return [Math.floor(pieces / ratio), pieces % ratio];
}

/** มูลค่าของชิ้นส่วนทั้งหมด คิดตามสัดส่วน ไม่ปัดขึ้นและไม่ปัดทิ้ง */
export function piecesValue(pieces, unitPrice, ratio) {
  if (pieces <= 0 || unitPrice <= 0) return 0;
  return (pieces / ratio) * unitPrice;
}

export function ladder(line) {
  const rows = LADDERS[line];
  if (!rows) throw new CalcError(`ไม่รู้จักสายวัสดุ: ${line}`);
  return rows;
}

/** ของชั้น index หนึ่งอัน คิดเป็นชิ้นส่วนชั้นล่างสุดกี่ชิ้น */
export function tierPieces(rows, index) {
  if (!(index >= 0 && index < rows.length)) {
    throw new CalcError(`ไม่มีชั้นที่ ${index} ในบันไดนี้`);
  }
  let total = 1;
  for (let i = 1; i <= index; i += 1) total *= rows[i].per;
  return total;
}

export function tierScale(rows) {
  return rows.map((_, i) => tierPieces(rows, i));
}

/** รวมของทุกชั้นเป็นจำนวนชิ้นส่วนทั้งหมด */
export function toPieces(rows, counts) {
  const scale = tierScale(rows);
  let total = 0;
  counts.forEach((amount, i) => {
    if (i < scale.length) total += Math.max(0, Math.trunc(amount || 0)) * scale[i];
  });
  return total;
}

/** แยกชิ้นส่วนออกเป็นของแต่ละชั้น ไล่จากชั้นสูงสุดลงมา */
export function splitDown(rows, pieces) {
  const out = new Array(rows.length).fill(0);
  if (pieces <= 0) return out;
  let left = Math.trunc(pieces);
  for (let i = rows.length - 1; i >= 0; i -= 1) {
    const worth = tierPieces(rows, i);
    out[i] = Math.floor(left / worth);
    left -= out[i] * worth;
  }
  return out;
}

/**
 * โอกาสตีบวกสำเร็จเป็น % จากจำนวนชิ้นส่วนที่ใส่
 * ค่าใน UPGRADE_RED คือจำนวนที่ทำให้เต็ม 100% ใส่เกินไม่ได้อะไรเพิ่ม
 */
export function successChance(pieces, needed) {
  if (needed <= 0) return 100;
  if (pieces <= 0) return 0;
  return Math.min(100, (pieces / needed) * 100);
}

/**
 * แผนไต่เกรด — สืบทอดข้ามเกรดได้ทีละเกรด ระดับร่วงทุกครั้ง
 * ถ้าร่วงต่ำกว่า +10 ต้องตีขึ้นมาก่อนถึงสืบต่อได้
 */
export function upgradePlan(startGrade, startLevel, targetGrade, targetLevel) {
  checkGrade(startGrade);
  checkGrade(targetGrade);
  for (const [name, lv] of [['ระดับปัจจุบัน', startLevel], ['ระดับเป้าหมาย', targetLevel]]) {
    if (!(lv >= MIN_START_LEVEL && lv <= MAX_LEVEL)) {
      throw new CalcError(`${name} ต้องอยู่ระหว่าง +${MIN_START_LEVEL} ถึง +${MAX_LEVEL}`);
    }
  }
  if (targetGrade < startGrade) {
    throw new CalcError('เกรดเป้าหมายต่ำกว่าเกรดปัจจุบัน สืบทอดย้อนลงไม่ได้');
  }

  const steps = [];
  let pieces = 0;
  let gold = 0;
  let grade = startGrade;
  let level = startLevel;

  while (grade < targetGrade) {
    if (level < MIN_INHERIT_LEVEL) {
      // ยังสืบต่อไม่ได้ ต้องตีขึ้นไปให้ถึงระดับต่ำสุดที่ตารางสืบทอดรองรับ
      const need = upgradePieces(level, MIN_INHERIT_LEVEL, grade);
      pieces += need;
      steps.push({ kind: 'upgrade', grade, from: level, to: MIN_INHERIT_LEVEL, pieces: need });
      level = MIN_INHERIT_LEVEL;
    }
    const next = grade + 1;
    const cost = inheritCost(INHERIT_MODE_HIGHER, level, grade, next);
    const after = HIGHER_RESULT_LEVEL[level];
    gold += cost;
    steps.push({ kind: 'inherit', grade, toGrade: next, from: level, to: after, gold: cost });
    grade = next;
    level = after;
  }

  if (level < targetLevel) {
    const need = upgradePieces(level, targetLevel, grade);
    pieces += need;
    steps.push({ kind: 'upgrade', grade, from: level, to: targetLevel, pieces: need });
    level = targetLevel;
  }

  return {
    steps,
    pieces,
    gold,
    finalLevel: level,
    // สืบมาแล้วได้สูงกว่าที่ขอ ลดระดับลงไม่ได้ จึงต้องบอกตามจริง
    overshoot: level > targetLevel,
  };
}

/** ราคาหินชั้นนั้น = ราคาต่อชิ้นส่วน x จำนวนชิ้นส่วนที่ชั้นนั้นมีค่าเท่า */
export function tierPrice(basePrice, tier) {
  if (!(basePrice > 0)) return 0;
  return (basePrice / BLUE_LADDER[1].per) * tierPieces(BLUE_LADDER, tier);
}
