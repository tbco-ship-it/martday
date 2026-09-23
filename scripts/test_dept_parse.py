#!/usr/bin/env python3
"""Offline parser tests for collect_dept.py against pages saved on 2026-09-23 (scripts/fixtures/dept/).
Run: .venv/bin/python scripts/test_dept_parse.py
IKEA fixtures are the single storeConfig <script type="text/hydrate"> tag cut verbatim from the full page."""
import json, sys, unittest
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import collect_dept as cd

FX = HERE / "fixtures/dept"
TODAY = date(2026, 9, 23)


def fx(name):
    return (FX / name).read_text(encoding="utf-8")


class Lotte(unittest.TestCase):
    def test_store_list(self):
        stores = cd.parse_lotte_stores(fx("lotte_0001.html"))
        self.assertEqual(len(stores), 55)
        by = {c: (n, t) for c, n, t in stores}
        self.assertEqual(by["0001"], ("본점", "백화점"))
        self.assertEqual(by["0349"], ("수원점", "타임빌라스"))
        self.assertEqual(by["0406"], ("의왕점", "프리미엄 아울렛"))
        self.assertEqual(by["0403"], ("피트인 산본점", "쇼핑몰"))

    def test_bonjeom_closed(self):
        p = cd.parse_lotte_page(fx("lotte_0001.html"), TODAY, "본점")
        self.assertEqual(sorted(p["closed"]), ["2026-09-24", "2026-09-25", "2026-10-12"])
        self.assertEqual(p["months"], {"2026-09": "ok", "2026-10": "ok"})
        ext = [s for s in p["special"] if s["kind"] == "extend"]
        self.assertIn({"date": "2026-09-26", "kind": "extend", "hours": "10:30~20:30"}, ext)

    def test_page_identity_guard(self):
        with self.assertRaises(ValueError):
            cd.parse_lotte_page(fx("lotte_0001.html"), TODAY, "잠실점")

    def test_suji_holiday_hours(self):
        p = cd.parse_lotte_page(fx("lotte_0405.html"), TODAY, "수지점")
        self.assertEqual(p["closed"], [])
        self.assertEqual(p["special"], [{"date": "2026-09-25", "kind": "holiday", "hours": "12:00~22:00"}])

    def test_unpublished_month(self):
        p = cd.parse_lotte_page(fx("lotte_0001.html"), date(2026, 10, 5), "본점")
        self.assertEqual(p["months"], {"2026-10": "ok", "2026-11": "unpublished"})


class Shinsegae(unittest.TestCase):
    def test_bonjeom(self):
        p = cd.parse_ssg_page(fx("ssg_SC00001.html"), TODAY)
        self.assertEqual(p["name"], "본점")
        self.assertEqual(p["closed"], ["2026-09-25", "2026-09-26", "2026-10-26"])
        self.assertEqual(p["months"], {"2026-09": "ok", "2026-10": "ok"})

    def test_label_must_start_with_hyujeomil(self):
        h = ('<title>신세계백화점 테스트점 한눈에 보기</title><div class="cal1"><span class="num">09</span></div>'
             '<div class="cal2"><span class="num">10</span></div><div class="day cal1">'
             '<div ><span>29</span></div>'
             '<div class="x" ><span class="sr-only">휴점일</span><span>30</span></div>'
             '<div class="" ><span class="sr-only">연장영업, 아카데미 휴점일</span><span>1</span></div>'
             '<div class="" ><span class="sr-only">아카데미 휴점일</span><span>2</span></div>'
             '<div class="" ><span class="sr-only">휴점일, 아카데미 휴점일</span><span>3</span></div></li>')
        p = cd.parse_ssg_page(h, TODAY)
        self.assertEqual(p["closed"], ["2026-09-30", "2026-10-03"])

    def test_empty_template_is_no_store(self):
        self.assertIsNone(cd.parse_ssg_page("<title>신세계백화점  한눈에 보기</title>", TODAY))


