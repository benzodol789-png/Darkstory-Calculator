// คุยกับ Google Apps Script — คืน { data, error } เสมอ ไม่โยน exception ออกไป
// เพื่อให้ฝั่ง UI จัดการข้อความผิดพลาดเป็นภาษาไทยได้ที่เดียว
import { SERVER_URL, TOKEN } from './config.js';

const TIMEOUT_MS = 30000;

function withParams(extra) {
  const url = new URL(SERVER_URL);
  if (TOKEN) url.searchParams.set('token', TOKEN);
  for (const [k, v] of Object.entries(extra)) url.searchParams.set(k, v);
  return url.toString();
}

async function request(url, options) {
  const control = new AbortController();
  const timer = setTimeout(() => control.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url, { ...options, signal: control.signal });
    const text = await res.text();
    let parsed;
    try {
      parsed = JSON.parse(text);
    } catch {
      // Apps Script ที่ deploy ผิดจะคืนหน้า HTML ล็อกอินแทน JSON
      return { data: null, error: text.trim().startsWith('<')
        ? 'เซิร์ฟเวอร์ตอบกลับเป็นหน้าเว็บ ไม่ใช่ข้อมูล — ตรวจการ deploy ว่าเปิดให้ทุกคนเข้าถึง'
        : 'อ่านคำตอบจากเซิร์ฟเวอร์ไม่ได้' };
    }
    if (parsed && parsed.error && !parsed.success) {
      return { data: null, error: String(parsed.error) };
    }
    if (parsed && parsed.success === false) {
      return { data: null, error: 'เซิร์ฟเวอร์ปฏิเสธคำขอ' };
    }
    return { data: parsed, error: null };
  } catch (err) {
    if (err.name === 'AbortError') return { data: null, error: 'เซิร์ฟเวอร์ตอบช้าเกินไป' };
    return { data: null, error: 'เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ' };
  } finally {
    clearTimeout(timer);
  }
}

/** อ่านชีต คืน { rows, error } โดย rows เป็น array ของ object */
export async function readSheet(sheet) {
  const { data, error } = await request(withParams({ action: 'read', sheet }), { method: 'GET' });
  if (error) return { rows: null, error };
  const rows = data && data.data;
  if (!Array.isArray(rows)) return { rows: null, error: `ชีต '${sheet}' ไม่มีข้อมูลที่อ่านได้` };
  return { rows: rows.filter((r) => r && typeof r === 'object'), error: null };
}

/**
 * เขียนทับชีตทั้งใบ rows เป็น array of array แถวแรกคือชื่อคอลัมน์
 *
 * ต้องส่งเป็น text/plain เท่านั้น ถ้าใส่ application/json เบราว์เซอร์จะยิง
 * preflight OPTIONS ก่อน ซึ่ง Apps Script ไม่ตอบ แล้วคำขอจะถูกบล็อกทั้งหมด
 */
export async function writeSheet(sheet, rows) {
  const body = JSON.stringify({ action: 'update', sheet, rows, token: TOKEN || undefined });
  const { data, error } = await request(withParams({ action: 'update', sheet }), {
    method: 'POST',
    headers: { 'Content-Type': 'text/plain;charset=utf-8' },
    body,
  });
  if (error) return { written: 0, error };
  return { written: (data && data.rows) || 0, error: null };
}
