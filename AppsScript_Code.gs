/**
 * Darkstory Calculator — ฝั่ง Google Apps Script
 *
 * โค้ดนี้ตรงกับที่ Darkstory_Calculator.py คาดหวังไว้เป๊ะ
 * วิธีติดตั้งอยู่ใน README.md หัวข้อ "ตั้งค่า Google Apps Script"
 *
 * สัญญาที่ตกลงกับ client:
 *   GET  ?action=read&sheet=<ชื่อชีต>&token=<token>
 *        -> {"success":true,"data":[{คอลัมน์: ค่า, ...}, ...]}
 *   POST ?action=update&sheet=<ชื่อชีต>&token=<token>
 *        body: {"action":"update","sheet":"...","rows":[[หัวคอลัมน์...],[ค่า...]],"token":"..."}
 *        -> {"success":true,"rows":<จำนวนแถวที่เขียน>}
 *   ถ้าพลาด -> {"success":false,"error":"<เหตุผล>"}
 */

// ตั้งให้ตรงกับ token ใน darkstory_config.json
// ปล่อยเป็น "" ได้ถ้ายังไม่อยากใช้ แต่แปลว่าใครรู้ลิงก์ก็เขียนทับชีตได้
var TOKEN = "";

// ชีตที่ยอมให้เข้าถึง — กันไม่ให้ใครสุ่มชื่อชีตอื่นในไฟล์เดียวกัน
var ALLOWED_SHEETS = ["currency", "items", "materials"];

// ปฏิเสธการเขียนที่ทำให้จำนวนแถวหายเกินสัดส่วนนี้ (0.5 = หายเกินครึ่ง)
var MAX_SHRINK = 0.5;

// เก็บ backup ไว้กี่ชุดต่อชีต
var KEEP_BACKUPS = 5;


function doGet(e) {
  try {
    var p = (e && e.parameter) || {};
    checkToken(p.token);

    if (p.action !== "read") {
      return fail("action ไม่ถูกต้อง: " + p.action);
    }
    var sheet = getSheet(p.sheet);
    return ok({ data: readRows(sheet) });
  } catch (err) {
    return fail(err.message || String(err));
  }
}


function doPost(e) {
  var lock = LockService.getScriptLock();
  try {
    // กันสองเครื่องเขียนพร้อมกันแล้วข้อมูลตีกัน
    if (!lock.tryLock(20000)) {
      return fail("มีการบันทึกอื่นค้างอยู่ ลองใหม่อีกครั้ง");
    }

    var p = (e && e.parameter) || {};
    var body = {};
    if (e && e.postData && e.postData.contents) {
      try {
        body = JSON.parse(e.postData.contents) || {};
      } catch (parseErr) {
        return fail("body ไม่ใช่ JSON ที่อ่านได้");
      }
    }

    // client ส่งมาทั้งใน query และ body — อ่านจากที่ไหนก็ได้
    var action = body.action || p.action;
    var name = body.sheet || p.sheet;
    var token = body.token || p.token;
    var rows = body.rows;

    checkToken(token);

    if (action !== "update") {
      return fail("action ไม่ถูกต้อง: " + action);
    }
    if (!rows || !rows.length) {
      return fail("ไม่มีข้อมูลให้บันทึก");
    }
    if (rows.length < 2) {
      return fail("มีแต่หัวคอลัมน์ ไม่มีข้อมูล — ปฏิเสธเพื่อกันข้อมูลหาย");
    }

    var sheet = getSheet(name);
    var before = Math.max(sheet.getLastRow() - 1, 0);   // ไม่นับหัวคอลัมน์
    var after = rows.length - 1;

    if (before > 0 && after < before * MAX_SHRINK) {
      return fail(
        "ปฏิเสธการบันทึก: จำนวนแถวจะลดจาก " + before + " เหลือ " + after +
        " (หายเกิน " + Math.round((1 - MAX_SHRINK) * 100) + "%) " +
        "ถ้าตั้งใจลบจริง ให้แก้ในชีตโดยตรง");
    }

    backup(sheet);
    writeRows(sheet, rows);
    return ok({ rows: after });
  } catch (err) {
    return fail(err.message || String(err));
  } finally {
    try { lock.releaseLock(); } catch (ignore) {}
  }
}


