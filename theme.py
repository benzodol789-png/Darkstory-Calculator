# -*- coding: utf-8 -*-
"""ธีมหน้าตาโปรแกรม Darkstory Calculator

รวมทุกอย่างที่เกี่ยวกับ "หน้าตา" ไว้ที่เดียว เพื่อให้ไฟล์หลักเหลือแต่ตรรกะ:
  PALETTE        สีที่ดูดมาจากภาพพื้นหลังของเกมจริง
  Fonts          ฟอนต์ที่ย่อ/ขยายตามขนาดหน้าต่าง
  apply_theme()  ตั้งสไตล์ ttk ทั้งหมดให้เป็นโทนมืด
  Backdrop       ผืนผ้าใบที่วาดรูปพื้นหลัง + แผงโค้งมน
  RoundedWindow  หน้าต่างไร้ขอบมุมโค้ง พร้อม title bar และการย่อ/ขยาย/ลากที่ทำเอง

หมายเหตุ: มุมโค้งของหน้าต่างบน Windows 10 ทำด้วย SetWindowRgn เอง
เพราะ DWM รองรับมุมโค้ง native เฉพาะ Windows 11 (build 22000 ขึ้นไป)
"""

import glob
import os
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageTk
    HAVE_PIL = True
except ImportError:                                   # pragma: no cover
    HAVE_PIL = False


# ---------------------------------------------------------------------------
# สี — โทนน้ำเงินเข้ม/ฟ้าเรืองแสง ตาม UI ในเกม Darkstory
#
# หมายเหตุชื่อคีย์: "gold*" ไม่ได้แปลว่าสีทองแล้ว มันคือ "สีเน้นหลัก" ของธีม
# (ตอนนี้เป็นฟ้าเรืองแสง) คงชื่อเดิมไว้เพราะมีชื่อ ttk style ผูกอยู่ด้วย
# เช่น "Gold.TButton" ซึ่ง ttk จะ fallback เงียบๆ ถ้าเปลี่ยนชื่อแล้วตกหล่น
# ---------------------------------------------------------------------------
PALETTE = {
    "void":      "#05090f",   # นอกสุด (เห็นตอนมุมโค้ง) + พื้นแถบสถานะ
    "base":      "#0b1421",   # พื้นแผงหลัก
    "panel":     "#122032",   # แผงย่อย / พื้นช่องกรอก
    "panel_hi":  "#1c3048",   # แถวที่ถูกเลือก / hover
    "card":      "#16243a",   # การ์ดเนื้อหา (สว่างกว่าพื้น = ลอยขึ้นมา)
    "card_lo":   "#040810",   # เงาใต้การ์ด
    "card_hi":   "#2e5175",   # ขอบบนการ์ด (แสงตกกระทบ)
    "line":      "#27405c",   # เส้นคั่น
    "border":    "#35618c",   # ขอบแผง / พื้นแถบที่ถูกเลือก
    "gold":      "#4fd6f7",   # สีเน้นหลัก — ฟ้าเรืองแสงจากกรอบไอเทมในเกม
    "gold_hi":   "#b8f0ff",   # ฟ้าสว่าง ใช้กับตัวหนังสือที่ต้องเด่นสุด
    "gold_lo":   "#1d7fa3",   # ฟ้าเข้ม ใช้ทำเงาปุ่มตอนกด
    "text":      "#e4eefa",   # ตัวหนังสือหลัก (ขาวอมฟ้า)
    "text_dim":  "#8aa2bd",   # ตัวหนังสือรอง
    "accent":    "#a87bff",   # ม่วง — จากกรอบรูนในเกม
    "danger":    "#ff6b7a",
    "ok":        "#4ade80",
    "info":      "#6ea8ff",   # น้ำเงินสด — ต้องแยกจาก gold ที่เป็นฟ้าให้ออก
    "locked":    "#6f8296",   # เทาอมฟ้า สำหรับของที่ซื้อขายไม่ได้
    "titlebar":  "#0d1826",   # แถบหัวโปรแกรม
    "tint":      "#071018",   # ฟิล์มที่ blend ทับภาพพื้นหลังให้เป็นโทนน้ำเงิน
}

# สีประจำแท็บ — แถบเน้นหัวการ์ด ให้แต่ละแท็บแยกกันด้วยสายตา
TAB_ACCENTS = ["#4fd6f7", "#4ade80", "#ffc861", "#a87bff", "#ff6b7a"]

CORNER_RADIUS = 18        # มุมโค้งของหน้าต่าง
PANEL_RADIUS = 14         # มุมโค้งของแผงข้างใน
MIN_W, MIN_H = 560, 680   # แนวตั้ง — แคบแต่สูง
EDGE = 6                  # ความหนาของขอบที่ลากย่อ/ขยายได้


def asset(pattern):
    """หาไฟล์รูปทั้งตอนรันจาก .py และตอนอยู่ใน .exe ที่ PyInstaller แตกไว้"""
    roots = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        roots.append(base)
    if getattr(sys, "frozen", False):
        roots.append(os.path.dirname(sys.executable))
    roots.append(os.path.dirname(os.path.abspath(__file__)))
    for root in roots:
        found = sorted(glob.glob(os.path.join(root, pattern)))
        if found:
            return found[0]
    return None


# ---------------------------------------------------------------------------
# ฟอนต์
# ---------------------------------------------------------------------------