class Hyundai(unittest.TestCase):
    def test_branches(self):
        br = cd.parse_hyundai_branches(fx("hyundai_store_B00121000.html"))
        codes = [b[0] for b in br]
        self.assertEqual(len(codes), 23)
        self.assertNotIn("B00189900", codes)  # 도쿄 (global) is not in branch_list
        by = {b[0]: b for b in br}
        self.assertEqual(by["B00140000"][1:3], ("더현대 서울", "더현대"))
        self.assertEqual(by["B00124000"][2], "커넥트현대")
        self.assertEqual(by["B00172000"][2], "현대아울렛")
        self.assertIn("/newPortal/outlet/", by["B00172000"][3])

    def test_apgujeong(self):
        j = json.loads(fx("hyundai_B00121000_202609.json"))
        status, closed, special, problems = cd.parse_hyundai_month(j, "B00121000", "202609")
        self.assertEqual((status, closed, problems), ("ok", ["2026-09-25", "2026-09-26"], []))
        self.assertEqual(len(special), 10)
        self.assertEqual(special[0], {"date": "2026-09-04", "kind": "extend", "extend_minutes": 30})

    def test_trade_center(self):
        j = json.loads(fx("hyundai_B00122000_202609.json"))
        self.assertEqual(cd.parse_hyundai_month(j, "B00122000", "202609")[1], ["2026-09-24", "2026-09-25"])

    def test_empty_is_unpublished_and_9_is_no_closure(self):
        empty = {"holyDay": [], "month": "10", "year": 2026}  # live response for 2026-10 on 2026-09-23
        self.assertEqual(cd.parse_hyundai_month(empty, "B00121000", "202610")[0], "unpublished")
        nine = {"holyDay": [{"branchCd": "B00121000", "yearmonth": "202610", "extendBreakTy": "9", "theDay": "20261001", "delYn": "N"}]}
        self.assertEqual(cd.parse_hyundai_month(nine, "B00121000", "202610")[:2], ("ok", []))


class Galleria(unittest.TestCase):
    def test_blocks(self):
        h = fx("galleria_luxuryhall.html")
        p = cd.parse_galleria_page(h, "luxuryhall", TODAY)
        self.assertEqual((p["name"], p["closed"], p["months"]), ("명품관", ["2026-09-25", "2026-09-26"], {"2026-09": "ok"}))
        self.assertEqual(cd.parse_galleria_page(h, "timeworld", TODAY)["closed"], ["2026-09-24", "2026-09-25"])
        self.assertEqual(cd.parse_galleria_page(h, "jinju", TODAY)["name"], "진주점")


class AK(unittest.TestCase):
    def test_suwon(self):
        h = fx("ak_02.html")
        self.assertEqual(cd.parse_ak_nav(h)["02"], ("수원", "백화점"))
        self.assertEqual(cd.parse_ak_page(h, TODAY), {"closed": ["2026-09-25"], "months": {"2026-09": "ok"}})

    def test_hongdae_muhyu(self):
        h = fx("ak_51.html")
        self.assertEqual(cd.parse_ak_nav(h)["51"], ("홍대", "쇼핑몰"))
        self.assertEqual(cd.parse_ak_page(h, TODAY), {"closed": [], "months": {"2026-09": "ok"}})

    def test_mismatch_is_error(self):
        h = fx("ak_51.html").replace("<span>무휴</span>", "<span>25일</span>", 1)
        with self.assertRaises(ValueError):
            cd.parse_ak_page(h, TODAY)


class Ikea(unittest.TestCase):
    def test_goyang(self):
        p = cd.parse_ikea_page(fx("ikea_goyang_storeconfig.html"))
        self.assertEqual(p["name"], "고양점")
        self.assertEqual(p["closed"], ["2026-09-25", "2027-02-07"])

    def test_dong_busan_exceptions(self):
        p = cd.parse_ikea_page(fx("ikea_dong-busan_storeconfig.html"))
        self.assertEqual(p["closed"], ["2026-09-25"])
        self.assertEqual(p["special"][0], {"date": "2026-09-24", "kind": "exception", "hours": "10:00~21:00", "note": "추석연휴"})

    def test_missing_config_is_error(self):
        with self.assertRaises(ValueError):
            cd.parse_ikea_page("<html></html>")


class Dates(unittest.TestCase):
    def test_month_rollover(self):
        self.assertEqual(cd.month_keys(date(2026, 12, 20)), ["2026-12", "2027-01"])
        self.assertEqual(cd.year_for(1, date(2026, 12, 20)), 2027)
        self.assertEqual(cd.year_for(12, date(2027, 1, 2)), 2026)


if __name__ == "__main__":
    unittest.main()
