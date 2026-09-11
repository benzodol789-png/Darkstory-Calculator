# -*- coding: utf-8 -*-
"""Darkstory Calculator — เครื่องคิดเลขต้นทุนไอเทมเกม Darkstory

ตารางข้อมูลเกมและฟังก์ชันคำนวณอยู่ใน game_data.py
ลิงก์ Google Apps Script อยู่ใน darkstory_config.json (ไม่ฝังไว้ในโค้ด)

ใช้เฉพาะ standard library — ไม่ต้องติดตั้งอะไรเพิ่ม
"""

import difflib
import json
import logging
import logging.handlers
import os
import sys
import threading
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
from tkinter import messagebox, ttk

import game_data as gd
import theme
from game_data import (
    GRADES,
    INHERIT_MODES,
    INHERIT_NONE,
    MATERIAL_BLUE_RATIO,
    MATERIAL_RED_RATIO,
    MAX_LEVEL,
    MIN_LEVEL,
    CalcError,
)

CURRENT_VERSION = "1.1.0"
DEFAULT_RATE = 0.85

# timeout ต่อการเชื่อมต่อหนึ่งครั้ง (วินาที) — เป็น socket timeout ไม่ใช่เพดานรวม
NET_TIMEOUT = 15


def app_dir():
    """โฟลเดอร์ของแอป — รองรับทั้งรันจาก .py และ build เป็น .exe ด้วย PyInstaller"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(name):
    """หาไฟล์ที่ถูกฝังมากับ .exe (PyInstaller แตกไว้ที่ sys._MEIPASS)

    ตอนรันจาก .py จะได้พาธข้างไฟล์ตามปกติ
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, name)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)


APP_DIR = app_dir()
CONFIG_PATH = os.path.join(APP_DIR, "darkstory_config.json")
LOCAL_PATH = os.path.join(APP_DIR, "darkstory_local.json")
LOG_PATH = os.path.join(APP_DIR, "darkstory.log")

log = logging.getLogger("darkstory")


def setup_logging():
    """เขียน log ลงไฟล์ข้างแอป — print() มองไม่เห็นเมื่อ build แบบ --windowed"""
    log.setLevel(logging.INFO)
    try:
        handler = logging.handlers.RotatingFileHandler(
            LOG_PATH, maxBytes=512 * 1024, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(message)s"))
        log.addHandler(handler)
    except OSError:
        # เขียนไฟล์ไม่ได้ (โฟลเดอร์อ่านอย่างเดียว) — ไม่ให้ล้มทั้งแอป
        log.addHandler(logging.NullHandler())


# ---------------------------------------------------------------------------
# แปลงตัวเลขจากช่องกรอก
# ---------------------------------------------------------------------------

def parse_num(text, default=None):
    """แปลงข้อความเป็น float รองรับ comma คั่นหลัก คืน default เมื่อแปลงไม่ได้

    ต้องใช้ helper ตัวนี้ทุกจุด เพราะโปรแกรมเขียนตัวเลขกลับเข้าช่องด้วย
    format "{:,.1f}" แล้ว float() เปล่าๆ อ่าน "4,250.0" ไม่ออก
    """
    if text is None:
        return default
    s = str(text).replace(",", "").strip()
    if not s:
        return default
    try:
        value = float(s)
    except ValueError:
        return default
    if value != value or value in (float("inf"), float("-inf")):
        return default
    return value


def parse_count(text, default=None):
    """แปลงเป็นจำนวนเต็มไม่ติดลบ (จำนวนชิ้นส่วน)"""
    value = parse_num(text, None)
    if value is None or value < 0:
        return default
    return int(value)


def to_num(value, default=0.0):
    """แปลงค่าที่มาจาก Google Sheet — เซลล์ว่างมาเป็น "" ไม่ใช่ key ที่หายไป"""
    return parse_num(value, default)


def money(value):
    """จัดรูปจำนวนเงิน — ทศนิยมหลักเดียวพอ ตัวเลขในเกมเป็นหลักล้าน อ่านง่ายกว่า"""
    return "{:,.1f}".format(value)


# ---------------------------------------------------------------------------
# ค้นหาชื่อไอเทมแบบเดาให้
#
# คนที่มาค้นมักไม่ใช่คนที่พิมพ์ชื่อเข้าไป จึงเรียกของชิ้นเดียวกันคนละแบบ
# พิมพ์สั้นบ้าง ตกวรรณยุกต์บ้าง สลับตัวบ้าง — ต้องเดาให้ออกทุกแบบ
# ---------------------------------------------------------------------------

# วรรณยุกต์ ไม้ไต่คู้ การันต์ นิคหิต — ตกหรือใส่เกินบ่อยที่สุด
# ตัดทิ้งก่อนเทียบ "ราชันย์" กับ "ราชัน" จะได้นับเป็นคำเดียวกัน
THAI_MARKS = "".join(chr(code) for code in range(0x0E47, 0x0E4F))
SEARCH_DROP = THAI_MARKS + " 	 -_.,()[]{}/\'\"+*"
SEARCH_MIN_SCORE = 45.0     # ต่ำกว่านี้ถือว่าคนละคำกัน
SEARCH_GUESSES = 5          # ถ้าไม่มีอะไรเข้าเกณฑ์ ยังเดาให้ดูเท่านี้


def norm_search(text):
    """ตัดสิ่งที่คนพิมพ์ไม่ตรงกันบ่อยออก ให้เทียบกันได้แม้พิมพ์ไม่เป๊ะ"""
    return "".join(ch for ch in str(text).lower() if ch not in SEARCH_DROP)


def _is_subsequence(short, long_text):
    """ตัวอักษรของ short โผล่ครบตามลำดับใน long_text ไหม — รองรับการพิมพ์ย่อ"""
    stream = iter(long_text)
    return all(ch in stream for ch in short)


def match_score(query, name):
    """ความใกล้เคียงของชื่อกับคำค้น 0-100 (0 = ไม่เกี่ยวกันเลย)"""
    q = norm_search(query)
    name_norm = norm_search(name)
    if not q:
        return 100.0
    if not name_norm:
        return 0.0
    if q == name_norm:
        return 100.0
    if name_norm.startswith(q):
        return 96.0
    if q in name_norm:
        # คำค้นกินเนื้อชื่อมากเท่าไหร่ ยิ่งน่าจะหมายถึงอันนี้
        return 85.0 + 10.0 * len(q) / len(name_norm)

    best = difflib.SequenceMatcher(None, q, name_norm).ratio()
    # เทียบกับทุกช่วงของชื่อที่ยาวเท่าคำค้นด้วย ไม่งั้นชื่อยาวเสียเปรียบ
    # เช่นค้น "ราชัน" ใน "ถุงมือราชันย์แห่งรัตติกาล" ratio เต็มสายจะต่ำมาก
    if len(name_norm) > len(q):
        for i in range(len(name_norm) - len(q) + 1):
            window = name_norm[i:i + len(q)]
            best = max(best, difflib.SequenceMatcher(None, q, window).ratio())
    score = best * 82.0

    if _is_subsequence(q, name_norm):
        score = max(score, 62.0)
    return score


def search_items(items, query):
    """คืน [(ตำแหน่งจริงใน items, คะแนน)] เรียงจากใกล้สุดไปไกลสุด

    ต้องคืน "ตำแหน่งจริง" ไม่ใช่ลำดับที่แสดง เพราะพอตารางถูกกรองแล้ว
    ลำดับแถวจะไม่ตรงกับ items อีก การแก้ราคา/ลบจะไปโดนตัวผิด
    """
    if not norm_search(query):
        return [(i, 100.0) for i in range(len(items))]

    scored = [(i, match_score(query, item["name"])) for i, item in enumerate(items)]
    scored.sort(key=lambda pair: (-pair[1], items[pair[0]]["name"]))

    hits = [pair for pair in scored if pair[1] >= SEARCH_MIN_SCORE]
    if hits:
        return hits
    # ไม่มีอะไรเข้าเกณฑ์ — ยังเดาให้ดูว่าน่าจะหมายถึงอันไหน ดีกว่าโชว์ตารางเปล่า
    return [pair for pair in scored[:SEARCH_GUESSES] if pair[1] > 0]


# ---------------------------------------------------------------------------
# Config / local cache
# ---------------------------------------------------------------------------

def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else default
    except FileNotFoundError:
        return default
    except (OSError, ValueError):
        log.exception("อ่าน %s ไม่สำเร็จ", path)
        return default


def write_json(path, data):
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except OSError:
        log.exception("เขียน %s ไม่สำเร็จ", path)
        return False


def normalize_url(raw):
    """ตัด fragment (#...) และ ? ท้ายทิ้ง

    ถ้า copy ลิงก์มาแล้วติด '#' ท้าย การต่อ query จะกลายเป็น '/exec#?action=...'
    ซึ่งทุกอย่างหลัง '#' ไม่ถูกส่งไปเซิร์ฟเวอร์เลย และไม่มี error ให้เห็น
    """
    if not raw:
        return ""
    url = urllib.parse.urldefrag(str(raw).strip())[0]
    return url.rstrip("?&")


def build_url(base, params):
    """ต่อ query string เข้ากับลิงก์ โดยไม่ทำลาย query ที่ลิงก์มีอยู่แล้ว

    การต่อ base + "?" + urlencode(...) ตรงๆ จะพังทันทีถ้าลิงก์มี '?' อยู่แล้ว
    เพราะจะได้ '...?a=1?action=read' ซึ่ง parse ออกมาเป็นพารามิเตอร์เดียว
    """
    parts = urllib.parse.urlsplit(base)
    merged = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    merged += list(params.items())
    return urllib.parse.urlunsplit((
        parts.scheme, parts.netloc, parts.path,
        urllib.parse.urlencode(merged), "",
    ))


def load_config():
    cfg = read_json(CONFIG_PATH, {})
    return {
        "server_url": normalize_url(cfg.get("server_url", "")),
        "token": str(cfg.get("token", "") or ""),
    }


# ---------------------------------------------------------------------------
# ชั้นเชื่อมต่อเซิร์ฟเวอร์ — คืน (data, error_text) เสมอ ไม่กลืน error เงียบๆ
# ---------------------------------------------------------------------------

class Api:
    def __init__(self, config):
        self.url = normalize_url(config.get("server_url", ""))
        self.token = str(config.get("token", "") or "")

    @property
    def configured(self):
        return bool(self.url)

    def _params(self, **extra):
        params = {}
        if self.token:
            params["token"] = self.token
        params.update({k: v for k, v in extra.items() if v is not None})
        return params

    def _request(self, params, body=None):
        if not self.configured:
            return None, ("ยังไม่ได้ตั้งค่าลิงก์เซิร์ฟเวอร์\n"
                          "ใส่ server_url ในไฟล์ darkstory_config.json")

        url = build_url(self.url, params)
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=NET_TIMEOUT) as resp:
                raw = resp.read().decode("utf-8", "replace")
                ctype = resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            log.error("HTTP %s จาก %s", exc.code, params.get("sheet"))
            return None, "เซิร์ฟเวอร์ตอบกลับ HTTP %s" % exc.code
        except urllib.error.URLError as exc:
            log.exception("เชื่อมต่อไม่สำเร็จ")
            return None, "เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ: %s" % exc.reason
        except OSError as exc:
            log.exception("เชื่อมต่อไม่สำเร็จ")
            return None, "เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ: %s" % exc

        try:
            parsed = json.loads(raw)
        except ValueError:
            log.error("คำตอบไม่ใช่ JSON (Content-Type: %s): %.200s", ctype, raw)
            if "html" in ctype.lower() or raw.lstrip().startswith("<"):
                return None, ("เซิร์ฟเวอร์ตอบกลับเป็นหน้าเว็บ ไม่ใช่ข้อมูล\n"
                              "ตรวจสอบว่า deploy Apps Script เป็น Web App "
                              "และตั้งสิทธิ์ให้เข้าถึงได้")
            return None, "คำตอบจากเซิร์ฟเวอร์ไม่ใช่ JSON ที่อ่านได้"

        # รองรับทั้ง {"success":..,"data":[..]} และการคืน list มาตรงๆ
        if isinstance(parsed, list):
            parsed = {"success": True, "data": parsed}
        if not isinstance(parsed, dict):
            return None, "รูปแบบคำตอบจากเซิร์ฟเวอร์ไม่ถูกต้อง"
        # บาง backend คืนแค่ {"error": "..."} โดยไม่มีคีย์ success
        # ถ้าดูแค่ success จะกลายเป็น "สำเร็จ" แล้วไปพังตอนหา data ทีหลัง
        # ทำให้ผู้ใช้เห็นข้อความกว้างๆ แทนสาเหตุจริงที่เซิร์ฟเวอร์บอกมา
        if parsed.get("error") and not parsed.get("success"):
            return None, str(parsed["error"])
        if not parsed.get("success", True):
            return None, "เซิร์ฟเวอร์แจ้งว่าทำรายการไม่สำเร็จ"
        return parsed, None

    def read(self, sheet):
        """อ่านชีต คืน (rows, error) โดย rows เป็น list ของ dict"""
        data, err = self._request(self._params(action="read", sheet=sheet))
        if err:
            return None, err
        rows = data.get("data")
        if not isinstance(rows, list):
            return None, "ชีต '%s' ไม่มีข้อมูลในรูปแบบที่อ่านได้" % sheet
        usable = [r for r in rows if isinstance(r, dict)]
        if rows and not usable:
            # เซิร์ฟเวอร์คืน array-of-arrays (getValues ดิบ) แทน array ของ object
            # ถ้าปล่อยผ่านจะกลายเป็น "โหลดสำเร็จ 0 แถว" ซึ่งอ่านเหมือนชีตว่าง
            log.error("ชีต %s คืนข้อมูลเป็น %s ไม่ใช่ object", sheet, type(rows[0]).__name__)
            return None, ("ชีต '%s' คืนข้อมูลเป็นตารางดิบ ไม่ใช่รายการที่มีชื่อคอลัมน์\n"
                          "ฝั่ง Apps Script ต้องแปลงแถวแรกเป็นชื่อคอลัมน์ก่อนส่งกลับ" % sheet)
        if len(usable) < len(rows):
            log.warning("ชีต %s ข้ามแถวที่อ่านไม่ได้ %d แถว", sheet, len(rows) - len(usable))
        return usable, None

    def update(self, sheet, rows):
        """เขียนทับชีต คืน (True, None) หรือ (False, error)

        ส่ง action/sheet ไปทั้งใน query string และใน body เพราะ Apps Script
        อาจอ่านจาก e.parameter หรือ e.postData.contents ก็ได้ และการ redirect
        302 ของ Apps Script อาจทำให้ body หายระหว่างทาง
        """
        body = {"action": "update", "sheet": sheet, "rows": rows}
        if self.token:
            body["token"] = self.token
        data, err = self._request(self._params(action="update", sheet=sheet), body)
        return (data is not None and not err), err