# ฟอนต์ที่วาดภาษาไทยได้สวยบน Windows เรียงตามความชอบ
THAI_FAMILIES = ["Leelawadee UI", "Leelawadee", "Tahoma", "Segoe UI"]
MONO_FAMILIES = ["Consolas", "Courier New"]

# ชื่อฟอนต์ -> (ขนาดฐาน, ตัวหนา, ใช้ฟอนต์ monospace ไหม)
FONT_SPEC = {
    "ds.body":    (10, False, False),
    "ds.small":   (9,  False, False),
    "ds.bold":    (10, True,  False),
    "ds.title":   (14, True,  False),
    "ds.heading": (12, True,  False),   # หัวข้อในการ์ด — หนาและใหญ่กว่าเนื้อชัดเจน
    "ds.label":   (10, True,  False),   # ป้ายกำกับช่องกรอก
    "ds.big":     (16, True,  False),   # ตัวเลขผลลัพธ์ที่ต้องเด่น
    "ds.chance":  (30, True,  False),   # ตัวเลขโอกาสสำเร็จ — ใหญ่สุดในโปรแกรม
    "ds.mono":    (10, False, True),
}


class Fonts:
    """สร้างฟอนต์ที่มีชื่อ แล้วปรับขนาดทีเดียวพร้อมกันได้ตอนหน้าต่างเปลี่ยนขนาด

    widget ที่อ้างฟอนต์ด้วย "ชื่อ" จะอัปเดตตามเองอัตโนมัติ ไม่ต้องไล่ตั้งทีละตัว
    """

    def __init__(self, root):
        available = set(tkfont.families(root))
        self.family = next((f for f in THAI_FAMILIES if f in available), "Tahoma")
        self.mono = next((f for f in MONO_FAMILIES if f in available), "Courier New")
        self.scale = 1.0
        self.fonts = {}
        for name, (size, bold, mono) in FONT_SPEC.items():
            self.fonts[name] = tkfont.Font(
                root=root, name=name,
                family=self.mono if mono else self.family,
                size=size, weight="bold" if bold else "normal")

    def rescale(self, width, height):
        """คิดตัวคูณจากขนาดหน้าต่าง แล้วปรับทุกฟอนต์ คืน True ถ้ามีการเปลี่ยน

        อิงด้านที่ 'คับ' กว่า เพื่อไม่ให้ตัวหนังสือโตจนล้นตอนหน้าต่างเตี้ยแต่กว้าง
        """
        scale = min(width / 1000.0, height / 700.0)
        scale = max(0.85, min(scale, 1.6))
        if abs(scale - self.scale) < 0.04:
            return False
        self.scale = scale
        for name, (size, _bold, _mono) in FONT_SPEC.items():
            self.fonts[name].configure(size=max(8, int(round(size * scale))))
        return True

    def row_height(self):
        return int(self.fonts["ds.body"].metrics("linespace") * 1.6)


# ---------------------------------------------------------------------------
# สไตล์ ttk
# ---------------------------------------------------------------------------

