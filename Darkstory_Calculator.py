# -*- coding: utf-8 -*-
"""Darkstory Calculator — เครื่องคิดเลขต้นทุนไอเทมเกม Darkstory

ตารางข้อมูลเกมและฟังก์ชันคำนวณอยู่ใน game_data.py
ลิงก์ Google Apps Script อยู่ใน darkstory_config.json (ไม่ฝังไว้ในโค้ด)

ใช้เฉพาะ standard library — ไม่ต้องติดตั้งอะไรเพิ่ม
"""

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
        self.mat_blue_price = 0.0

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
        self.load_btn = ttk.Button(toolbar, text="🔄  โหลดข้อมูลจากเซิร์ฟเวอร์",
                                   style="Gold.TButton", command=self.load_from_server)
        self.load_btn.pack(side=tk.RIGHT)
        ttk.Label(toolbar, style="Dim.TLabel",
                  text="ข้อมูลราคาซิงก์กับ Google Sheet ของกิลด์").pack(
            side=tk.LEFT, pady=(6, 0))

        nb = ttk.Notebook(self.body)
        nb.pack(fill=tk.BOTH, expand=True)
        self.nb = nb
        self._build_currency_tab(nb)
        self._build_items_tab(nb)
        self._build_materials_tab(nb)
        self._build_calc_tab(nb)

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
        self._ver_item = canvas.create_text(
            22, 48, anchor="w", text="เครื่องคิดเลขไอเทม  v%s" % CURRENT_VERSION,
            font="ds.small", fill=p["text_dim"])

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
        banner_h = max(72, title_h + small_h + 30)
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

        title_y = banner_h * 0.34
        canvas.coords(self._title_item, 22, title_y)
        canvas.coords(self._ver_item, 22, title_y + self.fonts.fonts["ds.title"]
                      .metrics("linespace") * 0.85)
        canvas.tag_raise(self._title_item)
        canvas.tag_raise(self._ver_item)

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
        listing.rowconfigure(0, weight=1)
        listing.columnconfigure(0, weight=1)

        self.item_tree = ttk.Treeview(listing, columns=("name", "price", "thb"),
                                      show="headings", height=8)
        for col, text, width, anchor in (("name", "ชื่อไอเทม", 220, "w"),
                                         ("price", "ทอง", 120, "e"),
                                         ("thb", "บาท", 120, "e")):
            self.item_tree.heading(col, text=text)
            self.item_tree.column(col, width=width, anchor=anchor, stretch=(col == "name"))
        self.item_tree.grid(row=0, column=0, sticky="nsew")
        self.item_tree.bind("<Delete>", lambda e: self.delete_item())
        self.item_tree.bind("<Double-1>", self._on_tree_double_click)
        self.item_tree.bind("<Return>", lambda e: self.edit_price())

        bar = ttk.Scrollbar(listing, orient=tk.VERTICAL, command=self.item_tree.yview)
        bar.grid(row=0, column=1, sticky="ns")
        self.item_tree.configure(yscrollcommand=bar.set)

        bottom = ttk.Frame(listing, style="Card.TFrame")
        bottom.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.item_count = ttk.Label(bottom, text="0 รายการ", style="CardDim.TLabel")
        self.item_count.pack(side=tk.LEFT)
        self.save_items_btn = ttk.Button(bottom, text="💾  บันทึกไอเทม",
                                         style="Gold.TButton", command=self.save_items)
        self.save_items_btn.pack(side=tk.RIGHT)

    def _build_materials_tab(self, nb):
        p = theme.PALETTE
        tab = ttk.Frame(nb, padding=12)
        nb.add(tab, text="⚒️  วัสดุ")

        # --- การ์ดหินดั้งเดิม: ตัวเดียวที่มีมูลค่าเป็นเหรียญทอง ---
        blue_card, blue = theme.card(
            tab, "หินดั้งเดิม", accent=p["info"],
            subtitle="ชิ้นส่วนหินดั้งเดิม %d ชิ้น  =  หินดั้งเดิม 1 ก้อน"
                     % MATERIAL_BLUE_RATIO)
        blue_card.pack(fill=tk.X, pady=(0, 12))
        blue.columnconfigure(1, weight=1)

        ttk.Label(blue, style="Ok.Card.TLabel",
                  text="✔  หินดั้งเดิม ซื้อขายด้วยเหรียญทองได้").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 2))
        ttk.Label(blue, style="Locked.TLabel",
                  text="🔒  ชิ้นส่วนหินดั้งเดิม ซื้อขายไม่ได้ ต้องหลอมรวมก่อน").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ttk.Label(blue, text="ราคาหินดั้งเดิม (ทอง/ก้อน)", style="Field.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w")
        self.blue_price = ttk.Entry(blue)
        self.blue_price.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 4))
        self.blue_price.bind("<KeyRelease>", self.upd_blue)
        self.blue_label = ttk.Label(blue, text="—", style="CardDim.TLabel")
        self.blue_label.grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ttk.Label(blue, text="มีชิ้นส่วนหินดั้งเดิมกี่ชิ้น", style="Field.TLabel").grid(
            row=5, column=0, columnspan=2, sticky="w")
        self.blue_amt = ttk.Entry(blue)
        self.blue_amt.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(2, 6))
        self.blue_amt.bind("<KeyRelease>", self.calc_blue)

        self.blue_res = ttk.Label(blue, text="หลอมได้: —", style="Info.Card.TLabel")
        self.blue_res.grid(row=7, column=0, columnspan=2, sticky="w")
        self.blue_value = ttk.Label(blue, text="", style="Value.TLabel")
        self.blue_value.grid(row=8, column=0, columnspan=2, sticky="w", pady=(2, 0))

        # --- การ์ดพลอยสีแดงเข้ม: ซื้อขายไม่ได้ จึงไม่มีช่องราคา ---
        red_card, red = theme.card(
            tab, "พลอยสีแดงเข้ม", accent=p["danger"],
            subtitle="ชิ้นส่วนหินดั้งเดิมแดง %d ชิ้น  =  พลอยสีแดงเข้ม 1 เม็ด"
                     % MATERIAL_RED_RATIO)
        red_card.pack(fill=tk.X, pady=(0, 12))
        red.columnconfigure(1, weight=1)

        ttk.Label(red, style="Locked.TLabel",
                  text="🔒  ซื้อขายไม่ได้ทั้งคู่ ใช้เหรียญทองซื้อขายไม่ได้ "
                       "จึงไม่มีราคาให้กรอก").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ttk.Label(red, text="มีชิ้นส่วนหินดั้งเดิมแดงกี่ชิ้น", style="Field.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w")
        self.red_amt = ttk.Entry(red)
        self.red_amt.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(2, 6))
        self.red_amt.bind("<KeyRelease>", self.calc_red)
        self.red_res = ttk.Label(red, text="หลอมได้: —", style="Danger.Card.TLabel")
        self.red_res.grid(row=3, column=0, columnspan=2, sticky="w")

        self.save_mats_btn = ttk.Button(tab, text="💾  บันทึกราคาหินดั้งเดิม",
                                        style="Gold.TButton", command=self.save_mats)
        self.save_mats_btn.pack(pady=(4, 0))

    def _build_calc_tab(self, nb):
        p = theme.PALETTE
        tab = ttk.Frame(nb, padding=12)
        nb.add(tab, text="📊  ตีบวก")
        tab.rowconfigure(1, weight=1)
        tab.columnconfigure(0, weight=1)

        form_card, form = theme.card(tab, "ตั้งค่าการตีบวก", accent=p["gold"])
        form_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        for col in (1, 3):
            form.columnconfigure(col, weight=1)

        levels = [str(i) for i in range(MIN_LEVEL, MAX_LEVEL + 1)]

        def field(row, col, text, widget):
            ttk.Label(form, text=text, style="Field.TLabel").grid(
                row=row, column=col, sticky="w", padx=(0 if col == 0 else 10, 0))
            widget.grid(row=row + 1, column=col, sticky="ew", pady=(2, 8),
                        padx=(0 if col == 0 else 10, 0))

        self.st = ttk.Combobox(form, values=levels, state="readonly", width=6)
        self.st.set("1")
        field(0, 0, "จากระดับ", self.st)

        self.en = ttk.Combobox(form, values=levels, state="readonly", width=6)
        self.en.set("10")
        field(0, 1, "ถึงระดับ", self.en)

        self.gr = ttk.Combobox(form, values=GRADES, state="readonly", width=10)
        self.gr.set(GRADES[0])
        self.gr.bind("<<ComboboxSelected>>", self.on_mode_change)
        field(2, 0, "เกรดไอเทม", self.gr)

        self.inh = ttk.Combobox(form, values=INHERIT_MODES, state="readonly", width=14)
        self.inh.set(INHERIT_NONE)
        self.inh.bind("<<ComboboxSelected>>", self.on_mode_change)
        field(2, 1, "การสืบทอด", self.inh)

        self.tgr = ttk.Combobox(form, values=GRADES, state="readonly", width=10)
        self.tgr.set(GRADES[0])
        field(4, 0, "เกรดเป้าหมาย", self.tgr)

        ttk.Button(form, text="🧮  คำนวณ", style="Gold.TButton",
                   command=self.calc_all).grid(row=5, column=1, sticky="ew",
                                               padx=(10, 0), pady=(2, 8))

        result_card, result = theme.card(tab, "ผลการคำนวณ", accent=p["info"])
        result_card.grid(row=1, column=0, sticky="nsew")
        result.rowconfigure(0, weight=1)
        result.columnconfigure(0, weight=1)

        self.txt = tk.Text(result, height=12, wrap="none", font="ds.mono",
                           state="disabled", relief="flat", padx=10, pady=8,
                           bg=p["panel"], fg=p["text"],
                           insertbackground=p["gold"], selectbackground=p["border"],
                           highlightthickness=1, highlightbackground=p["line"],
                           highlightcolor=p["line"])
        self.txt.grid(row=0, column=0, sticky="nsew")
        bar = ttk.Scrollbar(result, orient=tk.VERTICAL, command=self.txt.yview)
        bar.grid(row=0, column=1, sticky="ns")
        self.txt.configure(yscrollcommand=bar.set)

        self.on_mode_change()

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
        self.upd_red()
        self.upd_blue()
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
        self.upd_tree()
        self.set_status("เพิ่ม '%s' แล้ว (ยังไม่ได้บันทึกขึ้นเซิร์ฟเวอร์)" % name)

    def _selected_index(self):
        """ตำแหน่งของแถวที่เลือกใน self.items คืน None ถ้าไม่ได้เลือกหรือเลือกหลายแถว"""
        selected = self.item_tree.selection()
        if len(selected) != 1:
            return None
        index = self.item_tree.index(selected[0])
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
        children = self.item_tree.get_children()
        if index < len(children):
            self.item_tree.selection_set(children[index])
            self.item_tree.see(children[index])

        self.set_status("แก้ราคา '%s': %s → %s ทอง (ยังไม่ได้บันทึก)"
                        % (item["name"], money(old_price), money(new_price)))

    def delete_item(self):
        selected = self.item_tree.selection()
        if not selected:
            messagebox.showinfo("แจ้งเตือน", "เลือกแถวที่ต้องการลบก่อน")
            return
        indexes = sorted((self.item_tree.index(iid) for iid in selected), reverse=True)
        for index in indexes:
            if 0 <= index < len(self.items):
                del self.items[index]
        self.items_dirty = True
        self.upd_tree()
        self.set_status("ลบ %d รายการแล้ว (ยังไม่ได้บันทึก)" % len(indexes))

    def upd_tree(self):
        self.item_tree.delete(*self.item_tree.get_children())
        for item in self.items:
            self.item_tree.insert("", tk.END, values=(
                item["name"],
                money(item["price"]),
                money(item["price"] * self.rate_gold_thb),
            ))
        suffix = " • ยังไม่ได้บันทึก" if self.items_dirty else ""
        self.item_count.config(text="%d รายการ%s" % (len(self.items), suffix))

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

    # ---------------- แท็บวัสดุ ----------------

    def upd_red(self, event=None):
        """พลอยสีแดงเข้มซื้อขายไม่ได้ จึงไม่มีราคา เหลือแค่คำนวณจำนวน"""
        self.calc_red()

    def upd_blue(self, event=None):
        text = self.blue_price.get().strip()
        if not text:
            self.blue_label.config(text="—", foreground="")
        else:
            value = parse_num(text, None)
            if value is None or value < 0:
                # เก็บราคาเดิมไว้ และอย่าโชว์ตัวเลข เพื่อไม่ให้อ่านเป็นคำตอบ
                self.blue_price.config(foreground=theme.PALETTE["danger"])
                self.blue_label.config(
                    text="ราคาไม่ถูกต้อง — ยังใช้ %s ทองอยู่" % money(self.mat_blue_price),
                    foreground=theme.PALETTE["danger"])
                self.calc_blue()
                return
            self.blue_price.config(foreground="")
            self.mat_blue_price = value
            self.blue_label.config(
                text="= %s บาท/ก้อน   •   คิดเป็นชิ้นส่วนละ %s ทอง (นับเป็นทุนได้ "
                     "แม้ขายไม่ได้)"
                     % (money(value * self.rate_gold_thb),
                        money(value / MATERIAL_BLUE_RATIO)),
                foreground="")
        self.calc_blue()

    def calc_red(self, event=None):
        text = self.red_amt.get().strip()
        if not text:
            self.red_res.config(text="หลอมได้: —")
            return
        amount = parse_count(text, None)
        if amount is None:
            self.red_res.config(text="หลอมได้: — (จำนวนไม่ถูกต้อง)")
            return
        whole, left = gd.melt(amount, MATERIAL_RED_RATIO)
        self.red_res.config(
            text="หลอมได้ %s เม็ด  +  เศษ %d ชิ้น  •  ไม่มีมูลค่าเป็นเหรียญทอง"
                 % ("{:,}".format(whole), left))

    def calc_blue(self, event=None):
        text = self.blue_amt.get().strip()
        if not text:
            self.blue_res.config(text="หลอมได้: —")
            self.blue_value.config(text="")
            return
        amount = parse_count(text, None)
        if amount is None:
            self.blue_res.config(text="หลอมได้: — (จำนวนไม่ถูกต้อง)")
            self.blue_value.config(text="")
            return
        whole, left = gd.melt(amount, MATERIAL_BLUE_RATIO)
        self.blue_res.config(
            text="หลอมได้ %s ก้อน  +  เศษ %d ชิ้น"
                 % ("{:,}".format(whole), left))
        if self.mat_blue_price > 0:
            # เศษที่หลอมไม่ครบก็เป็นทุน คิดตามสัดส่วนไม่ปัดทิ้ง
            total = gd.pieces_value(amount, self.mat_blue_price, MATERIAL_BLUE_RATIO)
            self.blue_value.config(
                text="%s ทอง  =  %s บาท" % (money(total),
                                            money(total * self.rate_gold_thb)))
        else:
            self.blue_value.config(text="")

    def save_mats(self):
        text = self.blue_price.get().strip()
        value = parse_num(text, None)
        if text and (value is None or value < 0):
            messagebox.showwarning("แจ้งเตือน",
                                   "ราคาหินดั้งเดิมกรอกไม่ถูกต้อง แก้ให้เรียบร้อยก่อนบันทึก")
            return
        if not self._confirm_overwrite("materials", 1):
            return
        # บันทึกเฉพาะหินดั้งเดิม — พลอยสีแดงเข้มซื้อขายไม่ได้ จึงไม่มีราคาให้เก็บ
        rows = [["name", "price_gold_per_unit"],
                [gd.BLUE_UNIT, self.mat_blue_price]]
        self._push("materials", rows, "บันทึกราคาหินดั้งเดิมแล้ว",
                   on_success=self._save_local)

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

    def _write_result(self, text):
        self.txt.config(state="normal")
        self.txt.delete("1.0", tk.END)
        self.txt.insert(tk.END, text)
        self.txt.config(state="disabled")

    def calc_all(self):
        self._write_result("")          # อย่าให้รายงานเก่าค้างเป็นคำตอบของ input ใหม่

        if self.mat_blue_price <= 0:
            messagebox.showwarning(
                "แจ้งเตือน",
                "กรุณาใส่ราคาหินดั้งเดิมในแท็บ ⚒️ วัสดุ ก่อน\n"
                "ไม่งั้นมูลค่าวัสดุจะออกมาเป็น 0 ซึ่งไม่ใช่ราคาจริง")
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
            messagebox.showwarning("แจ้งเตือน", "กรุณาเลือกค่าจากรายการให้ครบ")
            return
        except CalcError as exc:
            messagebox.showwarning("แจ้งเตือน", str(exc))
            return

        # เศษที่หลอมไม่ครบก็เป็นทุน จึงคิดตามสัดส่วน ไม่ปัดขึ้นและไม่ปัดทิ้ง
        stones, leftover = gd.melt(pieces, MATERIAL_BLUE_RATIO)
        material_gold = gd.pieces_value(pieces, self.mat_blue_price,
                                        MATERIAL_BLUE_RATIO)
        total_gold = material_gold + inherit
        result_level = (gd.HIGHER_RESULT_LEVEL.get(end)
                        if mode == gd.INHERIT_MODE_HIGHER else end)

        if mode == INHERIT_NONE:
            grade_line = "เกรด %s (ไม่สืบทอด)" % GRADES[grade_index]
        else:
            grade_line = "เกรด %s → %s (%s)" % (
                GRADES[grade_index], GRADES[target_index], mode)

        w = 58
        rule = "─" * w
        out = [
            "  ตี +%d  →  +%d" % (start, end),
            "  %s" % grade_line,
            rule,
        ]
        if mode == gd.INHERIT_MODE_HIGHER and result_level is not None:
            # สืบทอดข้ามเกรดแล้วระดับตีบวกจะลดลง ต้องบอกให้เห็นก่อนตัดสินใจ
            out += ["  ⚠ หลังสืบทอดข้ามเกรด อุปกรณ์จะเหลือ +%d (จาก +%d)"
                    % (result_level, end), rule]
        out += [
            "",
            "  วัสดุที่ต้องใช้",
            "    %s" % gd.BLUE_PIECE,
            "        {:>16,} ชิ้น   (ซื้อขายไม่ได้)".format(pieces),
            "    หลอมรวมเป็น {}".format(gd.BLUE_UNIT),
            "        {:>16,} ก้อน  + เศษ {} ชิ้น".format(stones, leftover),
            "",
            rule,
            "  มูลค่าหินดั้งเดิม  {:>16} ทอง".format(money(material_gold)),
            "                    {:>16} บาท".format(
                money(material_gold * self.rate_gold_thb)),
            "",
            "  ค่าสืบทอด         {:>16} ทอง".format(money(inherit)),
            "                    {:>16} บาท".format(
                money(inherit * self.rate_gold_thb)),
            rule,
            "  รวมทั้งหมด        {:>16} ทอง".format(money(total_gold)),
            "                    {:>16} บาท".format(
                money(total_gold * self.rate_gold_thb)),
            rule,
            "",
            "  หมายเหตุ",
            "    • คิดราคาจาก %s ก้อนละ %s ทอง" % (gd.BLUE_UNIT,
                                                       money(self.mat_blue_price)),
            "      เศษที่หลอมไม่ครบก็นับเป็นทุนตามสัดส่วนด้วย",
            "    • %s และ %s ซื้อขายไม่ได้" % (gd.RED_PIECE, gd.RED_UNIT),
            "      จึงไม่มีมูลค่าเป็นเหรียญทอง",
            "    • เรตที่ใช้ 1 ทอง = %s บาท" % self.rate_gold_thb,
        ]
        self._write_result("\n".join(out))
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
            for row in rows:
                price = to_num(row.get("price_gold_per_unit"), None)
                if price is None or price < 0:
                    continue
                # แถวพลอยสีแดงเข้มในชีตเก่าถูกข้าม — วัสดุนั้นซื้อขายไม่ได้
                if row.get("name") == gd.BLUE_UNIT:
                    self.mat_blue_price = price
                    self._set_entry(self.blue_price, str(price))

    # ---------------- เก็บข้อมูลในเครื่อง ----------------

    def _load_local(self):
        data = read_json(LOCAL_PATH, {})
        rate = to_num(data.get("rate_gold_thb"), None)
        if rate and rate > 0:
            self.rate_gold_thb = rate
        self.mat_blue_price = to_num(data.get("mat_blue_price"), 0.0) or 0.0
        for row in data.get("items", []) if isinstance(data.get("items"), list) else []:
            if isinstance(row, dict) and row.get("name"):
                price = to_num(row.get("price"), None)
                if price is not None:
                    self.items.append({"name": str(row["name"]), "price": price})

    def _save_local(self):
        write_json(LOCAL_PATH, {
            "rate_gold_thb": self.rate_gold_thb,
            "mat_blue_price": self.mat_blue_price,
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