# ---------------------------------------------------------------------------
# แอป
# ---------------------------------------------------------------------------

class PriceDialog:
    """หน้าต่างเล็กสำหรับแก้ราคาไอเทมที่เลือก

    ใช้แล้วอ่านผลจาก .result — เป็นราคาใหม่ (float) หรือ None ถ้ายกเลิก
    """

    def __init__(self, parent, item, rate):
        self.result = None
        self.rate = rate

        self.win = win = tk.Toplevel(parent)
        win.title("แก้ราคา")
        win.resizable(False, False)
        win.transient(parent)

        body = ttk.Frame(win, padding=15)
        body.pack(fill=tk.BOTH, expand=True)

        ttk.Label(body, text=item["name"], font="ds.heading").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 2))
        ttk.Label(body, foreground=theme.PALETTE["text_dim"],
                  text="ราคาเดิม %s ทอง = %s บาท"
                       % (money(item["price"]), money(item["price"] * rate))).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 12))

        ttk.Label(body, text="ราคาใหม่ (ทอง):").grid(row=2, column=0, sticky="e", padx=(0, 8))
        self.entry = ttk.Entry(body, width=18)
        self.entry.insert(0, ("%g" % item["price"]))
        self.entry.grid(row=2, column=1, sticky="w")
        self.entry.bind("<KeyRelease>", self._preview)

        self.preview = ttk.Label(body, text="")
        self.preview.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))

        buttons = ttk.Frame(body)
        buttons.grid(row=4, column=0, columnspan=2, pady=(16, 0), sticky="e")
        ttk.Button(buttons, text="บันทึก", command=self._ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="ยกเลิก", command=self._cancel).pack(side=tk.LEFT)

        win.bind("<Return>", lambda e: self._ok())
        win.bind("<Escape>", lambda e: self._cancel())
        win.protocol("WM_DELETE_WINDOW", self._cancel)

        self._preview()
        self.entry.focus_set()
        self.entry.select_range(0, tk.END)
        self._center(parent)

        win.grab_set()          # โมดัล — กันไม่ให้หน้าต่างนี้หายไปอยู่หลังหน้าต่างหลัก
        parent.wait_window(win)

    def _center(self, parent):
        self.win.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.win.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.win.winfo_height()) // 3
        self.win.geometry("+%d+%d" % (max(x, 0), max(y, 0)))

    def _value(self):
        value = parse_num(self.entry.get(), None)
        return value if value is not None and value >= 0 else None

    def _preview(self, event=None):
        value = self._value()
        if value is None:
            self.preview.config(text="ราคาต้องเป็นตัวเลขไม่ติดลบ", foreground=theme.PALETTE["danger"])
        else:
            self.preview.config(text="= %s บาท" % money(value * self.rate), foreground="")

    def _ok(self):
        value = self._value()
        if value is None:
            self._preview()
            self.entry.focus_set()
            return
        self.result = value
        self.win.destroy()

    def _cancel(self):
        self.result = None
        self.win.destroy()


