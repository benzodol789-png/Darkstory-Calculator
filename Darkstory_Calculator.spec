# -*- mode: python ; coding: utf-8 -*-
"""สูตร build .exe ด้วย PyInstaller

รันด้วย build.bat หรือ:  py -m PyInstaller --noconfirm Darkstory_Calculator.spec

ผลลัพธ์: dist\\Darkstory_Calculator.exe (ไฟล์เดียว ไม่มีหน้าต่าง console)
darkstory_config.json / darkstory_local.json / darkstory.log จะอยู่ "ข้าง exe"
ไม่ได้ฝังอยู่ในตัว exe จึงแก้ลิงก์เซิร์ฟเวอร์ได้โดยไม่ต้อง build ใหม่
"""
import os

# ไอคอนอยู่ในโฟลเดอร์แม่ (d:\Darkstory\)
ICON_DIR = os.path.abspath(os.path.join(os.getcwd(), ".."))
ICON = os.path.join(ICON_DIR, "Red.ico")

import glob

datas = []
for name in ("Red.ico", "Blue.ico"):
    path = os.path.join(ICON_DIR, name)
    if os.path.exists(path):
        datas.append((path, "."))

# ภาพพื้นหลังธีม — ต้องฝังไปด้วย ไม่งั้น .exe จะเป็นพื้นดำเปล่าๆ
for path in glob.glob(os.path.join(os.getcwd(), "Darkstory*BG*.jpg")):
    datas.append((path, "."))

a = Analysis(
    ["Darkstory_Calculator.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    # ตัดเฉพาะ third-party ก้อนใหญ่ที่ไม่ได้ใช้แน่ๆ
    #
    # ห้ามตัดโมดูลของ standard library ที่นี่ โดยเฉพาะ email / http / xml:
    # urllib.request -> http.client -> email.parser ถ้าตัด email จะ import พัง
    # ตั้งแต่ก่อน setup_logging() จะทำงาน แล้ว .exe จะขึ้น error dialog เปล่าๆ
    # โดยไม่มี darkstory.log ให้ดูเลย
    # PIL ห้ามตัด — ธีมใช้ย่อ/ครอปภาพพื้นหลัง (ตัด plugin ที่ไม่ได้ใช้แทน)
    excludes=[
        "numpy", "pandas", "matplotlib", "scipy", "PyQt5", "PySide2",
        "pytest", "IPython", "notebook", "tkinter.test",
        "PIL.ImageQt", "PIL.ImageShow", "PIL.ImageGrab",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Darkstory_Calculator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,          # ไม่มีหน้าต่างดำ — error ทั้งหมดลง darkstory.log
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON if os.path.exists(ICON) else None,
)
