# -*- coding: utf-8 -*-
"""ตารางข้อมูลเกม Darkstory + ฟังก์ชันคำนวณ

แยกออกมาจาก Darkstory_Calculator.py เพราะตารางตัวเลขคือส่วนที่ต้องแก้บ่อยที่สุด
เวลาเกมอัปเดต และแยกออกมาแล้วตรวจความสม่ำเสมอของตารางได้ง่าย

ความหมายของตาราง (ยืนยันกับผู้ใช้แล้ว):
  UPGRADE_RED[lv][g]    = ชิ้นส่วนแดงที่ใช้ "ไปถึง" +lv สำหรับไอเทมเกรด GRADES[g]
                          => ตีจาก +st ไป +en ต้องรวมแถว st+1 .. en
  INHERIT_SAME[lv][g]   = ค่าสืบทอด (ทอง) ที่ +lv ไปเกรดเดิม GRADES[g]  -- 6 คอลัมน์
  INHERIT_HIGHER[lv][c] = ค่าสืบทอด (ทอง) ที่ +lv ไปเกรดที่สูงขึ้น      -- 5 คอลัมน์
                          คอลัมน์ c ตรงกับ GRADES[c + HIGHER_TARGET_OFFSET]
                          คือ หายาก..พระเจ้า ("ทั่วไป" เป็นเป้าหมายไม่ได้ เพราะต่ำสุด)
"""

GRADES = ["ทั่วไป", "หายาก", "วีรบุรุษ", "ตำนาน", "เซียน", "พระเจ้า"]

# หมวดหมู่ไอเทม — เรียงตามเมนูในเกม
# "ภาพรวม" ในเมนูไม่ใช่หมวดของไอเทม แต่เป็นตัวเลือก "ดูทั้งหมด"
# จึงแยกออกมาเป็นค่ากรองต่างหาก ไม่ใส่ในลิสต์ที่ให้เลือกตอนเพิ่มไอเทม
ITEM_CATEGORY_ALL = "ภาพรวม"
ITEM_CATEGORIES = ["อาวุธ", "เกราะ", "เครื่องประดับ", "สกิล",
                   "วัตถุดิบ", "โกดังมอลล์", "อื่นๆ"]
ITEM_CATEGORY_DEFAULT = "อื่นๆ"

# วัสดุอัปเกรด — "ชิ้นส่วน" ทั้งสองแบบซื้อขายไม่ได้ ต้องหลอมรวมก่อน
# และมีแต่ "หินดั้งเดิม" เท่านั้นที่ซื้อขายด้วยเหรียญทองได้
RED_PIECE = "ชิ้นส่วนหินดั้งเดิมแดง"
RED_UNIT = "พลอยสีแดงเข้ม"          # ซื้อขายไม่ได้ ไม่มีราคาเป็นทอง
BLUE_PIECE = "ชิ้นส่วนหินดั้งเดิม"
BLUE_UNIT = "หินดั้งเดิม"            # ซื้อขายได้ ใช้เหรียญทองซื้อขาย

# ---------------------------------------------------------------------------
# บันไดวัสดุ — ยืนยันกับผู้ใช้แล้ว
#
# แต่ละสายไต่ขึ้นทีละชั้น ชั้นละ 10 และ "แยกลงได้จริงทั้งสองทาง" ไม่สูญเสีย
# ดังนั้นทุกชั้นแปลงกลับเป็นจำนวน "ชิ้นส่วน" (ชั้นล่างสุด) ได้เสมอ
#
# และเพราะอัตราเป็น 10 ทุกขั้น การแยกของจึงเท่ากับอ่านเลขฐานสิบทีละหลัก
#   13,457 ชิ้นส่วน = 13 สูงสุด | 4 ขั้นสูง | 5 ก้อน | 7 ชิ้นส่วน
# แต่โค้ดข้างล่างไม่ได้ hardcode เลข 10 ไว้ ถ้าเกมออกชั้นที่อัตราต่างไปก็ยังถูก
#
# สำคัญ: สายแดงกับสายน้ำเงินให้ "โอกาสตีบวก" เท่ากันชิ้นต่อชิ้น
# ต่างกันแค่ผลข้างเคียง — ใช้สายแดงแล้วอุปกรณ์ถูกผนึก ขายต่อไม่ได้
# ---------------------------------------------------------------------------