/* ---------- ตัวช่วย ---------- */

function checkToken(given) {
  if (TOKEN && String(given || "") !== TOKEN) {
    throw new Error("token ไม่ถูกต้อง");
  }
}


function getSheet(name) {
  name = String(name || "");
  if (ALLOWED_SHEETS.indexOf(name) === -1) {
    throw new Error("ไม่อนุญาตให้เข้าถึงชีต '" + name + "'");
  }
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(name);
  if (!sheet) {
    throw new Error("ไม่พบชีตชื่อ '" + name + "'");
  }
  return sheet;
}


/**
 * แปลงตารางเป็น array ของ object โดยใช้แถวแรกเป็นชื่อคอลัมน์
 * client ต้องการรูปแบบนี้ ถ้าคืน getValues() ดิบไปจะอ่านไม่ออก
 */
function readRows(sheet) {
  var values = sheet.getDataRange().getValues();
  if (values.length < 2) {
    return [];
  }
  var headers = values[0].map(function (h) { return String(h).trim(); });
  var out = [];

  for (var r = 1; r < values.length; r++) {
    var row = values[r];
    var blank = row.every(function (c) { return c === "" || c === null; });
    if (blank) {
      continue;
    }
    var obj = {};
    for (var c = 0; c < headers.length; c++) {
      if (headers[c]) {
        obj[headers[c]] = row[c] === null ? "" : row[c];
      }
    }
    out.push(obj);
  }
  return out;
}


function writeRows(sheet, rows) {
  var width = 0;
  rows.forEach(function (r) { width = Math.max(width, r.length); });

  // เติมช่องว่างให้ทุกแถวยาวเท่ากัน ไม่งั้น setValues จะ error
  var padded = rows.map(function (r) {
    var copy = r.slice();
    while (copy.length < width) {
      copy.push("");
    }
    return copy;
  });

  sheet.clearContents();
  sheet.getRange(1, 1, padded.length, width).setValues(padded);
  SpreadsheetApp.flush();
}


/** copy ชีตไปเก็บไว้ก่อนเขียนทับ แล้วลบชุดเก่าที่เกินโควตา */
function backup(sheet) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var prefix = "_bak_" + sheet.getName() + "_";
  var stamp = Utilities.formatDate(new Date(), ss.getSpreadsheetTimeZone(),
                                   "yyyyMMdd_HHmmss");

  sheet.copyTo(ss).setName(prefix + stamp);

  var old = ss.getSheets()
    .filter(function (s) { return s.getName().indexOf(prefix) === 0; })
    .sort(function (a, b) { return a.getName() < b.getName() ? 1 : -1; });

  for (var i = KEEP_BACKUPS; i < old.length; i++) {
    ss.deleteSheet(old[i]);
  }
}


function ok(extra) {
  var payload = { success: true };
  for (var k in extra) {
    payload[k] = extra[k];
  }
  return json(payload);
}


function fail(message) {
  return json({ success: false, error: String(message) });
}


function json(payload) {
  return ContentService
    .createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}


/**
 * รันจากใน editor เพื่อสร้างชีตเปล่าพร้อมหัวคอลัมน์ที่ถูกต้อง
 * (เมนู Run > setupSheets)
 */
function setupSheets() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var spec = {
    currency: [["key", "value"], ["rate_gold_to_thb", "0.85"]],
    items: [["name", "price_gold"]],
    materials: [["name", "price_gold_per_unit"],
                ["พลอยสีแดงเข้ม", 0],
                ["หินดั้งเดิม", 0]]
  };

  Object.keys(spec).forEach(function (name) {
    var sheet = ss.getSheetByName(name) || ss.insertSheet(name);
    if (sheet.getLastRow() === 0) {
      var rows = spec[name];
      sheet.getRange(1, 1, rows.length, rows[0].length).setValues(rows);
      sheet.getRange(1, 1, 1, rows[0].length).setFontWeight("bold");
      sheet.setFrozenRows(1);
    }
  });
  SpreadsheetApp.getUi().alert("สร้างชีตครบแล้ว: " + Object.keys(spec).join(", "));
}
