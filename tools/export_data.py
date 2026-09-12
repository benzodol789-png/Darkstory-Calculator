# -*- coding: utf-8 -*-
"""สร้าง docs/js/data.js จาก game_data.py

ห้ามพิมพ์ตัวเลขในตารางเกมใหม่ด้วยมือเด็ดขาด ตัวเลขพวกนั้นตรวจสอบกับ
ตารางในเกมมาแล้ว และเคยมีบทเรียนว่าการ "แก้ให้ดูสวย" ทำข้อมูลจริงพัง
สคริปต์นี้จึงอ่านจากไฟล์ต้นทางแล้วพ่นออกมาเป็น JS ตรงๆ

รันใหม่ทุกครั้งที่ game_data.py เปลี่ยน:  py tools\\export_data.py
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import game_data as gd

OUT = os.path.join(ROOT, "docs", "js", "data.js")


def js_table(name, table, indent="  "):
    """dict ที่คีย์เป็นเลขระดับ -> object ของ JS เรียงตามระดับ"""
    lines = ["export const %s = {" % name]
    for level in sorted(table):
        lines.append("%s%d: %s," % (indent, level, json.dumps(table[level])))
    lines.append("};")
    return "\n".join(lines)


def js_ladder(name, ladder):
    rows = []
    for tier in ladder:
        rows.append("  %s," % json.dumps({
            "name": tier["name"],
            "per": tier["per"],
            "unit": tier["unit"],
            "tradeable": bool(tier["tradeable"]),
        }, ensure_ascii=False))
    return "export const %s = [\n%s\n];" % (name, "\n".join(rows))


def main():
    parts = [
        "// ไฟล์นี้สร้างอัตโนมัติจาก game_data.py — อย่าแก้ด้วยมือ",
        "// สร้างใหม่ด้วย:  py tools/export_data.py",
        "",
        "export const GRADES = %s;" % json.dumps(gd.GRADES, ensure_ascii=False),
        "",
        "export const ITEM_CATEGORY_ALL = %s;"
        % json.dumps(gd.ITEM_CATEGORY_ALL, ensure_ascii=False),
        "export const ITEM_CATEGORIES = %s;"
        % json.dumps(gd.ITEM_CATEGORIES, ensure_ascii=False),
        "export const ITEM_CATEGORY_DEFAULT = %s;"
        % json.dumps(gd.ITEM_CATEGORY_DEFAULT, ensure_ascii=False),
        "",
        js_ladder("BLUE_LADDER", gd.BLUE_LADDER),
        "",
        js_ladder("RED_LADDER", gd.RED_LADDER),
        "",
        "export const LINE_BLUE = %s;" % json.dumps(gd.LINE_BLUE),
        "export const LINE_RED = %s;" % json.dumps(gd.LINE_RED),
        "export const LADDERS = { [LINE_BLUE]: BLUE_LADDER, [LINE_RED]: RED_LADDER };",
        "",
        "export const MIN_LEVEL = %d;" % gd.MIN_LEVEL,
        "export const MAX_LEVEL = %d;" % gd.MAX_LEVEL,
        "export const MIN_INHERIT_LEVEL = %d;" % gd.MIN_INHERIT_LEVEL,
        "export const HIGHER_TARGET_OFFSET = %d;" % gd.HIGHER_TARGET_OFFSET,
        "export const MATERIAL_BLUE_RATIO = %d;" % gd.MATERIAL_BLUE_RATIO,
        "export const MATERIAL_RED_RATIO = %d;" % gd.MATERIAL_RED_RATIO,
        "",
        "export const INHERIT_NONE = %s;"
        % json.dumps(gd.INHERIT_NONE, ensure_ascii=False),
        "export const INHERIT_MODE_SAME = %s;"
        % json.dumps(gd.INHERIT_MODE_SAME, ensure_ascii=False),
        "export const INHERIT_MODE_HIGHER = %s;"
        % json.dumps(gd.INHERIT_MODE_HIGHER, ensure_ascii=False),
        "export const INHERIT_MODES = %s;"
        % json.dumps(gd.INHERIT_MODES, ensure_ascii=False),
        "",
        "// ระดับหลังสืบทอดข้ามเกรด (+10..+14 ลบ 4, ตั้งแต่ +15 ลบ 5)",
        "export const HIGHER_RESULT_LEVEL = %s;"
        % json.dumps({str(k): v for k, v in sorted(gd.HIGHER_RESULT_LEVEL.items())}),
        "",
        js_table("INHERIT_SAME", gd.INHERIT_SAME),
        "",
        js_table("INHERIT_HIGHER", gd.INHERIT_HIGHER),
        "",
        js_table("UPGRADE_RED", gd.UPGRADE_RED),
        "",
    ]
    text = "\n".join(parts)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(text)

    numbers = (sum(len(v) for v in gd.INHERIT_SAME.values())
               + sum(len(v) for v in gd.INHERIT_HIGHER.values())
               + sum(len(v) for v in gd.UPGRADE_RED.values()))
    print("เขียน %s" % OUT)
    print("  ตัวเลขในตาราง %d ตัว | เกรด %d | หมวดไอเทม %d"
          % (numbers, len(gd.GRADES), len(gd.ITEM_CATEGORIES)))


if __name__ == "__main__":
    main()