# per = ต้องใช้ของชั้นที่อยู่ล่างกว่ากี่อัน ถึงได้ของชั้นนี้ 1 อัน (ชั้นล่างสุด = None)
BLUE_LADDER = (
    {"name": BLUE_PIECE,           "per": None, "unit": "ชิ้น",  "tradeable": False},
    {"name": BLUE_UNIT,            "per": 10,   "unit": "ก้อน",  "tradeable": True},
    {"name": "หินดั้งเดิมขั้นสูง",     "per": 10,   "unit": "ก้อน",  "tradeable": True},
    {"name": "หินดั้งเดิมสูงสุด",      "per": 10,   "unit": "ก้อน",  "tradeable": True},
)

RED_LADDER = (
    {"name": RED_PIECE,            "per": None, "unit": "ชิ้น",  "tradeable": False},
    {"name": RED_UNIT,             "per": 10,   "unit": "เม็ด",  "tradeable": False},
    {"name": "หินดั้งเดิมแดงขั้นสูง",  "per": 10,   "unit": "เม็ด",  "tradeable": False},
    {"name": "หินดั้งเดิมแดงสูงสุด",   "per": 10,   "unit": "เม็ด",  "tradeable": False},
)

LINE_BLUE = "blue"
LINE_RED = "red"
LADDERS = {LINE_BLUE: BLUE_LADDER, LINE_RED: RED_LADDER}

# อัตราชั้นที่ 2 — ชื่อเดิมที่โค้ดส่วนอื่นเรียกใช้อยู่ ดึงจากบันไดเพื่อไม่ให้ค่าสองที่เพี้ยนกัน
MATERIAL_RED_RATIO = RED_LADDER[1]["per"]     # ชิ้นส่วนหินดั้งเดิมแดง 10 ชิ้น = พลอยสีแดงเข้ม 1 เม็ด
MATERIAL_BLUE_RATIO = BLUE_LADDER[1]["per"]   # ชิ้นส่วนหินดั้งเดิม 10 ชิ้น = หินดั้งเดิม 1 ก้อน

RED_TRADEABLE = False
BLUE_TRADEABLE = True

MIN_LEVEL = 1
MAX_LEVEL = 30
MIN_INHERIT_LEVEL = 10     # ตารางสืบทอดทั้งสองเริ่มที่ +10

# INHERIT_HIGHER คอลัมน์ 0 ตรงกับ GRADES[1] (หายาก)
HIGHER_TARGET_OFFSET = 1

# ระดับอุปกรณ์ "หลังสืบทอด" — สืบทอดข้ามเกรดแล้วระดับตีบวกจะลดลง
# +10..+14 ลด 4 ระดับ, ตั้งแต่ +15 ขึ้นไปลด 5 ระดับ (ทั้ง +14 และ +15 จึงเหลือ +10)
HIGHER_RESULT_LEVEL = {lv: lv - (4 if lv <= 14 else 5)
                       for lv in range(MIN_INHERIT_LEVEL, MAX_LEVEL + 1)}

INHERIT_NONE = "ไม่สืบทอด"
INHERIT_MODE_SAME = "ระดับเดียวกัน"
INHERIT_MODE_HIGHER = "ระดับสูงขึ้น"
INHERIT_MODES = [INHERIT_NONE, INHERIT_MODE_SAME, INHERIT_MODE_HIGHER]


class CalcError(Exception):
    """ตัวเลือกไม่ถูกต้องหรือไม่มีข้อมูลพอ — ข้อความเป็นภาษาไทยพร้อมแสดงให้ผู้ใช้"""


