# -*- coding: utf-8 -*-
"""คำนวณผลลัพธ์ทุกเคสที่เป็นไปได้ด้วย Python แล้วเขียนออกเป็น JSON

ใช้เป็น "คำตอบที่ถูก" ให้ฝั่ง JavaScript เอาไปเทียบ ถ้าตรงกันทุกตัว
แปลว่าแปลงมาได้เหมือนกันจริง ไม่ใช่แค่ผ่านเทสต์ที่เลือกมาไม่กี่เคส

รับ path ปลายทางเป็นอาร์กิวเมนต์:  py tools\\export_expected.py out.json
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

LEVELS = range(gd.MIN_START_LEVEL, gd.MAX_LEVEL + 1)
GRADE_IDS = range(len(gd.GRADES))


def call(fn, *args):
    """เรียกฟังก์ชัน คืน ('ok', ค่า) หรือ ('err',) ถ้าโยน CalcError

    ต้องเก็บกรณี error ไว้เทียบด้วย ไม่งั้นฝั่ง JS อาจยอมรับสิ่งที่
    ฝั่ง Python ปฏิเสธ แล้วคำนวณเลขมั่วออกมาโดยไม่มีใครรู้
    """
    try:
        return ["ok", fn(*args)]
    except gd.CalcError:
        return ["err"]


def main(out_path):
    data = {"upgrade_pieces": [], "inherit_cost": [], "upgrade_plan": [],
            "split_down": [], "to_pieces": [], "success_chance": [],
            "melt": [], "pieces_value": []}

    for grade in GRADE_IDS:
        for start in LEVELS:
            for end in LEVELS:
                data["upgrade_pieces"].append(
                    [start, end, grade, call(gd.upgrade_pieces, start, end, grade)])

    for mode in gd.INHERIT_MODES:
        for level in LEVELS:
            for grade in GRADE_IDS:
                for target in GRADE_IDS:
                    data["inherit_cost"].append(
                        [mode, level, grade, target,
                         call(gd.inherit_cost, mode, level, grade, target)])

    for sg in GRADE_IDS:
        for sl in LEVELS:
            for tg in GRADE_IDS:
                for tl in LEVELS:
                    result = call(gd.upgrade_plan, sg, sl, tg, tl)
                    if result[0] == "ok":
                        plan = result[1]
                        result = ["ok", {
                            "pieces": plan["pieces"],
                            "gold": plan["gold"],
                            "final_level": plan["final_level"],
                            "overshoot": plan["overshoot"],
                            "steps": len(plan["steps"]),
                        }]
                    data["upgrade_plan"].append([sg, sl, tg, tl, result])

    counts = [0, 1, 7, 9, 10, 11, 99, 100, 101, 131, 661, 999, 1000, 1001,
              2420, 13457, 99999, 999999, 1000000, 3535643]
    for line in (gd.LINE_BLUE, gd.LINE_RED):
        rows = gd.ladder(line)
        for n in counts:
            data["split_down"].append([line, n, gd.split_down(rows, n)])
            data["to_pieces"].append(
                [line, n, gd.to_pieces(rows, gd.split_down(rows, n))])

    for have in counts:
        for needed in (0, 1, 131, 661, 2420, 5672):
            data["success_chance"].append(
                [have, needed, gd.success_chance(have, needed)])

    for n in counts:
        data["melt"].append([n, list(gd.melt(n, gd.MATERIAL_BLUE_RATIO))])
        data["pieces_value"].append(
            [n, 375.0, gd.pieces_value(n, 375.0, gd.MATERIAL_BLUE_RATIO)])

    io.open(out_path, "w", encoding="utf-8").write(
        json.dumps(data, ensure_ascii=False))
    total = sum(len(v) for v in data.values())
    print("เขียน %s" % out_path)
    for name, rows in data.items():
        print("   %-16s %6d เคส" % (name, len(rows)))
    print("   รวมทั้งหมด %d เคส" % total)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "expected.json")