class DarkstoryApp:
    def __init__(self, root, config):
        self.root = root
        self.api = Api(config)

        self.rate_gold_thb = DEFAULT_RATE
        self.items = []
        # ราคาหินสายน้ำเงินแยกตามชั้นในบันได {ชั้น: ทองต่อหน่วย} — ชั้น 0 คือชิ้นส่วน
        # ซึ่งซื้อขายไม่ได้ จึงไม่มีราคา เก็บเฉพาะชั้นที่ tradeable
        self.mat_prices = {}

        self.items_dirty = False        # มีไอเทมที่ยังไม่ได้บันทึกขึ้นเซิร์ฟเวอร์
        self.loaded_from_server = False  # กันไม่ให้เขียนทับชีตก่อนเคยโหลด
        self.busy = False

        self._load_local()

        root.title("Darkstory Calculator v%s" % CURRENT_VERSION)
        root.geometry("620x880")
        self._set_icon()

        # ธีม: ฟอนต์ที่ปรับขนาดได้ -> สไตล์ ttk -> หน้าต่างมุมโค้ง -> ค่อยสร้าง widget
        self.fonts = theme.Fonts(root)
        self.style = theme.apply_theme(root, self.fonts)
        self.chrome = theme.RoundedWindow(root)

        self._build_ui()
        self.refresh_all()

        root.protocol("WM_DELETE_WINDOW", self.on_close)

        if not self.api.configured:
            self.set_status("ยังไม่ได้ตั้งค่าลิงก์เซิร์ฟเวอร์ใน darkstory_config.json", warn=True)

    # ราคา "หินดั้งเดิม" (บันไดชั้น 1) — คงชื่อเดิมไว้เพราะแท็บตีบวก การบันทึก
    # และไฟล์ในเครื่องอ้างถึงอยู่หลายจุด เปลี่ยนเป็น property จึงไม่ต้องแก้ตามทั้งไฟล์
    @property
    def mat_blue_price(self):
        return self.mat_prices.get(1, 0.0)

    @mat_blue_price.setter
    def mat_blue_price(self, value):
        self.mat_prices[1] = float(value or 0.0)

    def mat_price(self, tier):
        return self.mat_prices.get(tier, 0.0)

    # ---------------- หน้าตา ----------------

    def _set_icon(self):
        """หาไอคอนจากในตัว .exe ก่อน แล้วค่อยมองข้างไฟล์และโฟลเดอร์แม่"""
        for name in ("Red.ico", "Blue.ico"):
            candidates = [resource_path(name),
                          os.path.join(APP_DIR, name),
                          os.path.join(os.path.dirname(APP_DIR), name)]
            for path in candidates:
                if os.path.exists(path):
                    try:
                        self.root.iconbitmap(path)
                        return
                    except tk.TclError:
                        log.warning("ใช้ไอคอน %s ไม่ได้", path)

    def _build_ui(self):
        """โครงหน้าต่าง: พื้นหลังภาพเกม -> แถบหัว -> เนื้อหา -> แถบสถานะ

        ทุกชิ้นวางด้วย place() บน canvas พื้นหลัง เพื่อให้ภาพโผล่ตรงช่องว่างรอบๆ
        ส่วนข้างในแต่ละแท็บยังใช้ grid เหมือนเดิม จึงไม่มีปัญหาเนื้อหาล้น
        """
        root = self.root
        self.backdrop = theme.Backdrop(root, theme.asset("Darkstory*BG1*.jpg"),
                                       dim=0.62, blur=3)
        canvas = self.backdrop.canvas
        canvas.pack(fill=tk.BOTH, expand=True)

        self._build_titlebar(canvas)

        self.body = ttk.Frame(canvas, style="TFrame")

        toolbar = ttk.Frame(self.body, style="TFrame")
        toolbar.pack(fill=tk.X, pady=(0, 10))
        self.load_btn = ttk.Button(toolbar, text="🔄  โหลดข้อมูล",
                                   style="Gold.TButton", command=self.load_from_server)
        self.load_btn.pack(side=tk.RIGHT)

        nb = ttk.Notebook(self.body)
        nb.pack(fill=tk.BOTH, expand=True)
        self.nb = nb
        self._build_calc_tab(nb)
        self._build_split_tab(nb)
        self._build_materials_tab(nb)
        self._build_items_tab(nb)
        self._build_currency_tab(nb)

        self.status = ttk.Label(canvas, text="พร้อมใช้งาน", anchor="w",
                                style="Status.TLabel")

        canvas.bind("<Configure>", self._on_shell_resize)

    def _build_titlebar(self, canvas):
        """หัวโปรแกรม: ภาพ BG2 เต็มความกว้าง + ตัวหนังสือวาดทับบน canvas

        ตัวหนังสือต้องเป็น canvas item ไม่ใช่ Label เพราะ Label มีพื้นหลังทึบ
        จะบังภาพเป็นสี่เหลี่ยมทับอยู่
        """
        p = theme.PALETTE
        self.banner = theme.Banner(theme.asset("Darkstory*BG2*.jpg"),
                                   dim=0.42, focus=0.3)
        self._banner_item = None

        self._title_item = canvas.create_text(
            22, 26, anchor="w", text="⚔  DARKSTORY CALCULATOR",
            font="ds.title", fill=p["gold_hi"])

        self.win_buttons = []
        for text, cmd, style_name in (("✕", self.on_close, "Close.TButton"),
                                      ("▢", self.chrome.toggle_maximize, "Chrome.TButton"),
                                      ("—", self.chrome.minimize, "Chrome.TButton")):
            btn = ttk.Button(canvas, text=text, style=style_name, width=3,
                             command=cmd, takefocus=False)
            self.win_buttons.append(btn)

        # ลากบริเวณหัวเพื่อย้ายหน้าต่าง — ผูกที่ canvas แล้วกรองด้วยพิกัด y
        canvas.bind("<Button-1>", self._titlebar_press, add="+")
        canvas.bind("<B1-Motion>", self._titlebar_drag, add="+")
        canvas.bind("<Double-Button-1>", self._titlebar_double, add="+")

    def _in_titlebar(self, event):
        return event.y < getattr(self, "_banner_h", 78) and \
            event.x < getattr(self, "_chrome_left", self.root.winfo_width() - 140)

    def _titlebar_press(self, event):
        if self._in_titlebar(event):
            self.chrome._start_move(event)

    def _titlebar_drag(self, event):
        if self.chrome._drag:
            self.chrome._do_move(event)

    def _titlebar_double(self, event):
        if self._in_titlebar(event):
            self.chrome.toggle_maximize()

    PAD = 16               # ระยะขอบรอบเนื้อหา — ช่องว่างนี้คือที่ที่เห็นภาพพื้นหลัง

    def _metrics(self):
        """คิดความสูงของแถบหัวและแถบสถานะจากขนาดฟอนต์จริง ไม่ใช่ค่าคงที่

        ถ้าใช้ค่าคงที่ พอฟอนต์โตตามหน้าต่าง ตัวหนังสือจะโดนตัดขอบล่าง
        """
        f = self.fonts.fonts
        title_h = f["ds.title"].metrics("linespace")
        small_h = f["ds.small"].metrics("linespace")
        banner_h = max(64, title_h + 34)
        status_h = max(26, small_h + 12)
        return banner_h, status_h

    def _on_shell_resize(self, event):
        width, height = event.width, event.height
        if width < 10 or height < 10:
            return
        canvas = self.backdrop.canvas

        # canvas เต็มหน้าต่างพอดี จึงเป็นสัญญาณ resize ที่เชื่อถือได้กว่า Configure
        # ของ root — ถ้า region ไม่ตามขนาดใหม่ หน้าต่างจะโดนตัดเหลือขนาดเดิม
        self.chrome.refresh_region()

        # ปรับฟอนต์ก่อน แล้วค่อยคิดระยะ เพราะระยะอิงขนาดฟอนต์
        if self.fonts.rescale(width, height):
            self._apply_font_scale()
        banner_h, status_h = self._metrics()

        self.backdrop.render(width, height, radius=theme.CORNER_RADIUS)

        if self.banner.render(width, banner_h):
            if self._banner_item is None:
                self._banner_item = canvas.create_image(
                    0, 0, anchor="nw", image=self.banner.photo)
            else:
                canvas.itemconfigure(self._banner_item, image=self.banner.photo)
        if self._banner_item is not None:
            canvas.tag_raise(self._banner_item)

        canvas.coords(self._title_item, 22, banner_h * 0.5)
        canvas.tag_raise(self._title_item)

        btn_h = max(24, self.fonts.fonts["ds.body"].metrics("linespace") + 8)
        x = width - 12
        for btn in self.win_buttons:
            btn.update_idletasks()
            w = btn.winfo_reqwidth()
            x -= w
            btn.place(x=x, y=10, width=w, height=btn_h)
            x -= 2
        self._chrome_left = x          # ใช้กันไม่ให้ลากหน้าต่างโดนปุ่มพวกนี้

        pad = self.PAD
        top = banner_h + pad
        body_h = height - top - status_h - pad
        self.body.place(x=pad, y=top,
                        width=max(1, width - pad * 2), height=max(1, body_h))
        self.status.place(x=pad, y=height - status_h - 5,
                          width=max(1, width - pad * 2), height=status_h)
        self._banner_h = banner_h

    def _apply_font_scale(self):
        """ปรับสิ่งที่ไม่ได้อิงฟอนต์ที่มีชื่อโดยอัตโนมัติ"""
        self.style.configure("Treeview", rowheight=self.fonts.row_height())
        scale = self.fonts.scale
        for col, base in (("name", 220), ("price", 120), ("thb", 120)):
            self.item_tree.column(col, width=int(base * scale))

    def _build_currency_tab(self, nb):
        p = theme.PALETTE
        tab = ttk.Frame(nb, padding=12)
        nb.add(tab, text="💱  แปลงเงิน")

        rate_card, rate = theme.card(tab, "เรตแลกเปลี่ยน", accent=p["gold"],
                                     subtitle="ใช้กับทุกแท็บในโปรแกรม")
        rate_card.pack(fill=tk.X, pady=(0, 12))
        rate.columnconfigure(0, weight=1)

        ttk.Label(rate, text="เหรียญทอง 1 เหรียญ = กี่บาท", style="Field.TLabel").grid(
            row=0, column=0, sticky="w")
        self.rate_entry = ttk.Entry(rate)
        self.rate_entry.insert(0, str(self.rate_gold_thb))
        self.rate_entry.grid(row=1, column=0, sticky="ew", pady=(2, 4))
        self.rate_entry.bind("<KeyRelease>", self.on_rate_change)
        self.rate_entry.bind("<FocusOut>", self.on_rate_change)
        self.rate_hint = ttk.Label(rate, text="", style="CardDim.TLabel")
        self.rate_hint.grid(row=2, column=0, sticky="w")
        ttk.Button(rate, text="💾  บันทึกเรต", style="Gold.TButton",
                   command=self.save_rate).grid(row=3, column=0, sticky="w", pady=(10, 0))

        conv_card, conv = theme.card(tab, "แปลงค่าเงิน", accent=p["accent"],
                                     subtitle="พิมพ์ช่องไหนก็ได้ อีกช่องคำนวณให้เอง")
        conv_card.pack(fill=tk.X)
        conv.columnconfigure(0, weight=1)

        ttk.Label(conv, text="เหรียญทอง", style="Field.TLabel").grid(
            row=0, column=0, sticky="w")
        self.gold_entry = ttk.Entry(conv, font="ds.bold")
        self.gold_entry.grid(row=1, column=0, sticky="ew", pady=(2, 10))
        self.gold_entry.bind("<KeyRelease>", self.gold_to_thb)

        ttk.Label(conv, text="เงินบาท", style="Field.TLabel").grid(
            row=2, column=0, sticky="w")
        self.thb_entry = ttk.Entry(conv, font="ds.bold")
        self.thb_entry.grid(row=3, column=0, sticky="ew", pady=(2, 0))
        self.thb_entry.bind("<KeyRelease>", self.thb_to_gold)

    def _build_items_tab(self, nb):
        p = theme.PALETTE
        tab = ttk.Frame(nb, padding=12)
        nb.add(tab, text="🛒  ไอเทม")
        tab.rowconfigure(1, weight=1)
        tab.columnconfigure(0, weight=1)

        add_card, form = theme.card(tab, "เพิ่มไอเทม", accent=p["accent"])
        add_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        form.columnconfigure(0, weight=3)
        form.columnconfigure(1, weight=2)

        ttk.Label(form, text="ชื่อไอเทม", style="Field.TLabel").grid(
            row=0, column=0, sticky="w")
        ttk.Label(form, text="ราคา (ทอง)", style="Field.TLabel").grid(
            row=0, column=1, sticky="w", padx=(8, 0))
        self.item_name = ttk.Entry(form)
        self.item_name.grid(row=1, column=0, sticky="ew", pady=(2, 8))
        self.item_price = ttk.Entry(form)
        self.item_price.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(2, 8))
        self.item_name.bind("<Return>", lambda e: self.item_price.focus_set())
        self.item_price.bind("<Return>", lambda e: self.add_item())

        buttons = ttk.Frame(form, style="Card.TFrame")
        buttons.grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Button(buttons, text="➕  เพิ่ม", style="Gold.TButton",
                   command=self.add_item).pack(side=tk.LEFT)
        ttk.Button(buttons, text="✏️  แก้ราคา",
                   command=self.edit_price).pack(side=tk.LEFT, padx=8)
        ttk.Button(buttons, text="🗑  ลบ", command=self.delete_item).pack(side=tk.LEFT)

        list_card, listing = theme.card(tab, "ราคาตลาด", accent=p["gold"],
                                        subtitle="ดับเบิลคลิกที่แถวเพื่อแก้ราคา")
        list_card.grid(row=1, column=0, sticky="nsew")
        listing.rowconfigure(1, weight=1)
        listing.columnconfigure(0, weight=1)

        search_row = ttk.Frame(listing, style="Card.TFrame")
        search_row.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        search_row.columnconfigure(1, weight=1)
        ttk.Label(search_row, text="🔍", style="Card.TLabel").grid(row=0, column=0)
        self.item_search = ttk.Entry(search_row)
        self.item_search.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self.item_search.bind("<KeyRelease>", lambda e: self.upd_tree())
        self.item_search.bind("<Escape>", lambda e: self.clear_search())
        ttk.Button(search_row, text="✕", width=3, command=self.clear_search).grid(
            row=0, column=2, padx=(6, 0))

        self.item_tree = ttk.Treeview(listing, columns=("name", "price", "thb"),
                                      show="headings", height=8)
        for col, text, width, anchor in (("name", "ชื่อไอเทม", 220, "w"),
                                         ("price", "ทอง", 120, "e"),
                                         ("thb", "บาท", 120, "e")):
            self.item_tree.heading(col, text=text)
            self.item_tree.column(col, width=width, anchor=anchor, stretch=(col == "name"))
        self.item_tree.grid(row=1, column=0, sticky="nsew")
        self.item_tree.bind("<Delete>", lambda e: self.delete_item())
        self.item_tree.bind("<Double-1>", self._on_tree_double_click)
        self.item_tree.bind("<Return>", lambda e: self.edit_price())

        bar = ttk.Scrollbar(listing, orient=tk.VERTICAL, command=self.item_tree.yview)
        bar.grid(row=1, column=1, sticky="ns")
        self.item_tree.configure(yscrollcommand=bar.set)

        bottom = ttk.Frame(listing, style="Card.TFrame")
        bottom.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.item_count = ttk.Label(bottom, text="0 รายการ", style="CardDim.TLabel")
        self.item_count.pack(side=tk.LEFT)
        self.save_items_btn = ttk.Button(bottom, text="💾  บันทึกไอเทม",
                                         style="Gold.TButton", command=self.save_items)
        self.save_items_btn.pack(side=tk.RIGHT)

    def _build_materials_tab(self, nb):
        """เหลือแค่ช่องราคา — การแยก/หลอมย้ายไปแท็บของตัวเองแล้ว"""
        tab = ttk.Frame(nb, padding=12)
        nb.add(tab, text="💰  ราคา")

        outer, body = theme.card(tab, "ราคาหินดั้งเดิม", accent=theme.TAB_ACCENTS[2])
        outer.pack(fill=tk.X)
        body.columnconfigure(1, weight=1)

        scale = gd.tier_scale(gd.BLUE_LADDER)
        self.price_entries = {}
        self.price_hints = {}

        row = 0
        for tier, spec in enumerate(gd.BLUE_LADDER):
            if not spec["tradeable"]:
                continue
            ttk.Label(body, text=spec["name"], style="Field.TLabel").grid(
                row=row, column=0, sticky="w")
            ttk.Label(body, text="= %s ชิ้นส่วน" % "{:,}".format(scale[tier]),
                      style="CardDim.TLabel").grid(row=row, column=1, sticky="e")

            entry = ttk.Entry(body)
            entry.grid(row=row + 1, column=0, columnspan=2, sticky="ew", pady=(3, 2))
            entry.bind("<KeyRelease>", lambda e, t=tier: self.upd_price(t))
            if self.mat_price(tier) > 0:   # ราคาที่เคยเก็บไว้ในเครื่อง
                entry.insert(0, str(self.mat_price(tier)))

            hint = ttk.Label(body, text="—", style="CardDim.TLabel")
            hint.grid(row=row + 2, column=0, columnspan=2, sticky="w", pady=(0, 14))

            self.price_entries[tier] = entry
            self.price_hints[tier] = hint
            row += 3

        # ชื่อเดิม — ตัวโหลดจากชีตและตัวบันทึกอ้างถึงช่องนี้อยู่
        self.blue_price = self.price_entries[1]

        self.save_mats_btn = ttk.Button(tab, text="💾  บันทึกราคา",
                                        style="Gold.TButton", command=self.save_mats)
        self.save_mats_btn.pack(pady=(14, 0))

    def _build_split_tab(self, nb):
        """แยกไอเทมลงชั้นล่าง / หลอมขึ้นชั้นบน — ทำงานทั้งสองทางในหน้าเดียว"""
        tab = ttk.Frame(nb, padding=12)
        nb.add(tab, text="🔀  แยก/หลอม")

        self.split_line = tk.StringVar(value=gd.LINE_BLUE)

        pick_outer, pick = theme.card(tab, "มีอะไรอยู่บ้าง",
                                      accent=theme.TAB_ACCENTS[3])
        pick_outer.pack(fill=tk.X, pady=(0, 12))
        pick.columnconfigure(1, weight=1)

        line_row = ttk.Frame(pick, style="Card.TFrame")
        line_row.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        for value, text in ((gd.LINE_BLUE, "สายน้ำเงิน"), (gd.LINE_RED, "สายแดง")):
            ttk.Radiobutton(line_row, text=text, value=value,
                            variable=self.split_line, style="Card.TRadiobutton",
                            command=self._split_line_changed).pack(
                side=tk.LEFT, padx=(0, 18))

        self.split_entries = []
        self.split_names = []
        self.split_worth = []
        for tier in range(len(gd.BLUE_LADDER)):
            name = ttk.Label(pick, text="", style="Field.TLabel")
            name.grid(row=tier + 1, column=0, sticky="w", pady=3)

            worth = ttk.Label(pick, text="", style="CardDim.TLabel")
            worth.grid(row=tier + 1, column=1, sticky="e", padx=(8, 10), pady=3)

            entry = ttk.Entry(pick, width=12, justify="right")
            entry.grid(row=tier + 1, column=2, sticky="e", pady=3)
            entry.bind("<KeyRelease>", self.calc_split)

            self.split_names.append(name)
            self.split_worth.append(worth)
            self.split_entries.append(entry)

        ttk.Button(pick, text="ล้างทั้งหมด", command=self.clear_split).grid(
            row=len(gd.BLUE_LADDER) + 1, column=2, sticky="e", pady=(12, 0))

        res_outer, res = theme.card(tab, "แยกออกมาได้", accent=theme.TAB_ACCENTS[0])
        res_outer.pack(fill=tk.X)
        res.columnconfigure(1, weight=1)

        self.split_total = ttk.Label(res, text="—", style="Value.TLabel")
        self.split_total.grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(res, text="ชิ้นส่วนรวมทั้งหมด", style="CardDim.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 12))

        self.split_out = []
        for tier in range(len(gd.BLUE_LADDER)):
            label = ttk.Label(res, text="", style="Card.TLabel")
            label.grid(row=tier + 2, column=0, sticky="w", pady=2)
            value = ttk.Label(res, text="", style="Info.Card.TLabel")
            value.grid(row=tier + 2, column=1, sticky="e", pady=2)
            self.split_out.append((label, value))

        self.split_note = ttk.Label(res, text="", style="CardDim.TLabel")
        self.split_note.grid(row=len(gd.BLUE_LADDER) + 2, column=0, columnspan=2,
                             sticky="w", pady=(12, 0))

        self._split_line_changed()

    def _build_calc_tab(self, nb):
        p = theme.PALETTE
        tab = ttk.Frame(nb, padding=12)
        nb.add(tab, text="📊  ตีบวก")
        tab.rowconfigure(3, weight=1)      # แถวว่างท้ายสุด ดันการ์ดทุกใบขึ้นบน
        tab.columnconfigure(0, weight=1)

        form_card, form = theme.card(tab, "ตั้งค่าการตีบวก", accent=p["gold"])
        form_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        form.columnconfigure(0, weight=5)
        form.columnconfigure(1, weight=4)

        left = ttk.Frame(form, style="Card.TFrame")
        left.grid(row=0, column=0, sticky="nsew")
        left.columnconfigure(0, weight=1)
        left.columnconfigure(1, weight=1)

        need = ttk.Frame(form, style="Card.TFrame")
        need.grid(row=0, column=1, sticky="nsew", padx=(16, 0))
        need.columnconfigure(1, weight=1)

        levels = [str(i) for i in range(MIN_LEVEL, MAX_LEVEL + 1)]

        def field(row, col, text, widget, span=1):
            ttk.Label(left, text=text, style="Field.TLabel").grid(
                row=row, column=col, columnspan=span, sticky="w",
                padx=(0 if col == 0 else 8, 0))
            widget.grid(row=row + 1, column=col, columnspan=span, sticky="ew",
                        pady=(2, 8), padx=(0 if col == 0 else 8, 0))

        self.st = ttk.Combobox(left, values=levels, state="readonly", width=5)
        self.st.set("1")
        field(0, 0, "จากระดับ", self.st)

        self.en = ttk.Combobox(left, values=levels, state="readonly", width=5)
        self.en.set("10")
        field(0, 1, "ถึงระดับ", self.en)

        self.gr = ttk.Combobox(left, values=GRADES, state="readonly", width=10)
        self.gr.set(GRADES[0])
        self.gr.bind("<<ComboboxSelected>>", self.on_mode_change)
        field(2, 0, "เกรดไอเทม", self.gr, span=2)

        self.inh = ttk.Combobox(left, values=INHERIT_MODES, state="readonly",
                                width=14)
        self.inh.set(INHERIT_NONE)
        self.inh.bind("<<ComboboxSelected>>", self.on_mode_change)
        field(4, 0, "การสืบทอด", self.inh, span=2)

        self.tgr = ttk.Combobox(left, values=GRADES, state="readonly", width=10)
        self.tgr.set(GRADES[0])
        field(6, 0, "เกรดเป้าหมาย", self.tgr, span=2)

        ttk.Button(left, text="🧮  คำนวณ", style="Gold.TButton",
                   command=self.calc_all).grid(row=8, column=0, columnspan=2,
                                               sticky="ew", pady=(4, 0))

        # ช่องสรุปฝั่งขวา — "ต้องใช้เท่าไหร่ ราคาเท่าไหร่" คนละเรื่องกับที่เรามีข้างล่าง
        ttk.Label(need, text="ต้องใช้", style="CardDim.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w")
        self.need_pieces = ttk.Label(need, text="—", style="Value.TLabel")
        self.need_pieces.grid(row=1, column=0, columnspan=2, sticky="w")
        self.need_melt = ttk.Label(need, text="", style="CardDim.TLabel")
        self.need_melt.grid(row=2, column=0, columnspan=2, sticky="w",
                            pady=(0, 10))

        ttk.Separator(need, orient="horizontal").grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        self.cost_mat = ttk.Label(need, text="—", style="Card.TLabel")
        self.cost_inherit = ttk.Label(need, text="—", style="Card.TLabel")
        for row, (text, value) in enumerate(((" มูลค่าวัสดุ", self.cost_mat),
                                             (" ค่าสืบทอด", self.cost_inherit))):
            ttk.Label(need, text=text, style="CardDim.TLabel").grid(
                row=4 + row, column=0, sticky="w")
            value.grid(row=4 + row, column=1, sticky="e")

        ttk.Separator(need, orient="horizontal").grid(
            row=6, column=0, columnspan=2, sticky="ew", pady=(8, 6))
        ttk.Label(need, text=" รวมทั้งหมด", style="Field.TLabel").grid(
            row=7, column=0, sticky="w")
        self.cost_total = ttk.Label(need, text="—", style="Info.Card.TLabel")
        self.cost_total.grid(row=7, column=1, sticky="e")
        self.cost_thb = ttk.Label(need, text="", style="CardDim.TLabel")
        self.cost_thb.grid(row=8, column=1, sticky="e")

        self.calc_note = ttk.Label(need, text="", style="CardDim.TLabel",
                                   wraplength=210, justify="left")
        self.calc_note.grid(row=9, column=0, columnspan=2, sticky="w",
                            pady=(8, 0))

        for combo in (self.st, self.en, self.gr, self.inh, self.tgr):
            combo.bind("<<ComboboxSelected>>", self._settings_changed, add="+")

        # --- หินที่จะใส่: 4 ชั้น x 2 สี เหมือนช่อง +/- ในหน้าตีบวกของเกม ---
        stone_card, stones = theme.card(tab, "หินที่จะใส่",
                                        accent=theme.TAB_ACCENTS[1])
        stone_card.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        stones.columnconfigure(0, weight=1)

        ttk.Label(stones, text="น้ำเงิน", style="Info.Card.TLabel").grid(
            row=0, column=1, pady=(0, 4))
        ttk.Label(stones, text="แดง (ใช้แล้วไอเทมถูกผนึก)",
                  style="Danger.Card.TLabel").grid(
            row=0, column=2, padx=(8, 0), pady=(0, 4))

        short = ("ชิ้นส่วน", "หิน / พลอย", "ขั้นสูง", "สูงสุด")
        scale = gd.tier_scale(gd.BLUE_LADDER)
        self.stone_entries = {}
        for tier in range(len(gd.BLUE_LADDER)):
            ttk.Label(stones, text="%s   ×%s" % (short[tier],
                                                 "{:,}".format(scale[tier])),
                      style="Field.TLabel").grid(row=tier + 1, column=0,
                                                 sticky="w", pady=3)
            for col, line in ((1, gd.LINE_BLUE), (2, gd.LINE_RED)):
                cell = ttk.Frame(stones, style="Card.TFrame")
                cell.grid(row=tier + 1, column=col, sticky="e", pady=3,
                          padx=(8, 0))
                icon = theme.stone_icon(line, tier)
                if icon is not None:
                    badge = ttk.Label(cell, image=icon, style="Card.TLabel")
                    badge.image = icon      # กัน Tk เก็บกวาดรูปทิ้ง
                    badge.pack(side=tk.LEFT, padx=(0, 5))
                entry = ttk.Entry(cell, width=9, justify="right")
                entry.pack(side=tk.LEFT)
                entry.bind("<KeyRelease>", self.upd_chance)
                self.stone_entries[(line, tier)] = entry

        btns = ttk.Frame(stones, style="Card.TFrame")
        btns.grid(row=len(gd.BLUE_LADDER) + 1, column=0, columnspan=3,
                  sticky="e", pady=(12, 0))
        ttk.Button(btns, text="เติมให้เต็ม 100%",
                   command=self.fill_to_full).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btns, text="ล้าง", command=self.clear_stones).pack(side=tk.LEFT)

        # --- แถบโอกาสสำเร็จ ---
        chance_card, chance = theme.card(tab, "โอกาสสำเร็จ",
                                         accent=theme.TAB_ACCENTS[0])
        chance_card.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        chance.columnconfigure(0, weight=1)

        self.chance_value = ttk.Label(chance, text="0.0000 %", style="Chance.TLabel")
        self.chance_value.grid(row=0, column=0, sticky="w")

        self.chance_bar = ttk.Progressbar(chance, orient="horizontal", maximum=100.0,
                                          style="Chance.Horizontal.TProgressbar")
        self.chance_bar.grid(row=1, column=0, sticky="ew", pady=(6, 6))

        self.chance_detail = ttk.Label(chance, text="—", style="CardDim.TLabel")
        self.chance_detail.grid(row=2, column=0, sticky="w")

        self.on_mode_change()
        self.upd_chance()
        self.calc_all(quiet=True)

    # ---------------- สถานะ / busy ----------------

    def set_status(self, text, warn=False):
        self.status.config(text=text, foreground=theme.PALETTE["danger"] if warn else "")

    def set_busy(self, busy, text=None):
        self.busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        for widget in (self.load_btn, self.save_items_btn, self.save_mats_btn):
            widget.config(state=state)
        self.root.config(cursor="watch" if busy else "")
        if text:
            self.set_status(text)

    def run_async(self, work, done):
        """ยิงงานเน็ตใน thread แยก แล้วกลับมาแตะ widget บน main thread เท่านั้น"""
        def worker():
            try:
                result = work()
            except Exception as exc:                # pragma: no cover - กันตาย
                log.exception("งานเบื้องหลังล้มเหลว")
                result = ("__error__", str(exc))
            self.root.after(0, lambda: done(result))

        threading.Thread(target=worker, daemon=True).start()

    # ---------------- แท็บแปลงเงิน ----------------

    def on_rate_change(self, event=None):
        value = parse_num(self.rate_entry.get(), None)
        if value is None or value <= 0:
            # เก็บเรตเดิมไว้ ไม่ทำลายค่าที่ถูกต้องทิ้ง
            self.rate_entry.config(foreground=theme.PALETTE["danger"])
            self.rate_hint.config(text="เรตไม่ถูกต้อง — ยังใช้ %s อยู่" % self.rate_gold_thb,
                                  foreground=theme.PALETTE["danger"])
            return
        self.rate_entry.config(foreground="")
        self.rate_hint.config(text="", foreground="")
        if value != self.rate_gold_thb:
            self.rate_gold_thb = value
            self.refresh_all()

    def refresh_all(self):
        """วาดทุกอย่างที่ขึ้นกับเรตใหม่ — กันไม่ให้มีเลขบาทสองค่าอยู่บนจอพร้อมกัน"""
        self.upd_tree()
        self.refresh_prices()
        self.calc_split()
        self.calc_all(quiet=True)
        self.gold_to_thb()

    def gold_to_thb(self, event=None):
        gold = parse_num(self.gold_entry.get(), None)
        if gold is None:
            return
        self._set_entry(self.thb_entry, money(gold * self.rate_gold_thb))

    def thb_to_gold(self, event=None):
        thb = parse_num(self.thb_entry.get(), None)
        if thb is None:
            return
        if self.rate_gold_thb <= 0:
            self._set_entry(self.gold_entry, "--")
            return
        self._set_entry(self.gold_entry, money(thb / self.rate_gold_thb))

    @staticmethod
    def _set_entry(entry, text):
        """แก้ค่าใน widget หลังจากคำนวณเสร็จแล้วเท่านั้น

        ของเดิมลบช่องปลายทางก่อนแล้วค่อยหาร ทำให้ตอนหารพังช่องถูกล้างทิ้งไปแล้ว
        """
        entry.delete(0, tk.END)
        entry.insert(0, text)

    def save_rate(self):
        value = parse_num(self.rate_entry.get(), None)
        if value is None or value <= 0:
            messagebox.showwarning("แจ้งเตือน", "กรุณาใส่เรตเป็นตัวเลขมากกว่า 0")
            return
        self.rate_gold_thb = value
        self.refresh_all()
        self._push("currency",
                   [["key", "value"], ["rate_gold_to_thb", str(value)]],
                   "บันทึกเรตแล้ว")

    # ---------------- แท็บไอเทม ----------------

    def add_item(self):
        name = self.item_name.get().strip()
        price = parse_num(self.item_price.get(), None)
        if not name:
            messagebox.showwarning("แจ้งเตือน", "กรุณาใส่ชื่อไอเทม")
            self.item_name.focus_set()
            return
        if price is None or price < 0:
            messagebox.showwarning("แจ้งเตือน", "กรุณาใส่ราคาเป็นตัวเลขไม่ติดลบ")
            self.item_price.focus_set()
            return

        self.items.append({"name": name, "price": price})
        self.items_dirty = True
        self.item_name.delete(0, tk.END)
        self.item_price.delete(0, tk.END)
        self.item_name.focus_set()
        self.item_search.delete(0, tk.END)   # ไม่งั้นของที่เพิ่งเพิ่มโดนคำค้นเดิมกรองหาย
        self.upd_tree()
        self.set_status("เพิ่ม '%s' แล้ว (ยังไม่ได้บันทึกขึ้นเซิร์ฟเวอร์)" % name)

    def _selected_index(self):
        """ตำแหน่งของแถวที่เลือกใน self.items คืน None ถ้าไม่ได้เลือกหรือเลือกหลายแถว

        ต้องอ่านจาก iid ไม่ใช่ .index() เพราะตารางอาจถูกกรองด้วยคำค้นอยู่
        """
        selected = self.item_tree.selection()
        if len(selected) != 1:
            return None
        try:
            index = int(selected[0])
        except ValueError:
            return None
        return index if 0 <= index < len(self.items) else None

    def _on_tree_double_click(self, event):
        # ดับเบิลคลิกบนหัวตาราง/เส้นแบ่งคอลัมน์ ไม่ควรเปิดหน้าต่างแก้ราคา
        if self.item_tree.identify_region(event.x, event.y) != "cell":
            return
        row = self.item_tree.identify_row(event.y)
        if row:
            self.item_tree.selection_set(row)
            self.edit_price()

    def edit_price(self):
        index = self._selected_index()
        if index is None:
            messagebox.showinfo("แจ้งเตือน",
                                "เลือกไอเทมที่ต้องการแก้ราคา 1 รายการก่อน\n"
                                "(ดับเบิลคลิกที่แถวก็ได้)")
            return

        item = self.items[index]
        new_price = PriceDialog(self.root, item, self.rate_gold_thb).result
        if new_price is None or new_price == item["price"]:
            return

        old_price = item["price"]
        item["price"] = new_price
        self.items_dirty = True
        self.upd_tree()

        # เลือกแถวเดิมไว้ให้ จะได้แก้ตัวถัดไปหรือกด Enter ซ้ำได้เลย
        iid = str(index)
        if self.item_tree.exists(iid):
            self.item_tree.selection_set(iid)
            self.item_tree.see(iid)

        self.set_status("แก้ราคา '%s': %s → %s ทอง (ยังไม่ได้บันทึก)"
                        % (item["name"], money(old_price), money(new_price)))

    def delete_item(self):
        selected = self.item_tree.selection()
        if not selected:
            messagebox.showinfo("แจ้งเตือน", "เลือกแถวที่ต้องการลบก่อน")
            return
        indexes = sorted((int(iid) for iid in selected if iid.isdigit()), reverse=True)
        for index in indexes:
            if 0 <= index < len(self.items):
                del self.items[index]
        self.items_dirty = True
        self.upd_tree()
        self.set_status("ลบ %d รายการแล้ว (ยังไม่ได้บันทึก)" % len(indexes))

    def clear_search(self):
        self.item_search.delete(0, tk.END)
        self.upd_tree()

    def upd_tree(self):
        self.item_tree.delete(*self.item_tree.get_children())
        query = self.item_search.get() if hasattr(self, "item_search") else ""
        matches = search_items(self.items, query)

        for index, _score in matches:
            item = self.items[index]
            # iid = ตำแหน่งจริงใน self.items ไม่ใช่ลำดับแถวที่เห็น
            # พอกรองด้วยคำค้นแล้วสองอย่างนี้ไม่ตรงกัน ที่อื่นต้องอ่านจาก iid เท่านั้น
            self.item_tree.insert("", tk.END, iid=str(index), values=(
                item["name"],
                money(item["price"]),
                money(item["price"] * self.rate_gold_thb),
            ))

        suffix = " • ยังไม่ได้บันทึก" if self.items_dirty else ""
        if not norm_search(query):
            self.item_count.config(text="%d รายการ%s" % (len(self.items), suffix))
        elif not matches:
            self.item_count.config(text="ไม่เจอ '%s'%s" % (query.strip(), suffix))
        elif matches[0][1] < SEARCH_MIN_SCORE:
            # ไม่มีชื่อไหนใกล้พอ แต่เดาให้ดูดีกว่าโชว์ตารางเปล่า
            self.item_count.config(
                text="ไม่เจอที่ตรง — เดาว่าน่าจะเป็น %d รายการนี้%s"
                     % (len(matches), suffix))
        else:
            self.item_count.config(
                text="เจอ %d จาก %d รายการ%s" % (len(matches), len(self.items), suffix))

    def save_items(self):
        if not self.items:
            messagebox.showwarning(
                "แจ้งเตือน",
                "รายการว่างอยู่ — การบันทึกจะลบข้อมูลไอเทมทั้งหมดบนเซิร์ฟเวอร์\n"
                "ถ้าต้องการล้างข้อมูลจริงๆ ให้แก้ในชีตโดยตรง")
            return
        if not self._confirm_overwrite("items", len(self.items)):
            return
        rows = [["name", "price_gold"]] + [[i["name"], i["price"]] for i in self.items]
        self._push("items", rows, "บันทึกไอเทมแล้ว", on_success=self._items_saved)

    def _items_saved(self):
        self.items_dirty = False
        self.upd_tree()
        self._save_local()

    # ---------------- แท็บราคา ----------------

    def upd_price(self, tier, event=None):
        """อัปเดตราคาหินชั้นหนึ่ง แล้ววาดบรรทัดสรุปใต้ช่องใหม่"""
        entry = self.price_entries[tier]
        hint = self.price_hints[tier]
        worth = gd.tier_pieces(gd.BLUE_LADDER, tier)

        text = entry.get().strip()
        if not text:
            entry.config(foreground="")
            self.mat_prices[tier] = 0.0
            hint.config(text="—", foreground="")
            self.upd_chance()
            return

        value = parse_num(text, None)
        if value is None or value < 0:
            # เก็บราคาเดิมไว้ และอย่าโชว์ตัวเลข เพื่อไม่ให้อ่านเป็นคำตอบ
            entry.config(foreground=theme.PALETTE["danger"])
            hint.config(text="ราคาไม่ถูกต้อง — ยังใช้ %s ทองอยู่"
                             % money(self.mat_price(tier)),
                        foreground=theme.PALETTE["danger"])
            self.upd_chance()
            return

        entry.config(foreground="")
        self.mat_prices[tier] = value
        hint.config(text="%s บาท   •   %s ทอง/ชิ้นส่วน"
                         % (money(value * self.rate_gold_thb),
                            money(value / float(worth))),
                    foreground="")
        self.upd_chance()
        self.calc_all(quiet=True)

    def refresh_prices(self):
        """วาดบรรทัดใต้ช่องราคาทุกชั้นใหม่ — เรียกตอนเรตเปลี่ยนหรือโหลดข้อมูลเสร็จ"""
        for tier in sorted(self.price_entries):
            self.upd_price(tier)

    def save_mats(self):
        for tier in sorted(self.price_entries):
            text = self.price_entries[tier].get().strip()
            value = parse_num(text, None)
            if text and (value is None or value < 0):
                messagebox.showwarning(
                    "แจ้งเตือน",
                    "ราคา%s กรอกไม่ถูกต้อง แก้ให้เรียบร้อยก่อนบันทึก"
                    % gd.BLUE_LADDER[tier]["name"])
                return

        tiers = sorted(self.price_entries)
        if not self._confirm_overwrite("materials", len(tiers)):
            return
        # ต้องส่งทุกชั้นที่ซื้อขายได้ เพราะฝั่งชีตล้างข้อมูลเดิมก่อนเขียนทับ
        # ถ้าส่งไม่ครบ ราคาชั้นที่ขาดไปจะหายจากชีต
        rows = [["name", "price_gold_per_unit"]]
        rows += [[gd.BLUE_LADDER[t]["name"], self.mat_price(t)] for t in tiers]
        self._push("materials", rows, "บันทึกราคาแล้ว", on_success=self._save_local)

    # ---------------- แท็บแยก/หลอม ----------------

    def _current_ladder(self):
        return gd.ladder(self.split_line.get())

    def _split_line_changed(self):
        """สลับสาย — เปลี่ยนชื่อชั้นทั้งหมดแล้วคิดใหม่"""
        rows = self._current_ladder()
        scale = gd.tier_scale(rows)
        line = self.split_line.get()
        for tier, spec in enumerate(rows):
            icon = theme.stone_icon(line, tier)
            for label in (self.split_names[tier], self.split_out[tier][0]):
                label.config(text=spec["name"])
                if icon is not None:
                    label.config(image=icon, compound="left", padding=(0, 0, 6, 0))
                    label.image = icon      # กัน Tk เก็บกวาดรูปทิ้ง
            self.split_worth[tier].config(
                text="= %s ชิ้นส่วน" % "{:,}".format(scale[tier]))
        self.calc_split()

    def clear_split(self):
        for entry in self.split_entries:
            entry.delete(0, tk.END)
        self.calc_split()

    def calc_split(self, event=None):
        """รวมของทุกชั้นเป็นชิ้นส่วน แล้วแยกกลับลงมาใหม่

        ในเกมแยกลงได้ไม่สูญเสีย ยอดชิ้นส่วนรวมจึงเท่าเดิมเสมอไม่ว่าจะถือชั้นไหน
        """
        rows = self._current_ladder()
        counts = []
        bad = False
        for entry in self.split_entries:
            text = entry.get().strip()
            if not text:
                counts.append(0)
                entry.config(foreground="")
                continue
            amount = parse_count(text, None)
            if amount is None:
                counts.append(0)
                entry.config(foreground=theme.PALETTE["danger"])
                bad = True
            else:
                counts.append(amount)
                entry.config(foreground="")

        total = gd.to_pieces(rows, counts)
        self.split_total.config(text="{:,}".format(total))

        parts = gd.split_down(rows, total)
        for tier, spec in enumerate(rows):
            self.split_out[tier][1].config(
                text="%s %s" % ("{:,}".format(parts[tier]), spec["unit"]))

        if bad:
            self.split_note.config(text="มีช่องที่กรอกไม่ใช่จำนวนเต็ม",
                                   foreground=theme.PALETTE["danger"])
        elif total > 0 and self.split_line.get() == gd.LINE_BLUE \
                and self.mat_blue_price > 0:
            # เศษที่หลอมไม่ครบก็เป็นทุน คิดตามสัดส่วนไม่ปัดทิ้ง
            value = gd.pieces_value(total, self.mat_blue_price, MATERIAL_BLUE_RATIO)
            self.split_note.config(
                text="≈ %s ทอง  =  %s บาท" % (money(value),
                                              money(value * self.rate_gold_thb)),
                foreground="")
        else:
            self.split_note.config(text="", foreground="")

    # ---------------- แถบโอกาสสำเร็จ ----------------

    def _needed_pieces(self):
        """ชิ้นส่วนที่ทำให้เต็ม 100% — None ถ้าตัวเลือกยังไม่ครบ"""
        try:
            return gd.upgrade_pieces(int(self.st.get()), int(self.en.get()),
                                     GRADES.index(self.gr.get()))
        except (ValueError, CalcError):
            return None

    def _stones_put_in(self):
        """รวมหินที่กรอกทั้ง 8 ช่องเป็นจำนวนชิ้นส่วน

        สายแดงกับสายน้ำเงินให้โอกาสเท่ากันชิ้นต่อชิ้น จึงบวกรวมกันได้ตรงๆ
        คืน (จำนวนชิ้นส่วน, มีช่องที่กรอกผิดหรือไม่)
        """
        total = 0
        bad = False
        for line in (gd.LINE_BLUE, gd.LINE_RED):
            rows = gd.ladder(line)
            counts = []
            for tier in range(len(rows)):
                entry = self.stone_entries[(line, tier)]
                text = entry.get().strip()
                if not text:
                    counts.append(0)
                    entry.config(foreground="")
                    continue
                amount = parse_count(text, None)
                if amount is None:
                    counts.append(0)
                    entry.config(foreground=theme.PALETTE["danger"])
                    bad = True
                else:
                    counts.append(amount)
                    entry.config(foreground="")
            total += gd.to_pieces(rows, counts)
        return total, bad

    def upd_chance(self, event=None):
        # ถูกเรียกจาก upd_price ได้ตั้งแต่ยังสร้างแท็บตีบวกไม่เสร็จ
        if not hasattr(self, "chance_bar"):
            return

        have, bad = self._stones_put_in()
        needed = self._needed_pieces()

        if needed is None:
            self.chance_value.config(text="—")
            self.chance_bar.config(value=0)
            self.chance_detail.config(text="", foreground="")
            return

        pct = gd.success_chance(have, needed)
        self.chance_value.config(text="%.4f %%" % pct)
        self.chance_bar.config(value=pct)

        if bad:
            self.chance_detail.config(text="มีช่องที่กรอกไม่ใช่จำนวนเต็ม",
                                      foreground=theme.PALETTE["danger"])
            return

        detail = "ใส่ %s  /  ต้องใช้ %s ชิ้นส่วน" % ("{:,}".format(have),
                                                    "{:,}".format(needed))
        if have < needed:
            detail += "   •   ขาดอีก %s" % "{:,}".format(needed - have)
        self.chance_detail.config(text=detail, foreground="")

    def fill_to_full(self):
        """เติมหินสายน้ำเงินให้พอดี 100% แล้วล้างสายแดงออก"""
        needed = self._needed_pieces()
        if not needed:
            return
        parts = gd.split_down(gd.BLUE_LADDER, needed)
        for tier in range(len(gd.BLUE_LADDER)):
            self._set_entry(self.stone_entries[(gd.LINE_BLUE, tier)],
                            str(parts[tier]) if parts[tier] else "")
            self._set_entry(self.stone_entries[(gd.LINE_RED, tier)], "")
        self.upd_chance()

    def clear_stones(self):
        for entry in self.stone_entries.values():
            entry.delete(0, tk.END)
        self.upd_chance()

    # ---------------- แท็บคำนวณ ----------------

    def on_mode_change(self, event=None):
        """จำกัดตัวเลือกเป้าหมายเกรดตามโหมด — เลือกค่าที่ไม่มีข้อมูลไม่ได้ตั้งแต่แรก"""
        mode = self.inh.get()
        try:
            grade_index = GRADES.index(self.gr.get())
        except ValueError:
            grade_index = 0

        if mode == INHERIT_NONE:
            self.tgr.config(values=[], state="disabled")
            self.tgr.set("")
            return

        targets = gd.available_targets(mode, grade_index)
        self.tgr.config(values=targets,
                        state="disabled" if len(targets) <= 1 else "readonly")
        if targets:
            if self.tgr.get() not in targets:
                self.tgr.set(targets[0])
        else:
            self.tgr.set("")

    def _settings_changed(self, event=None):
        """ตั้งค่าเปลี่ยน — อัปเดตทั้งช่องสรุปข้างบนและโอกาสข้างล่างให้ตรงกันเสมอ"""
        self.upd_chance()
        self.calc_all(quiet=True)

    def _clear_need(self, note=""):
        self.need_pieces.config(text="—")
        self.need_melt.config(text="")
        self.cost_mat.config(text="—")
        self.cost_inherit.config(text="—")
        self.cost_total.config(text="—")
        self.cost_thb.config(text="")
        self.calc_note.config(text=note,
                              foreground=theme.PALETTE["danger"] if note else "")

    def calc_all(self, quiet=False):
        """ส่วนบนของแท็บ: ตีถึงระดับที่ตั้งไว้ ต้องใช้เท่าไหร่ และเป็นเงินเท่าไหร่

        คนละเรื่องกับส่วนล่าง ซึ่งดูว่า "ของที่มีอยู่ตอนนี้" ได้โอกาสกี่ %

        quiet=True คือโปรแกรมเรียกเองตอนผู้ใช้เปลี่ยนตัวเลือก จะไม่เด้ง popup
        ต้องกดปุ่มคำนวณเองถึงจะบอกเหตุผลตอนเลือกไม่ครบ
        """
        if not hasattr(self, "need_pieces"):
            return

        try:
            start = int(self.st.get())
            end = int(self.en.get())
            grade_index = GRADES.index(self.gr.get())
            mode = self.inh.get()
            target_name = self.tgr.get()
            target_index = (GRADES.index(target_name)
                            if target_name in GRADES else grade_index)

            pieces = gd.upgrade_pieces(start, end, grade_index)
            inherit = gd.inherit_cost(mode, end, grade_index, target_index)
        except ValueError:
            self._clear_need()
            if not quiet:
                messagebox.showwarning("แจ้งเตือน", "กรุณาเลือกค่าจากรายการให้ครบ")
            return
        except CalcError as exc:
            self._clear_need(str(exc))
            if not quiet:
                messagebox.showwarning("แจ้งเตือน", str(exc))
            return

        # เศษที่หลอมไม่ครบก็เป็นทุน จึงคิดตามสัดส่วน ไม่ปัดขึ้นและไม่ปัดทิ้ง
        stones, leftover = gd.melt(pieces, MATERIAL_BLUE_RATIO)
        material_gold = gd.pieces_value(pieces, self.mat_blue_price,
                                        MATERIAL_BLUE_RATIO)
        total_gold = material_gold + inherit

        self.need_pieces.config(text="{:,} ชิ้นส่วน".format(pieces))
        melt_text = "= %s %s" % ("{:,}".format(stones), gd.BLUE_LADDER[1]["unit"])
        if leftover:
            melt_text += "  + เศษ %d ชิ้น" % leftover
        self.need_melt.config(text=melt_text)

        self.cost_mat.config(text="%s ทอง" % money(material_gold))
        self.cost_inherit.config(text="%s ทอง" % money(inherit))
        self.cost_total.config(text="%s ทอง" % money(total_gold))
        self.cost_thb.config(text="%s บาท"
                                  % money(total_gold * self.rate_gold_thb))

        notes = []
        if mode == gd.INHERIT_MODE_HIGHER:
            result_level = gd.HIGHER_RESULT_LEVEL.get(end)
            if result_level is not None:
                # สืบทอดข้ามเกรดแล้วระดับตีบวกจะลดลง ต้องบอกก่อนตัดสินใจ
                notes.append("⚠ สืบทอดข้ามเกรดแล้วเหลือ +%d (จาก +%d)"
                             % (result_level, end))
        if self.mat_blue_price <= 0:
            notes.append("ยังไม่ได้ใส่ราคาในแท็บ 💰 ราคา มูลค่าวัสดุจึงเป็น 0")
        self.calc_note.config(text="\n".join(notes),
                              foreground=theme.PALETTE["danger"] if notes else "")

        if not quiet:
            if self.mat_blue_price <= 0:
                messagebox.showwarning(
                    "แจ้งเตือน",
                    "กรุณาใส่ราคาหินดั้งเดิมในแท็บ 💰 ราคา ก่อน\n"
                    "ไม่งั้นมูลค่าวัสดุจะออกมาเป็น 0 ซึ่งไม่ใช่ราคาจริง")
            self.set_status("คำนวณ +%d → +%d เรียบร้อย" % (start, end))

    # ---------------- เซิร์ฟเวอร์ ----------------

    def _confirm_overwrite(self, sheet, row_count):
        if not self.loaded_from_server:
            proceed = messagebox.askyesno(
                "ยืนยัน",
                "ยังไม่ได้โหลดข้อมูลจากเซิร์ฟเวอร์ในรอบนี้\n"
                "การบันทึกจะเขียนทับชีต '%s' ทั้งหมดด้วย %d แถวที่มีอยู่ตอนนี้\n\n"
                "ต้องการทำต่อหรือไม่?" % (sheet, row_count))
            if not proceed:
                return False
        return messagebox.askyesno(
            "ยืนยันการเขียนทับ",
            "กำลังจะเขียนทับชีต '%s' ด้วยข้อมูล %d แถว\nยืนยันหรือไม่?"
            % (sheet, row_count))

    def _push(self, sheet, rows, success_text, on_success=None):
        if self.busy:
            return
        if not self.api.configured:
            messagebox.showerror("ผิดพลาด",
                                 "ยังไม่ได้ตั้งค่าลิงก์เซิร์ฟเวอร์\n"
                                 "ใส่ server_url ในไฟล์ darkstory_config.json")
            return

        self.set_busy(True, "กำลังบันทึกชีต '%s'..." % sheet)

        def done(result):
            self.set_busy(False)
            ok, err = result if isinstance(result, tuple) else (False, str(result))
            if ok:
                self.set_status(success_text)
                messagebox.showinfo("สำเร็จ", success_text)
                if on_success:
                    on_success()
            else:
                self.set_status("บันทึกไม่สำเร็จ: %s" % err, warn=True)
                messagebox.showerror("ผิดพลาด", err or "บันทึกไม่สำเร็จ")

        self.run_async(lambda: self.api.update(sheet, rows), done)

    def load_from_server(self):
        if self.busy:
            return
        if not self.api.configured:
            messagebox.showerror("ผิดพลาด",
                                 "ยังไม่ได้ตั้งค่าลิงก์เซิร์ฟเวอร์\n"
                                 "ใส่ server_url ในไฟล์ darkstory_config.json")
            return
        if self.items_dirty and not messagebox.askyesno(
                "ยืนยัน",
                "มีไอเทม %d รายการที่ยังไม่ได้บันทึก\n"
                "การโหลดจะเขียนทับรายการเหล่านี้ ต้องการทำต่อหรือไม่?" % len(self.items)):
            return

        self.set_busy(True, "กำลังโหลดข้อมูลจากเซิร์ฟเวอร์...")

        def work():
            return {name: self.api.read(name)
                    for name in ("currency", "items", "materials")}

        self.run_async(work, self._apply_server_data)

    def _apply_server_data(self, results):
        self.set_busy(False)
        if not isinstance(results, dict):
            messagebox.showerror("ผิดพลาด", "โหลดข้อมูลไม่สำเร็จ: %s" % (results,))
            return

        loaded, failed = [], []
        for sheet, outcome in results.items():
            rows, err = outcome
            if err or rows is None:
                failed.append("%s (%s)" % (sheet, err))
                continue
            try:
                self._apply_sheet(sheet, rows)
                loaded.append(sheet)
            except Exception:
                log.exception("อ่านชีต %s ไม่สำเร็จ", sheet)
                failed.append("%s (ข้อมูลในชีตไม่ถูกต้อง)" % sheet)

        self.refresh_all()

        if loaded and not failed:
            self.loaded_from_server = True
            self.items_dirty = False
            self.upd_tree()
            self._save_local()
            self.set_status("โหลดข้อมูลครบทั้ง 3 ชีตแล้ว")
            messagebox.showinfo("สำเร็จ", "โหลดข้อมูลเรียบร้อยแล้ว!")
        elif loaded:
            self._save_local()
            self.set_status("โหลดได้บางส่วน — ล้มเหลว: %s" % ", ".join(failed), warn=True)
            messagebox.showwarning(
                "โหลดได้บางส่วน",
                "สำเร็จ: %s\n\nล้มเหลว:\n%s"
                % (", ".join(loaded), "\n".join("• " + f for f in failed)))
        else:
            self.set_status("โหลดไม่สำเร็จทั้งหมด", warn=True)
            messagebox.showerror(
                "ผิดพลาด",
                "โหลดข้อมูลไม่สำเร็จ:\n%s" % "\n".join("• " + f for f in failed))

    def _apply_sheet(self, sheet, rows):
        if sheet == "currency":
            for row in rows:
                if row.get("key") == "rate_gold_to_thb":
                    rate = to_num(row.get("value"), None)
                    if rate and rate > 0:
                        self.rate_gold_thb = rate
                        self._set_entry(self.rate_entry, str(rate))
        elif sheet == "items":
            items = []
            for row in rows:
                name = str(row.get("name", "")).strip()
                price = to_num(row.get("price_gold"), None)
                if not name or price is None:
                    log.warning("ข้ามแถวไอเทมที่อ่านไม่ได้: %r", row)
                    continue
                items.append({"name": name, "price": price})
            self.items = items
        elif sheet == "materials":
            by_name = {gd.BLUE_LADDER[t]["name"]: t for t in self.price_entries}
            for row in rows:
                price = to_num(row.get("price_gold_per_unit"), None)
                if price is None or price < 0:
                    continue
                # ชื่อที่ไม่ได้อยู่ในบันไดสายน้ำเงิน (เช่นแถวพลอยสีแดงเข้มในชีตเก่า)
                # ถูกข้าม — ของสายแดงซื้อขายไม่ได้ จึงไม่มีราคาให้เก็บ
                tier = by_name.get(str(row.get("name", "")).strip())
                if tier is None:
                    continue
                self.mat_prices[tier] = price
                self._set_entry(self.price_entries[tier], str(price))
            self.refresh_prices()

    # ---------------- เก็บข้อมูลในเครื่อง ----------------

    def _load_local(self):
        data = read_json(LOCAL_PATH, {})
        rate = to_num(data.get("rate_gold_thb"), None)
        if rate and rate > 0:
            self.rate_gold_thb = rate
        # ฟอร์แมตเก่าเก็บราคาชั้นเดียวชื่อ mat_blue_price — ย้ายเข้าชั้น 1 ให้เอง
        # ไม่งั้นคนที่อัปเดตจากเวอร์ชันก่อนจะเปิดมาเจอช่องราคาว่างเปล่า
        legacy = to_num(data.get("mat_blue_price"), 0.0) or 0.0
        if legacy > 0:
            self.mat_prices[1] = legacy
        saved = data.get("mat_prices")
        if isinstance(saved, dict):
            for key, value in saved.items():
                price = to_num(value, None)
                try:
                    tier = int(key)
                except (TypeError, ValueError):
                    continue
                if price is not None and price >= 0:
                    self.mat_prices[tier] = price
        for row in data.get("items", []) if isinstance(data.get("items"), list) else []:
            if isinstance(row, dict) and row.get("name"):
                price = to_num(row.get("price"), None)
                if price is not None:
                    self.items.append({"name": str(row["name"]), "price": price})

    def _save_local(self):
        write_json(LOCAL_PATH, {
            "rate_gold_thb": self.rate_gold_thb,
            # คีย์เดิมเก็บต่อไว้ เผื่อเปิดด้วยโปรแกรมเวอร์ชันก่อนหน้า
            "mat_blue_price": self.mat_blue_price,
            "mat_prices": {str(k): v for k, v in self.mat_prices.items()},
            "items": self.items,
        })

    def on_close(self):
        if self.items_dirty:
            answer = messagebox.askyesnocancel(
                "ยังไม่ได้บันทึก",
                "มีไอเทม %d รายการที่ยังไม่ได้บันทึกขึ้นเซิร์ฟเวอร์\n"
                "ต้องการเก็บไว้ในเครื่องก่อนปิดหรือไม่?\n\n"
                "ใช่ = เก็บแล้วปิด | ไม่ = ปิดเลย | ยกเลิก = กลับไปทำงานต่อ"
                % len(self.items))
            if answer is None:
                return
            if answer:
                self._save_local()
        else:
            self._save_local()
        self.root.destroy()