# ---------------------------------------------------------------------------
# ตารางค่าสืบทอด "ระดับเดียวกัน" (ทอง) — 6 คอลัมน์ = GRADES[0..5]
# ระดับอุปกรณ์หลังสืบทอดเท่าเดิม (+lv -> +lv)
#
# ตัวเลขตรงตามตารางในเกม อย่าไป "แก้ให้ ratio สวย" เอง — lv24 col5 = 2,047,007
# และ lv30 col1 = 130,349 หลุดจากตัวคูณ 3/2.8 อยู่นิดหน่อย แต่เป็นค่าจริง
# ---------------------------------------------------------------------------
INHERIT_SAME = {
    10: [213, 639, 1917, 5753, 17260, 48330],
    11: [282, 846, 2538, 7614, 22844, 63963],
    12: [371, 1114, 3344, 10034, 30102, 84286],
    13: [488, 1464, 4393, 13179, 39538, 110706],
    14: [639, 1918, 5756, 17268, 51804, 145052],
    15: [836, 2509, 7527, 22583, 67750, 189702],
    16: [1092, 3276, 9831, 29493, 88481, 247747],
    17: [1425, 4275, 12825, 38476, 115430, 323205],
    18: [1857, 5572, 16718, 50154, 150464, 421301],
    19: [2419, 7259, 21778, 65336, 196009, 548825],
    20: [3150, 9452, 28357, 85072, 255216, 714607],
    21: [4101, 12303, 36909, 110728, 332187, 930124],
    22: [5336, 16009, 48027, 144082, 432248, 1210295],
    23: [6942, 20826, 62480, 187442, 562327, 1574517],
    24: [9030, 27089, 81270, 243810, 731430, 2047007],
    25: [11744, 35231, 105696, 317088, 951265, 2663543],
    26: [15272, 45816, 137449, 412349, 1237049, 3463740],
    27: [19858, 59576, 178729, 536189, 1608569, 4503996],
    28: [25821, 77464, 232393, 697181, 2091545, 5856329],
    29: [33572, 100718, 302157, 906471, 2719414, 7614361],
    30: [43649, 130349, 392849, 1178548, 3535643, 9899804],
}

# ---------------------------------------------------------------------------
# ตารางค่าสืบทอด "ระดับสูงขึ้น" (ทอง) — 5 คอลัมน์ = การเปลี่ยนเกรดทีละขั้น
#   คอลัมน์ 0 = ทั่วไป->หายาก, 1 = หายาก->วีรบุรุษ, 2 = วีรบุรุษ->ตำนาน,
#   3 = ตำนาน->เซียน, 4 = เซียน->พระเจ้า   (เกรดปลายทาง = GRADES[c + 1])
#
# แถว lv15 คอลัมน์ 0-3 ต่ำกว่า lv14 ซึ่งดูผิดปกติ แต่เป็นค่าจริงจากเกม
# (ในตารางต้นฉบับทำสีแดงกำกับไว้เอง) และเป็นระดับเดียวกับที่ระดับหลังสืบทอด
# เปลี่ยนจาก "ลบ 4" เป็น "ลบ 5" พอดี -- อย่าไปคำนวณค่าใหม่ทับ
# ---------------------------------------------------------------------------
INHERIT_HIGHER = {
    10: [169, 508, 1526, 4578, 11669],
    11: [245, 736, 2209, 6627, 17033],
    12: [344, 1032, 3096, 9090, 24006],
    13: [472, 1417, 4250, 12752, 33071],
    14: [638, 1917, 5751, 17253, 44856],
    15: [442, 1326, 3979, 11938, 60176],
    16: [599, 1799, 5398, 16194, 80092],
    17: [804, 2414, 7242, 21727, 105983],
    18: [1070, 3213, 9640, 28921, 139641],
    19: [1417, 4252, 12757, 38272, 183396],
    20: [1867, 5603, 16809, 50429, 240278],
    21: [2452, 7359, 22077, 66233, 314224],
    22: [3213, 9641, 28926, 86778, 410354],
    23: [4202, 12609, 37828, 113486, 535324],
    24: [5488, 16467, 49402, 148208, 697784],
    25: [7160, 21482, 64448, 193345, 908982],
    26: [9334, 28002, 84006, 252018, 1183540],
    27: [12159, 36478, 109435, 328306, 1540465],
    28: [15832, 47496, 142490, 427473, 2004468],
    29: [20606, 61821, 185463, 556390, 2607672],
    30: [26814, 80442, 241327, 723982, 3391836],
}