def apply_theme(root, fonts):
    """ตั้งสไตล์ ttk ทั้งหมดให้เป็นโทนมืดของเกม คืนตัว Style"""
    style = ttk.Style(root)
    style.theme_use("clam")          # clam ยอมให้เปลี่ยนสีได้มากที่สุด
    p = PALETTE

    root.configure(bg=p["void"])

    style.configure(".", background=p["base"], foreground=p["text"],
                    fieldbackground=p["panel"], font="ds.body",
                    borderwidth=0, focuscolor=p["gold"])

    style.configure("TFrame", background=p["base"])
    style.configure("Panel.TFrame", background=p["panel"])
    style.configure("Title.TFrame", background=p["titlebar"])

    # การ์ด — ใช้ relief raised ของ clam ที่วาดขอบสว่างด้านบนซ้ายและเงาด้านล่างขวา
    # ทำให้ดูนูนขึ้นมาจากพื้นจริงๆ ไม่ใช่แค่กล่องสี
    style.configure("Card.TFrame", background=p["card"], relief="raised",
                    borderwidth=2, lightcolor=p["card_hi"], darkcolor=p["card_lo"],
                    bordercolor=p["card_lo"])
    style.configure("Sunken.TFrame", background=p["panel"], relief="sunken",
                    borderwidth=1, lightcolor=p["card_lo"], darkcolor=p["card_hi"],
                    bordercolor=p["line"])

    style.configure("TLabel", background=p["base"], foreground=p["text"])
    style.configure("Card.TLabel", background=p["card"], foreground=p["text"])
    style.configure("Panel.TLabel", background=p["panel"], foreground=p["text"])
    style.configure("Dim.TLabel", background=p["base"], foreground=p["text_dim"],
                    font="ds.small")
    style.configure("CardDim.TLabel", background=p["card"], foreground=p["text_dim"],
                    font="ds.small")
    style.configure("Field.TLabel", background=p["card"], foreground=p["text"],
                    font="ds.label")
    style.configure("Heading.TLabel", background=p["card"], foreground=p["gold_hi"],
                    font="ds.heading")
    style.configure("Value.TLabel", background=p["card"], foreground=p["gold"],
                    font="ds.big")
    style.configure("Locked.TLabel", background=p["card"], foreground=p["locked"],
                    font="ds.small")
    style.configure("Title.TLabel", background=p["titlebar"], foreground=p["gold_hi"],
                    font="ds.title")

    # ป้ายบอกผลลัพธ์ในการ์ด แยกสีตามความหมาย
    for name, colour in (("Gold", p["gold"]), ("Info", p["info"]),
                         ("Ok", p["ok"]), ("Danger", p["danger"])):
        style.configure("%s.Card.TLabel" % name, background=p["card"],
                        foreground=colour, font="ds.bold")

    # ปุ่มนูน — ขอบบนสว่าง ขอบล่างเงา แล้วสลับตอนกดให้ดูยุบลงไป
    style.configure("TButton", background=p["panel_hi"], foreground=p["text"],
                    borderwidth=2, relief="raised", padding=(14, 7), font="ds.bold",
                    lightcolor=p["card_hi"], darkcolor=p["card_lo"],
                    bordercolor=p["line"])
    style.map("TButton",
              background=[("pressed", p["line"]), ("active", p["border"])],
              foreground=[("active", p["gold_hi"])],
              relief=[("pressed", "sunken")],
              lightcolor=[("pressed", p["card_lo"])],
              darkcolor=[("pressed", p["card_hi"])])

    style.configure("Gold.TButton", background=p["border"], foreground=p["gold_hi"],
                    lightcolor=p["gold"], darkcolor=p["gold_lo"])
    style.map("Gold.TButton",
              background=[("pressed", p["gold_lo"]), ("active", p["gold"])],
              foreground=[("active", p["void"])],
              relief=[("pressed", "sunken")],
              lightcolor=[("pressed", p["gold_lo"])], darkcolor=[("pressed", p["gold"])])

    style.configure("Chrome.TButton", background=p["titlebar"], foreground=p["text_dim"],
                    padding=(10, 2), relief="flat", font="ds.bold")
    style.map("Chrome.TButton",
              background=[("active", p["line"])], foreground=[("active", p["gold_hi"])])
    style.configure("Close.TButton", background=p["titlebar"], foreground=p["text_dim"],
                    padding=(10, 2), relief="flat", font="ds.bold")
    style.map("Close.TButton",
              background=[("active", p["danger"])], foreground=[("active", p["text"])])

    style.configure("TEntry", fieldbackground=p["panel"], foreground=p["text"],
                    insertcolor=p["gold"], borderwidth=1, relief="flat",
                    padding=5, bordercolor=p["line"])
    style.map("TEntry", bordercolor=[("focus", p["gold"])])

    # Combobox แบบ readonly จะแสดงข้อความเป็น "ที่ถูกเลือก" ตลอดเวลา
    # ถ้าไม่ตั้ง selectbackground จะได้แถบน้ำเงินสว่างของระบบทับอยู่
    style.configure("TCombobox", fieldbackground=p["panel"], background=p["panel_hi"],
                    foreground=p["text"], arrowcolor=p["gold"],
                    selectbackground=p["panel"], selectforeground=p["text"],
                    borderwidth=1, bordercolor=p["line"], padding=4,
                    lightcolor=p["panel"], darkcolor=p["panel"])
    style.map("TCombobox",
              fieldbackground=[("readonly", p["panel"]), ("disabled", p["base"])],
              background=[("readonly", p["panel_hi"]), ("active", p["border"])],
              foreground=[("readonly", p["text"]), ("disabled", p["text_dim"])],
              selectbackground=[("readonly", p["panel"])],
              selectforeground=[("readonly", p["text"])],
              arrowcolor=[("disabled", p["line"]), ("active", p["gold_hi"])],
              bordercolor=[("focus", p["gold"])],
              lightcolor=[("focus", p["gold"])], darkcolor=[("focus", p["gold"])])
    # รายการที่ dropdown ของ Combobox เป็น widget ของ Tk ไม่ใช่ ttk ต้องตั้งผ่าน option
    root.option_add("*TCombobox*Listbox.background", p["panel"])
    root.option_add("*TCombobox*Listbox.foreground", p["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", p["border"])
    root.option_add("*TCombobox*Listbox.selectForeground", p["gold_hi"])

    style.configure("Treeview", background=p["panel"], fieldbackground=p["panel"],
                    foreground=p["text"], borderwidth=0,
                    rowheight=fonts.row_height())
    style.map("Treeview",
              background=[("selected", p["border"])],
              foreground=[("selected", p["gold_hi"])])
    style.configure("Treeview.Heading", background=p["panel_hi"], foreground=p["gold"],
                    font="ds.bold", relief="flat", padding=6)
    style.map("Treeview.Heading", background=[("active", p["border"])])

    style.configure("TNotebook", background=p["base"], borderwidth=0, tabmargins=(2, 4, 2, 0))
    style.configure("TNotebook.Tab", background=p["panel"], foreground=p["text_dim"],
                    padding=(16, 8), font="ds.body", borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", p["border"]), ("active", p["panel_hi"])],
              foreground=[("selected", p["gold_hi"]), ("active", p["text"])],
              expand=[("selected", (0, 0, 0, 0))])

    style.configure("TSeparator", background=p["line"])
    style.configure("Vertical.TScrollbar", background=p["panel_hi"],
                    troughcolor=p["base"], borderwidth=0, arrowcolor=p["gold"])
    style.map("Vertical.TScrollbar", background=[("active", p["border"])])
    style.configure("Horizontal.TScrollbar", background=p["panel_hi"],
                    troughcolor=p["base"], borderwidth=0, arrowcolor=p["gold"])

    # ปิดล้อเมาส์ของ Combobox ทิ้ง — ค่าเริ่มต้นของ Tk คือหมุนล้อเหนือช่องแล้ว
    # "ค่าที่เลือกเปลี่ยน" ซึ่งอันตรายมากที่นี่ เพราะทุกช่องผูกกับ
    # <<ComboboxSelected>> ที่คำนวณใหม่ทั้งหน้า ผู้ใช้ตั้งใจจะเลื่อนหน้าเฉยๆ
    # แต่กลับได้ตัวเลขของค่าที่ไม่ได้เลือก และหน้าเลื่อนหนีจนไม่ทันเห็น
    root.unbind_class("TCombobox", "<MouseWheel>")

    style.configure("Status.TLabel", background=p["void"], foreground=p["text_dim"],
                    font="ds.small", padding=(10, 4))

    # เครดิตคนทำ มุมขวาล่าง — จางกว่าแถบสถานะ ให้เห็นแต่ไม่แย่งสายตา
    style.configure("Credit.TLabel", background=p["void"], foreground=p["line"],
                    font="ds.small", padding=(10, 4))

    # ปุ่มตัวเลือกในการ์ด — ต้องตั้ง background เอง ไม่งั้น clam ให้พื้นเทาตัดกับการ์ด
    style.configure("Card.TRadiobutton", background=p["card"], foreground=p["text"],
                    font="ds.bold", focuscolor=p["gold"])
    style.map("Card.TRadiobutton",
              background=[("active", p["card"])],
              foreground=[("active", p["gold_hi"]), ("selected", p["gold"])],
              indicatorcolor=[("selected", p["gold"]), ("!selected", p["panel"])])

    # ตัวเลขโอกาสสำเร็จ — ตัวใหญ่สุดในโปรแกรม เลียนแบบหน้าตีบวกในเกม
    style.configure("Chance.TLabel", background=p["card"], foreground=p["gold_hi"],
                    font="ds.chance")

    # แถบโอกาสสำเร็จในแท็บตีบวก
    style.configure("Chance.Horizontal.TProgressbar", troughcolor=p["panel"],
                    background=p["gold"], bordercolor=p["line"],
                    lightcolor=p["gold"], darkcolor=p["gold_lo"], thickness=14)
    return style


# ---------------------------------------------------------------------------
# พื้นหลัง
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# ไอคอนหินตามชั้น
#
# ในเกมหินแต่ละชั้นเป็นรูปเดียวกัน ต่างกันแค่สี ตัวโปรแกรมจึงวาดเองได้
# แต่ถ้าวางไฟล์รูปจริงจากเกมไว้ข้างโปรแกรม จะหยิบไปใช้แทนทันที
# ตั้งชื่อว่า stone_blue_0.png .. stone_blue_3.png และ stone_red_0.png ..
# ---------------------------------------------------------------------------

STONE_COLORS = {
    "blue": ["#3d7fa0", "#4fd6f7", "#8ae9ff", "#dff8ff"],
    "red":  ["#a03d55", "#ff6b7a", "#ff9ec4", "#ffd9ec"],
}

_icon_cache = {}


def _trim_border(img, tol=18):
    """ตัดขอบที่เป็นสีเดียวกับมุมภาพออก — รูปแคปจากเกมมักมีกรอบเกินมา"""
    w, h = img.size
    px = img.load()
    corner = px[0, 0]

    def same(a, b):
        if len(a) > 3 and a[3] < 12 and len(b) > 3 and b[3] < 12:
            return True             # โปร่งใสทั้งคู่ = ขอบเหมือนกัน
        return all(abs(a[i] - b[i]) <= tol for i in range(3))

    left, right, top, bottom = 0, w - 1, 0, h - 1
    while left < right and all(same(px[left, y], corner) for y in range(h)):
        left += 1
    while right > left and all(same(px[right, y], corner) for y in range(h)):
        right -= 1
    while top < bottom and all(same(px[x, top], corner) for x in range(w)):
        top += 1
    while bottom > top and all(same(px[x, bottom], corner) for x in range(w)):
        bottom -= 1
    if right - left < 4 or bottom - top < 4:
        return img                  # ตัดแล้วแทบไม่เหลือ แปลว่าเดาผิด เอาของเดิม
    return img.crop((left, top, right + 1, bottom + 1))


def _recolor(img, hue):
    """เปลี่ยนสีภาพไปเป็นเฉดเดียว โดยคงความสว่างและเงาเดิมไว้

    ในเกมหินแต่ละชั้นเป็นรูปเดียวกันต่างแค่สี จึงเอารูปสายแดงมาทำสายน้ำเงินได้
    hue เป็นสเกล 0-255 ของ PIL (ไม่ใช่ 0-360)
    """
    rgb = img.convert("RGB")
    h, s_ch, v = rgb.convert("HSV").split()
    h_px, s_px = h.load(), s_ch.load()
    w, ht = img.size
    for y in range(ht):
        for x in range(w):
            if s_px[x, y] > 40:     # เฉพาะส่วนที่มีสี ไม่แตะกรอบสีเทา/ดำ
                h_px[x, y] = hue
    out = Image.merge("HSV", (h, s_ch, v)).convert("RGBA")
    out.putalpha(img.split()[3] if img.mode == "RGBA"
                 else Image.new("L", img.size, 255))
    return out


# สายน้ำเงินใช้รูปของสายแดงมาเปลี่ยนสีได้ ถ้าไม่มีไฟล์ของตัวเอง
BLUE_HUE = 132          # ~186 องศา ฟ้าเรืองแสงแบบในเกม


def _load_stone_image(line, tier):
    """หาไฟล์รูปหิน คืน PIL Image ที่ตัดขอบแล้ว หรือ None ถ้าไม่มี"""
    path = asset("stone_%s_%d.*" % (line, tier))
    recolor_to = None
    if not path and line == "blue":
        # ไม่มีรูปสายน้ำเงินชั้นนี้ -> ยืมของสายแดงมาเปลี่ยนเป็นสีฟ้า
        path = asset("stone_red_%d.*" % tier)
        recolor_to = BLUE_HUE
    if not path:
        return None
    try:
        img = Image.open(path).convert("RGBA")
        img = _trim_border(img)
        if recolor_to is not None:
            img = _recolor(img, recolor_to)
        return img
    except Exception:
        return None                 # ไฟล์เสีย -> ให้ผู้เรียกไปวาดเอง


def stone_icon(line, tier, size=22):
    """ไอคอนหินชั้นหนึ่ง คืน PhotoImage หรือ None ถ้าไม่มี PIL

    ต้องเก็บผลลัพธ์ไว้ในตัวแปรที่ไม่ถูกเก็บกวาด ไม่งั้น Tk จะลบรูปทิ้ง
    ที่นี่ใช้ _icon_cache ถือไว้ให้แล้ว
    """
    root = tk._default_root
    if root is None or not HAVE_PIL:
        return None
    # ผูกคีย์กับ Tk ตัวที่สร้างรูป ไม่งั้นถ้ามี Tk ตัวใหม่จะได้รูปที่ใช้ไม่ได้
    # แล้วพังเป็น TclError: image "pyimageN" doesn't exist
    key = (id(root), line, tier, size)
    if key in _icon_cache:
        return _icon_cache[key]

    img = _load_stone_image(line, tier)
    if img is not None:
        img = img.resize((size, size), Image.LANCZOS)
        _icon_cache[key] = ImageTk.PhotoImage(img)
        return _icon_cache[key]

    ramp = STONE_COLORS.get(line, STONE_COLORS["blue"])
    color = ramp[min(tier, len(ramp) - 1)]

    scale = 4                          # วาดใหญ่แล้วย่อ ขอบจะได้เนียน
    box = size * scale
    img = Image.new("RGBA", (box, box), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = box // 8
    draw.rounded_rectangle((0, 0, box - 1, box - 1), radius=box // 5,
                           fill=PALETTE["panel"], outline=color,
                           width=max(2, scale))
    # เม็ดพลอยทรงสี่เหลี่ยมขนมเปียกปูนแบบในเกม
    cx = cy = box / 2.0
    r = (box - pad * 2) / 2.0
    draw.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)],
                 fill=color)
    # แสงสะท้อนมุมบนซ้าย ให้ดูเป็นผิวมันไม่ใช่สีแบน
    draw.polygon([(cx, cy - r * 0.85), (cx + r * 0.4, cy - r * 0.2),
                  (cx, cy), (cx - r * 0.4, cy - r * 0.2)],
                 fill=(255, 255, 255, 110))

    img = img.resize((size, size), Image.LANCZOS)
    _icon_cache[key] = ImageTk.PhotoImage(img)
    return _icon_cache[key]


def rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


class Backdrop:
    """Canvas ที่วาดรูปพื้นหลังเกม (ย่อ/ครอปให้เต็มหน้าต่าง) แล้วคลุมด้วยม่านมืด

    ม่านมืดจำเป็น เพราะภาพต้นฉบับมีตัวละครกลางจอ ถ้าวางตัวหนังสือทับตรงๆ จะอ่านไม่ออก
    """

    def __init__(self, parent, image_path, dim=0.72, blur=2):
        self.canvas = tk.Canvas(parent, highlightthickness=0, bd=0,
                                bg=PALETTE["base"])
        self.source = None
        self.dim = dim
        self.blur = blur
        self._photo = None
        self._item = None
        self._size = (0, 0)
        if HAVE_PIL and image_path and os.path.exists(image_path):
            try:
                self.source = Image.open(image_path).convert("RGB")
            except OSError:
                self.source = None

    def render(self, width, height, radius=0):
        """วาดพื้นหลังใหม่ให้พอดีขนาดที่ให้มา (aspect-fill แล้วครอปกลาง)"""
        if width < 2 or height < 2:
            return
        if (width, height) == self._size:
            return
        self._size = (width, height)

        if self.source is None:
            self.canvas.configure(bg=PALETTE["base"])
            return

        src = self.source
        scale = max(width / src.width, height / src.height)
        new = (max(1, int(src.width * scale)), max(1, int(src.height * scale)))
        img = src.resize(new, Image.LANCZOS)

        left = (new[0] - width) // 2
        top = (new[1] - height) // 2
        img = img.crop((left, top, left + width, top + height))

        if self.blur:
            img = img.filter(ImageFilter.GaussianBlur(self.blur))

        # ฟิล์มน้ำเงิน — ดึงภาพโทนทองเดิมให้เข้าธีม และทำให้ตัวหนังสืออ่านออกทุกจุด
        overlay = Image.new("RGB", img.size, PALETTE["tint"])
        img = Image.blend(img, overlay, self.dim)

        if radius:
            img.putalpha(rounded_mask(img.size, radius))
            img = img.convert("RGBA")

        self._photo = ImageTk.PhotoImage(img)
        if self._item is None:
            self._item = self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
        else:
            self.canvas.itemconfigure(self._item, image=self._photo)
        self.canvas.tag_lower(self._item)