def enable_dpi_awareness():
    """จอ scaling 150% จะได้ไม่เบลอ — เฉพาะ Windows"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (ImportError, AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def report_fatal(exc):
    """แสดงข้อผิดพลาดร้ายแรงให้เห็น — build แบบ --windowed ไม่มี console ให้ดู traceback"""
    log.exception("โปรแกรมหยุดทำงาน")
    try:
        box = tk.Tk()
        box.withdraw()
        messagebox.showerror(
            "Darkstory Calculator หยุดทำงาน",
            "เกิดข้อผิดพลาดที่ทำให้เปิดโปรแกรมไม่ได้:\n\n%s: %s\n\n"
            "รายละเอียดทั้งหมดอยู่ในไฟล์\n%s" % (type(exc).__name__, exc, LOG_PATH))
        box.destroy()
    except Exception:
        pass


def main():
    setup_logging()
    log.info("เริ่มโปรแกรม v%s (frozen=%s)", CURRENT_VERSION,
             bool(getattr(sys, "frozen", False)))

    try:
        problems = gd.validate_tables()
        for problem in problems:
            log.error("ตารางผิดปกติ: %s", problem)

        enable_dpi_awareness()
        root = tk.Tk()
        app = DarkstoryApp(root, load_config())

        # ดัก exception ที่หลุดออกมาจาก callback ของ Tk ให้ลง log แทนที่จะหายเงียบ
        root.report_callback_exception = lambda *exc: log.error(
            "exception ใน callback", exc_info=exc)

        if problems:
            messagebox.showwarning(
                "ข้อมูลตารางผิดปกติ",
                "ตรวจพบความผิดปกติในตารางข้อมูลเกม %d จุด\n"
                "ผลการคำนวณอาจไม่ถูกต้อง (รายละเอียดใน darkstory.log)\n\n%s"
                % (len(problems), "\n".join("• " + p for p in problems[:5])))

        root.mainloop()
    except Exception as exc:
        report_fatal(exc)
        raise SystemExit(1)
    log.info("ปิดโปรแกรม")


if __name__ == "__main__":
    main()