# ---------------------------------------------------------------------------
# ชิ้นส่วนหินดั้งเดิม (เศษแดง) ที่ใช้ตีบวก "ขึ้น 1 ระดับ" — 6 คอลัมน์ = GRADES[0..5]
# UPGRADE_RED[lv] = ค่าที่ใช้ตีจาก +(lv-1) ไป +lv
# เช่น เกรดตำนาน ตีจาก +6 ไป +7 ใช้ UPGRADE_RED[7][3] = 131 ชิ้น
# ---------------------------------------------------------------------------
UPGRADE_RED = {
    1: [1, 4, 10, 27, 81, 227],
    2: [2, 4, 12, 36, 106, 295],
    3: [2, 6, 16, 46, 137, 384],
    4: [2, 7, 20, 60, 178, 499],
    5: [3, 9, 26, 78, 232, 648],
    6: [4, 12, 34, 101, 301, 843],
    7: [5, 15, 44, 131, 391, 1095],
    8: [7, 19, 57, 170, 509, 1424],
    9: [9, 25, 74, 221, 661, 1851],
    10: [11, 32, 96, 287, 859, 2406],
    11: [14, 42, 125, 373, 1117, 3127],
    12: [18, 54, 162, 484, 1452, 4065],
    13: [24, 70, 210, 630, 1888, 5285],
    14: [31, 91, 273, 818, 2454, 6870],
    15: [40, 119, 355, 1064, 3190, 8930],
    16: [52, 154, 461, 1383, 4147, 11609],
    17: [67, 200, 599, 1797, 5390, 15092],
    18: [87, 260, 779, 2336, 7007, 19620],
    19: [113, 338, 1013, 3037, 9109, 25505],
    20: [147, 439, 1316, 3948, 11842, 33157],
    21: [191, 571, 1711, 5132, 15395, 43104],
    22: [248, 742, 2224, 6671, 20013, 56035],
    23: [322, 964, 2891, 8672, 26016, 72845],
    24: [418, 1253, 3758, 11274, 33821, 94698],
    25: [543, 1629, 4886, 14656, 43967, 123108],
    26: [706, 2117, 6351, 19053, 57157, 160040],
    27: [918, 2753, 8257, 24768, 74305, 208052],
    28: [1193, 3578, 10733, 32199, 96596, 270467],
    29: [1551, 4651, 13953, 41858, 125575, 351607],
    30: [2016, 6047, 18139, 54416, 163247, 457089],
}


# ---------------------------------------------------------------------------
# ฟังก์ชันคำนวณ
# ---------------------------------------------------------------------------

def upgrade_pieces(start_level, end_level, grade_index):
    """ชิ้นส่วนแดงที่ต้องใช้เพื่อตีจาก +start_level ไป +end_level

    UPGRADE_RED[lv] คือค่าที่ใช้ "ไปถึง" +lv ดังนั้นระดับต้นทางไม่ต้องจ่ายซ้ำ
    -> รวมแถว start_level+1 .. end_level

    ผลลัพธ์เป็น additive: f(a,b) + f(b,c) == f(a,c) เสมอ
    และ f(x,x) == 0 (ไม่ได้ตีก็ไม่เสียอะไร)
    """
    _check_level_range(start_level, end_level)
    _check_grade(grade_index)
    return sum(UPGRADE_RED[lv][grade_index]
               for lv in range(start_level + 1, end_level + 1))