class Banner:
    """แถบภาพแนวนอนสำหรับหัวโปรแกรม — ครอปเอาเฉพาะช่วงกลางของภาพที่มีตัวละคร

    ไล่เฉดให้จางลงทางขอบล่าง เพื่อให้กลืนกับพื้นหลังส่วนเนื้อหาแทนที่จะตัดเป็นเส้นตรง
    """

    def __init__(self, image_path, dim=0.45, focus=0.55):
        self.dim = dim
        self.focus = focus          # 0 = ครอปบนสุด, 1 = ครอปล่างสุด
        self.source = None
        self.photo = None           # ผู้เรียกเอาไปวางบน canvas เอง (โปร่งใสจริง)
        self._size = (0, 0)
        if HAVE_PIL and image_path and os.path.exists(image_path):
            try:
                self.source = Image.open(image_path).convert("RGB")
            except OSError:
                self.source = None

    def render(self, width, height):
        """คืน True ถ้าวาดใหม่จริง (ผู้เรียกต้องเอา .photo ไปอัปเดตบน canvas)"""
        if width < 2 or height < 2 or (width, height) == self._size:
            return False
        self._size = (width, height)
        if self.source is None:
            return False

        src = self.source
        scale = max(width / src.width, height / src.height)
        new = (max(1, int(src.width * scale)), max(1, int(src.height * scale)))
        img = src.resize(new, Image.LANCZOS)

        left = (new[0] - width) // 2
        top = int((new[1] - height) * self.focus)
        img = img.crop((left, top, left + width, top + height)).convert("RGB")

        # ฟิล์มน้ำเงินสม่ำเสมอ + ไล่มืดเพิ่มทางล่าง ให้ต่อกับพื้นหลังเนื้อหาแบบไม่มีรอยต่อ
        base = Image.new("RGB", img.size, PALETTE["tint"])
        img = Image.blend(img, base, self.dim)
        fade = Image.new("L", (1, height))
        for y in range(height):
            t = y / max(1, height - 1)
            fade.putpixel((0, y), int(255 * (t ** 2) * 0.9))
        img = Image.composite(base, img, fade.resize(img.size))

        self.photo = ImageTk.PhotoImage(img)
        return True