def inherit_cost(mode, level, grade_index, target_grade_index):
    """ค่าสืบทอด (ทอง) ที่ระดับ +level

    mode เป็นหนึ่งใน INHERIT_MODES คืน 0 เมื่อ "ไม่สืบทอด"
    โยน CalcError พร้อมข้อความภาษาไทยเมื่อตัวเลือกใช้ไม่ได้ หรือไม่มีข้อมูล
    """
    if mode == INHERIT_NONE:
        return 0

    if mode not in INHERIT_MODES:
        raise CalcError("โหมดสืบทอดไม่ถูกต้อง: %s" % mode)

    _check_grade(grade_index)
    _check_grade(target_grade_index)

    if level < MIN_INHERIT_LEVEL:
        raise CalcError(
            "ไม่มีข้อมูลค่าสืบทอดต่ำกว่า +%d (เลือก 'ถึง' ตั้งแต่ +%d ขึ้นไป "
            "หรือเลือก '%s')" % (MIN_INHERIT_LEVEL, MIN_INHERIT_LEVEL, INHERIT_NONE)
        )

    if mode == INHERIT_MODE_SAME:
        # "ระดับเดียวกัน" = เกรดปลายทางเท่ากับเกรดต้นทางเสมอ จึงใช้ grade_index
        # (ไฟล์เดิมใช้เกรดเป้าหมายที่ผู้ใช้เลือกแยก ทำให้ค่าผิดได้ถึง 81 เท่า)
        if target_grade_index != grade_index:
            raise CalcError(
                "โหมด '%s' เกรดเป้าหมายต้องเป็น '%s' เท่ากับเกรดไอเทม"
                % (INHERIT_MODE_SAME, GRADES[grade_index])
            )
        return INHERIT_SAME[level][grade_index]

    # INHERIT_MODE_HIGHER
    if grade_index >= len(GRADES) - 1:
        raise CalcError(
            "'%s' เป็นเกรดสูงสุดแล้ว ไม่มีเกรดที่สูงกว่าให้สืบทอด"
            % GRADES[grade_index]
        )
    if target_grade_index <= grade_index:
        raise CalcError(
            "โหมด '%s' เกรดเป้าหมายต้องสูงกว่า '%s'"
            % (INHERIT_MODE_HIGHER, GRADES[grade_index])
        )

    column = target_grade_index - HIGHER_TARGET_OFFSET
    if not 0 <= column < len(INHERIT_HIGHER[level]):
        raise CalcError(
            "ไม่มีข้อมูลค่าสืบทอดแบบ '%s' สำหรับเกรดเป้าหมาย '%s'"
            % (INHERIT_MODE_HIGHER, GRADES[target_grade_index])
        )
    return INHERIT_HIGHER[level][column]


def melt(pieces, ratio=MATERIAL_BLUE_RATIO):
    """หลอมชิ้นส่วนเป็นก้อน คืน (จำนวนก้อนเต็ม, เศษที่เหลือ)

    เช่น 131 ชิ้น -> (13 ก้อน, เศษ 1 ชิ้น)
    """
    if pieces <= 0:
        return 0, 0
    return pieces // ratio, pieces % ratio


def pieces_value(pieces, unit_price, ratio=MATERIAL_BLUE_RATIO):
    """มูลค่าของชิ้นส่วนทั้งหมด คิดตามสัดส่วน ไม่ปัดทิ้งและไม่ปัดขึ้น

    เศษที่ยังหลอมไม่ครบก็นับเป็นทุนด้วย ถึงจะเอาไปขายตอนนี้ไม่ได้ก็ตาม
    เช่น 455 ชิ้น (45 ก้อน + เศษ 5) ที่ก้อนละ 3.5 -> 45.5 x 3.5 = 159.25
    """
    if pieces <= 0 or unit_price <= 0:
        return 0.0
    return pieces / float(ratio) * unit_price


# ---------------------------------------------------------------------------
# บันไดวัสดุ — แยกลง / หลอมขึ้น / คิดโอกาสตีบวก
# ---------------------------------------------------------------------------

def ladder(line):
    """บันไดของสายที่เลือก (LINE_BLUE หรือ LINE_RED)"""
    if line not in LADDERS:
        raise CalcError("ไม่รู้จักสายวัสดุ: %s" % line)
    return LADDERS[line]


def tier_pieces(rows, index):
    """ของชั้น index จำนวน 1 อัน คิดเป็นชิ้นส่วนชั้นล่างสุดกี่ชิ้น"""
    if not 0 <= index < len(rows):
        raise CalcError("ไม่มีชั้นที่ %s ในบันไดนี้" % index)
    total = 1
    for tier in rows[1:index + 1]:
        total *= tier["per"]
    return total


def tier_scale(rows):
    """มูลค่าเป็นชิ้นส่วนของทุกชั้นเรียงตามบันได เช่น (1, 10, 100, 1000)"""
    return tuple(tier_pieces(rows, i) for i in range(len(rows)))


def to_pieces(rows, counts):
    """รวมของที่มีอยู่ทุกชั้นเป็นจำนวนชิ้นส่วนทั้งหมด

    counts เรียงตามบันได (ชั้นล่างสุดก่อน) ใส่ไม่ครบก็ได้ ตัวที่ขาดนับเป็น 0
    """
    scale = tier_scale(rows)
    total = 0
    for i, amount in enumerate(counts):
        if i >= len(scale):
            break
        total += max(0, int(amount or 0)) * scale[i]
    return total


def split_down(rows, pieces):
    """แยกชิ้นส่วนทั้งหมดออกเป็นของแต่ละชั้น ไล่จากชั้นสูงสุดลงมา

    คืน list ยาวเท่าบันได ตำแหน่งตรงกับชั้น เช่น 13,457 -> [7, 5, 4, 13]
    เศษที่ไม่พอขึ้นชั้นถัดไปค้างอยู่ชั้นล่าง ไม่ปัดขึ้นและไม่ปัดทิ้ง
    """
    out = [0] * len(rows)
    if pieces <= 0:
        return out
    left = int(pieces)
    for i in range(len(rows) - 1, -1, -1):
        worth = tier_pieces(rows, i)
        out[i] = left // worth
        left -= out[i] * worth
    return out


def success_chance(pieces, needed):
    """โอกาสตีบวกสำเร็จเป็น % จากจำนวนชิ้นส่วนที่ใส่ลงไป

    ค่าใน UPGRADE_RED คือจำนวนที่ทำให้เต็ม 100% — ผู้ใช้ยืนยันจากในเกมว่า
    ถุงมือราชันย์ +8 -> +9 เกรดเซียน ใช้ 661 ชิ้น = 100% ซึ่งตรงกับ
    UPGRADE_RED[9][4] = 661 พอดี  ใส่เกินไม่ได้อะไรเพิ่ม จึงตันที่ 100
    """
    if needed <= 0:
        return 100.0
    if pieces <= 0:
        return 0.0
    return min(100.0, pieces / float(needed) * 100.0)


# ---------------------------------------------------------------------------
# แผนการไต่เกรด — สืบทอดข้ามเกรดได้ทีละเกรด และระดับร่วงทุกครั้งที่สืบ
# ---------------------------------------------------------------------------