def card(parent, title, accent=None, subtitle=None):
    """สร้างการ์ดนูนพร้อมหัวข้อ คืน frame ที่ไว้ใส่เนื้อหา

    หัวข้อมีแถบสีตั้งอยู่ข้างหน้า ทำให้แยกส่วนได้ด้วยสายตาโดยไม่ต้องมีเส้นคั่น
    """
    accent = accent or PALETTE["gold"]
    outer = ttk.Frame(parent, style="Card.TFrame", padding=(0, 0, 0, 10))

    head = ttk.Frame(outer, style="Card.TFrame")
    head.pack(fill=tk.X, padx=14, pady=(12, 8))
    tk.Frame(head, bg=accent, width=4, height=1).pack(side=tk.LEFT, fill=tk.Y,
                                                      padx=(0, 10))
    text = ttk.Frame(head, style="Card.TFrame")
    text.pack(side=tk.LEFT, fill=tk.X, expand=True)
    lbl = ttk.Label(text, text=title, style="Heading.TLabel")
    lbl.pack(anchor="w")
    lbl.configure(foreground=accent)
    if subtitle:
        ttk.Label(text, text=subtitle, style="CardDim.TLabel").pack(anchor="w")

    body = ttk.Frame(outer, style="Card.TFrame")
    body.pack(fill=tk.BOTH, expand=True, padx=14)
    return outer, body