def upgrade_plan(start_grade, start_level, target_grade, target_level):
    """ไล่ทีละขั้นจากของที่ถืออยู่ ไปจนถึงเกรด+ระดับที่ตั้งไว้

    กติกาที่ผู้ใช้ยืนยัน:
      - สืบทอดข้ามเกรดได้ "ทีละเกรด" เท่านั้น ข้ามรวดเดียวไม่ได้
      - ทุกครั้งที่สืบ ระดับร่วงตาม HIGHER_RESULT_LEVEL (+15 -> +10, +10 -> +6)
      - ตารางสืบทอดเริ่มที่ +10 ถ้าร่วงต่ำกว่านั้นต้องตีขึ้นมาก่อนจึงสืบต่อได้
        (เคสนี้ทำให้มีค่าชิ้นส่วนโผล่กลางทาง ไม่ใช่แค่ตอนท้าย)
      - ถึงเกรดเป้าหมายแล้วค่อยตีบวกต่อจนถึงระดับที่ต้องการ

    คืน dict: steps (รายการขั้นตอน), pieces (ชิ้นส่วนรวม), gold (ค่าสืบทอดรวม),
    final_level (ระดับที่ได้จริง), overshoot (ได้สูงกว่าที่ขอไหม)
    """
    _check_grade(start_grade)
    _check_grade(target_grade)
    for name, lv in (("ระดับปัจจุบัน", start_level), ("ระดับเป้าหมาย", target_level)):
        if not MIN_LEVEL <= lv <= MAX_LEVEL:
            raise CalcError("%s ต้องอยู่ระหว่าง +%d ถึง +%d"
                            % (name, MIN_LEVEL, MAX_LEVEL))
    if target_grade < start_grade:
        raise CalcError("เกรดเป้าหมายต่ำกว่าเกรดปัจจุบัน สืบทอดย้อนลงไม่ได้")

    steps = []
    pieces = 0
    gold = 0
    grade = start_grade
    level = start_level

    while grade < target_grade:
        if level < MIN_INHERIT_LEVEL:
            # ยังสืบต่อไม่ได้ ต้องตีขึ้นไปให้ถึงระดับต่ำสุดที่ตารางสืบทอดรองรับ
            need = upgrade_pieces(level, MIN_INHERIT_LEVEL, grade)
            pieces += need
            steps.append({"kind": "upgrade", "grade": grade, "from": level,
                          "to": MIN_INHERIT_LEVEL, "pieces": need})
            level = MIN_INHERIT_LEVEL

        nxt = grade + 1
        cost = inherit_cost(INHERIT_MODE_HIGHER, level, grade, nxt)
        after = HIGHER_RESULT_LEVEL[level]
        gold += cost
        steps.append({"kind": "inherit", "grade": grade, "to_grade": nxt,
                      "from": level, "to": after, "gold": cost})
        grade = nxt
        level = after

    if level < target_level:
        need = upgrade_pieces(level, target_level, grade)
        pieces += need
        steps.append({"kind": "upgrade", "grade": grade, "from": level,
                      "to": target_level, "pieces": need})
        level = target_level

    return {
        "steps": steps,
        "pieces": pieces,
        "gold": gold,
        "final_level": level,
        # สืบมาแล้วได้สูงกว่าที่ขอ — ลดระดับลงไม่ได้ จึงต้องบอกตามจริง
        "overshoot": level > target_level,
    }


def available_targets(mode, grade_index):
    """รายชื่อเกรดเป้าหมายที่เลือกได้จริงสำหรับโหมดนี้ (ใช้กรอง combobox)"""
    if mode == INHERIT_MODE_SAME:
        return [GRADES[grade_index]]
    if mode == INHERIT_MODE_HIGHER:
        top = HIGHER_TARGET_OFFSET + len(INHERIT_HIGHER[MAX_LEVEL])
        return [GRADES[i] for i in range(grade_index + 1, min(top, len(GRADES)))]
    return list(GRADES)


def _check_grade(grade_index):
    if not 0 <= grade_index < len(GRADES):
        raise CalcError("เกรดไม่ถูกต้อง")


def _check_level_range(start_level, end_level):
    for name, lv in (("ระดับ", start_level), ("ถึง", end_level)):
        if not MIN_LEVEL <= lv <= MAX_LEVEL:
            raise CalcError("%s ต้องอยู่ระหว่าง +%d ถึง +%d (ได้ %s)"
                            % (name, MIN_LEVEL, MAX_LEVEL, lv))
    if start_level > end_level:
        raise CalcError("ระดับเริ่มต้น (+%d) ต้องไม่มากกว่าระดับปลายทาง (+%d)"
                        % (start_level, end_level))


# ---------------------------------------------------------------------------
# ตรวจความสม่ำเสมอของตาราง — เรียกตอน start เพื่อจับข้อมูลพังตั้งแต่เนิ่นๆ
# ---------------------------------------------------------------------------

def validate_tables(tolerance=0.05):
    """ตรวจ "โครงสร้าง" ของตาราง ไม่ใช่ความสวยของตัวเลข

    ข้อมูลจริงจากเกมไม่ได้เรียบเป๊ะ (เช่น INHERIT_HIGHER lv15 ต่ำกว่า lv14 จริงๆ)
    ตัวตรวจนี้จึงดูแค่สิ่งที่ผิดแน่ๆ เช่น จำนวนคอลัมน์ไม่ครบ ระดับขาด หรือค่าติดลบ
    คืน list ของข้อความปัญหา (list ว่าง = ผ่าน)
    """
    problems = []

    for name, table, width in (("INHERIT_SAME", INHERIT_SAME, 6),
                               ("INHERIT_HIGHER", INHERIT_HIGHER, 5),
                               ("UPGRADE_RED", UPGRADE_RED, 6)):
        for lv, row in sorted(table.items()):
            if len(row) != width:
                problems.append("%s lv%d มี %d คอลัมน์ (ต้องมี %d)"
                                % (name, lv, len(row), width))
            if any(v <= 0 for v in row):
                problems.append("%s lv%d มีค่าที่ไม่เป็นบวก: %s" % (name, lv, row))
            if sorted(row) != list(row):
                problems.append("%s lv%d ไม่เรียงจากน้อยไปมากตามเกรด: %s"
                                % (name, lv, row))

    expected = set(range(MIN_INHERIT_LEVEL, MAX_LEVEL + 1))
    for name, table in (("INHERIT_SAME", INHERIT_SAME),
                        ("INHERIT_HIGHER", INHERIT_HIGHER)):
        missing = expected - set(table)
        if missing:
            problems.append("%s ขาดระดับ %s" % (name, sorted(missing)))
    missing = set(range(MIN_LEVEL, MAX_LEVEL + 1)) - set(UPGRADE_RED)
    if missing:
        problems.append("UPGRADE_RED ขาดระดับ %s" % sorted(missing))

    width = len(INHERIT_HIGHER[MAX_LEVEL])
    if width + HIGHER_TARGET_OFFSET != len(GRADES):
        problems.append(
            "INHERIT_HIGHER มี %d คอลัมน์ + offset %d ไม่พอดีกับ GRADES %d เกรด"
            % (width, HIGHER_TARGET_OFFSET, len(GRADES)))

    for lv, result in sorted(HIGHER_RESULT_LEVEL.items()):
        if not MIN_LEVEL <= result < lv:
            problems.append("HIGHER_RESULT_LEVEL[%d] = %d ไม่สมเหตุสมผล" % (lv, result))

    return problems


def anomalies():
    """จุดที่ตัวเลขสวนทางกับแนวโน้ม — เป็นข้อมูลจริง ไม่ใช่ error

    ใช้ตอนคัดลอกตารางใหม่จากเกม จะได้เห็นว่าพิมพ์ตกหรือเปล่า
    """
    notes = []
    for name, table in (("INHERIT_SAME", INHERIT_SAME),
                        ("INHERIT_HIGHER", INHERIT_HIGHER),
                        ("UPGRADE_RED", UPGRADE_RED)):
        levels = sorted(table)
        for col in range(len(table[levels[0]])):
            for prev, cur in zip(levels, levels[1:]):
                if table[cur][col] < table[prev][col]:
                    notes.append("%s คอลัมน์ %d: lv%d=%s ลดลงเหลือ lv%d=%s"
                                 % (name, col, prev, table[prev][col],
                                    cur, table[cur][col]))
    return notes


if __name__ == "__main__":
    issues = validate_tables()
    if issues:
        print("พบปัญหาโครงสร้าง %d จุด:" % len(issues))
        for p in issues:
            print("  -", p)
    else:
        print("โครงสร้างตารางผ่านทั้งหมด")
    notes = anomalies()
    if notes:
        print()
        print("จุดที่ตัวเลขสวนแนวโน้ม (เป็นข้อมูลจริงจากเกม ไม่ใช่ error):")
        for n in notes:
            print("  -", n)