def draw_round_rect(canvas, x1, y1, x2, y2, radius, **kwargs):
    """วาดสี่เหลี่ยมมุมโค้งบน Canvas ด้วย polygon แบบ smooth"""
    radius = max(0, min(radius, (x2 - x1) // 2, (y2 - y1) // 2))
    points = [
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


# ---------------------------------------------------------------------------
# หน้าต่างไร้ขอบมุมโค้ง
# ---------------------------------------------------------------------------

GWL_EXSTYLE = -20
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080
SW_MINIMIZE = 6
SPI_GETWORKAREA = 0x0030


class _Rect(object):
    pass


def work_area():
    """พื้นที่จอที่ไม่โดน taskbar ทับ คืน (x, y, w, h)"""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        rect = wintypes.RECT()
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
        return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    except Exception:
        return None


class ScrollArea:
    """กรอบที่เลื่อนได้ "เฉพาะตอนจำเป็น"

    เนื้อหาพอดีหน้าต่าง = ไม่มีแถบเลื่อนให้เกะกะเลย
    จอเตี้ยกว่าเนื้อหาเมื่อไหร่แถบถึงโผล่ ของจึงไม่มีทางโดนตัดหาย
    ใส่ widget ลงใน .body เหมือน Frame ปกติ
    """

    def __init__(self, parent, padding=12):
        self.outer = ttk.Frame(parent, style="TFrame")
        self.outer.rowconfigure(0, weight=1)
        self.outer.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self.outer, highlightthickness=0, bd=0,
                                bg=PALETTE["base"])
        self.canvas.grid(row=0, column=0, sticky="nsew")

        self.bar = ttk.Scrollbar(self.outer, orient="vertical",
                                 command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._on_scroll)

        self.body = ttk.Frame(self.canvas, style="TFrame", padding=padding)
        self._window = self.canvas.create_window((0, 0), window=self.body,
                                                 anchor="nw")

        self.body.bind("<Configure>", self._on_body_resize)
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # ผูกล้อเมาส์ครั้งเดียวตอนสร้าง แล้วคัดกรองเอาใน _on_wheel
        # ห้ามผูก/ถอนด้วย <Enter>/<Leave> ของ canvas เพราะเนื้อหาคลุม canvas
        # ไว้หมด เมาส์จึงอยู่เหนือ "ลูก" ตลอด ไม่เคยเข้า-ออก canvas เอง
        # และต้องใส่ add="+" ไม่งั้น ScrollArea ตัวหลังจะไปทับ binding ตัวก่อน
        self._accum = 0
        self.canvas.bind_all("<MouseWheel>", self._on_wheel, add="+")

    def _on_scroll(self, first, last):
        # ซ่อนแถบเลื่อนเมื่อเนื้อหาพอดีอยู่แล้ว
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.bar.grid_remove()
        else:
            self.bar.grid(row=0, column=1, sticky="ns")
        self.bar.set(first, last)

    def _on_body_resize(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_resize(self, event):
        # ให้เนื้อหากว้างเท่ากรอบเสมอ จะได้ไม่ต้องเลื่อนแนวนอน
        self.canvas.itemconfigure(self._window, width=event.width)

    # widget พวกนี้จัดการล้อเมาส์เองอยู่แล้ว ถ้าไปแย่งจะเกิดสองอย่างพร้อมกัน
    # เช่นหมุนล้อเหนือ Combobox แล้วค่าที่เลือกเปลี่ยนไปโดยผู้ใช้ไม่ได้ตั้งใจ
    # widget พวกนี้เลื่อนเนื้อหาของตัวเองได้จริง ปล่อยให้จัดการเอง
    # ไม่รวม TCombobox เพราะ apply_theme ปิดล้อของมันไปแล้ว (ดูเหตุผลที่นั่น)
    WHEEL_OWNERS = ("Treeview", "Listbox", "Text", "Scrollbar", "TScrollbar")

    def _inside(self, widget):
        """widget ตัวนี้อยู่ในกรอบเลื่อนของเราหรือเปล่า"""
        node = widget
        while node is not None:
            if node is self.canvas:
                return True
            node = getattr(node, "master", None)
        return False

    def _on_wheel(self, event):
        widget = getattr(event, "widget", None)
        if not isinstance(widget, tk.Misc):
            return
        try:
            if widget.winfo_class() in self.WHEEL_OWNERS:
                return          # เจ้าของล้อตัวจริง อย่าไปยุ่ง
        except tk.TclError:
            return
        if not self._inside(widget):
            return              # อยู่คนละแท็บ/คนละกรอบ

        first, last = self.canvas.yview()
        if first <= 0.0 and last >= 1.0:
            return              # ไม่มีอะไรให้เลื่อน อย่าไปกินอีเวนต์

        # ทัชแพดส่ง delta เป็นเศษของ 120 ได้ (8, 40, 119) ถ้าหารแบบปัดลง
        # ค่าบวกน้อยๆ จะกลายเป็น 0 (เลื่อนขึ้นไม่ได้เลย) ส่วนค่าลบกลับปัดเป็น -1
        # จึงต้องสะสมไว้แล้วเลื่อนเมื่อครบหน่วย สองทิศทางถึงจะสมมาตรกัน
        self._accum += event.delta
        steps = int(self._accum / 120)
        if steps:
            self._accum -= steps * 120
            self.canvas.yview_scroll(-steps, "units")

    def required_height(self):
        self.body.update_idletasks()
        return self.body.winfo_reqheight()


class RoundedWindow:
    """ทำให้หน้าต่าง Tk ไร้ขอบ มุมโค้ง ลากย้ายได้ ย่อ/ขยายได้ ปรับขนาดได้

    บน Windows 10 ไม่มีมุมโค้ง native (มีเฉพาะ Win11) จึงตัดรูปทรงหน้าต่างเอง
    ด้วย SetWindowRgn + CreateRoundRectRgn แล้ววาด title bar เอง
    """

    def __init__(self, root, radius=CORNER_RADIUS):
        self.root = root
        self.radius = radius
        self.maximized = False
        self._normal_geometry = None
        self._drag = None
        self._resize = None
        self._applied = None

        root.overrideredirect(True)
        root.configure(bg=PALETTE["void"])
        root.minsize(MIN_W, MIN_H)

        if sys.platform == "win32":
            root.after(10, self._register_taskbar)

        root.bind("<Configure>", self._on_configure, add="+")
        root.bind("<Motion>", self._on_motion, add="+")
        root.bind("<Button-1>", self._on_press, add="+")
        root.bind("<B1-Motion>", self._on_drag, add="+")
        root.bind("<ButtonRelease-1>", self._on_release, add="+")

    # ---- Win32 ----

    def _hwnd(self):
        import ctypes
        wid = self.root.winfo_id()
        # Tk ห่อหน้าต่างไว้อีกชั้น ต้องเอาตัวแม่ ถ้าไม่มีค่อยใช้ตัวเอง
        return ctypes.windll.user32.GetParent(wid) or wid

    def _register_taskbar(self):
        """overrideredirect ทำให้ปุ่มบน taskbar หายไป ต้องขอคืนเอง"""
        try:
            import ctypes
            hwnd = self._hwnd()
            user32 = ctypes.windll.user32
            get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            style = get_long(hwnd, GWL_EXSTYLE)
            style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
            set_long(hwnd, GWL_EXSTYLE, style)
            self.root.withdraw()
            self.root.after(20, self._reshow)
        except Exception:
            pass

    def _reshow(self):
        """deiconify ล้าง window region ที่ตั้งไว้ทิ้ง ต้องตั้งใหม่หลังโชว์เสมอ"""
        self.root.deiconify()
        self._applied = None
        self.root.after_idle(self.refresh_region)

    def refresh_region(self):
        self._apply_region(self.root.winfo_width(), self.root.winfo_height())

    def _apply_region(self, width, height):
        """ตัดรูปทรงหน้าต่างให้มุมโค้ง — ต้องทำใหม่ทุกครั้งที่ขนาดเปลี่ยน"""
        if sys.platform != "win32":
            return
        radius = 0 if self.maximized else self.radius
        if self._applied == (width, height, radius):
            return
        self._applied = (width, height, radius)
        try:
            import ctypes
            hwnd = self._hwnd()
            rgn = ctypes.windll.gdi32.CreateRoundRectRgn(
                0, 0, width + 1, height + 1, radius * 2, radius * 2)
            # ระบบเป็นเจ้าของ region หลังเรียก SetWindowRgn ห้าม DeleteObject เอง
            ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True)
        except Exception:
            pass

    # ---- ปุ่มควบคุม ----

    def minimize(self):
        if sys.platform != "win32":
            self.root.iconify()
            return
        try:
            import ctypes
            ctypes.windll.user32.ShowWindow(self._hwnd(), SW_MINIMIZE)
        except Exception:
            self.root.iconify()

    def toggle_maximize(self):
        if self.maximized:
            if self._normal_geometry:
                self.root.geometry(self._normal_geometry)
            self.maximized = False
        else:
            self._normal_geometry = self.root.geometry()
            area = work_area()
            if area:
                x, y, w, h = area
                self.root.geometry("%dx%d+%d+%d" % (w, h, x, y))
            else:
                self.root.state("zoomed")
            self.maximized = True
        self._applied = None
        self.root.after_idle(
            lambda: self._apply_region(self.root.winfo_width(), self.root.winfo_height()))

    # ---- ลากย้าย ----

    def bind_drag(self, widget):
        """ทำให้ widget นี้ลากย้ายหน้าต่างได้ (ใช้กับแถบหัว)"""
        widget.bind("<Button-1>", self._start_move, add="+")
        widget.bind("<B1-Motion>", self._do_move, add="+")
        widget.bind("<Double-Button-1>", lambda e: self.toggle_maximize(), add="+")

    def _start_move(self, event):
        self._drag = (event.x_root - self.root.winfo_x(),
                      event.y_root - self.root.winfo_y())

    def _do_move(self, event):
        if not self._drag:
            return
        if self.maximized:                 # ลากหน้าต่างที่ขยายเต็มจอ -> คืนขนาดเดิมก่อน
            self.toggle_maximize()
            self._drag = (self.root.winfo_width() // 2, 20)
        dx, dy = self._drag
        self.root.geometry("+%d+%d" % (event.x_root - dx, event.y_root - dy))

    # ---- ปรับขนาดด้วยการลากขอบ ----

    def _edge_at(self, x, y):
        w, h = self.root.winfo_width(), self.root.winfo_height()
        left, right = x < EDGE, x > w - EDGE
        top, bottom = y < EDGE, y > h - EDGE
        return ("w" if left else "e" if right else "") + \
               ("n" if top else "s" if bottom else "")

    _CURSORS = {"n": "sb_v_double_arrow", "s": "sb_v_double_arrow",
                "e": "sb_h_double_arrow", "w": "sb_h_double_arrow",
                "wn": "size_nw_se", "es": "size_nw_se",
                "en": "size_ne_sw", "ws": "size_ne_sw"}

    def _on_motion(self, event):
        if self._resize or self.maximized:
            return
        edge = self._edge_at(event.x_root - self.root.winfo_x(),
                             event.y_root - self.root.winfo_y())
        self.root.configure(cursor=self._CURSORS.get(edge, ""))

    def _on_press(self, event):
        if self.maximized:
            return
        x = event.x_root - self.root.winfo_x()
        y = event.y_root - self.root.winfo_y()
        edge = self._edge_at(x, y)
        if edge:
            self._resize = (edge, event.x_root, event.y_root,
                            self.root.winfo_x(), self.root.winfo_y(),
                            self.root.winfo_width(), self.root.winfo_height())

    def _on_drag(self, event):
        if not self._resize:
            return
        edge, sx, sy, ox, oy, ow, oh = self._resize
        dx, dy = event.x_root - sx, event.y_root - sy
        x, y, w, h = ox, oy, ow, oh

        if "e" in edge:
            w = max(MIN_W, ow + dx)
        if "w" in edge:
            w = max(MIN_W, ow - dx)
            x = ox + (ow - w)
        if "s" in edge:
            h = max(MIN_H, oh + dy)
        if "n" in edge:
            h = max(MIN_H, oh - dy)
            y = oy + (oh - h)
        self.root.geometry("%dx%d+%d+%d" % (w, h, x, y))

    def _on_release(self, event):
        self._resize = None
        self._drag = None

    def _on_configure(self, event):
        if event.widget is self.root:
            self._apply_region(event.width, event.height)
