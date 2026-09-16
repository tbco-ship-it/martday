#!/usr/bin/env python3
"""Homeplus stores list, hours, closures and coordinates.
Source: my.homeplus.co.kr store API (public endpoint)."""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/stores/homeplus.json"

UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://my.homeplus.co.kr/store?hyper=Y",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
}


def fetch_stores():
    data = urllib.parse.urlencode({
        "viewHomeplus": "H",
        "viewSpecial": "S",
        "viewExpress": "",
        "viewPlus": "",
        "draw": "1",
        "pageSize": "2000",
        "sortFlag": "N",
        "searchRegion": "",
        "locatePage": "N",
        "searchStoreNm": ""
    }).encode()
    req = urllib.request.Request("https://my.homeplus.co.kr/store/get_list", data=data, headers=UA)
    res = urllib.request.urlopen(req, timeout=30)
    body = res.read().decode("utf-8")
    return json.loads(body).get("data", [])


def main():
    raw_list = fetch_stores()
    out = []
    for s in raw_list:
        name = s.get("storKorNm", "").strip()
        div_cd = s.get("storDivCd", "")
        # Prefix with 홈플러스
        full_name = f"홈플러스 {name}" if not name.startswith("홈플러스") else name
        if div_cd == "S" and "스페셜" not in full_name:
            full_name = f"홈플러스 스페셜 {name}"

        addr = (s.get("storAddr") or "").strip()
        area = addr.split()[0] if addr else ""

        # Parse coordinates
        lat = float(s["storLat"]) if s.get("storLat") else None
        lng = float(s["storLon"]) if s.get("storLon") else None

        # Parse closures
        dayoff_raw = s.get("storDayoffCntt") or ""
        dates = re.findall(r"(\d{1,2})/(\d{1,2})", dayoff_raw)
        closures = [f"{int(m)}/{int(d)}" for m, d in dates]

        # Check Chuseok holiday note (9/24 ~ 9/27)
        holiday_notes = []
        for m, d in dates:
            if int(m) == 9 and 24 <= int(d) <= 27:
                if int(d) == 25:
                    holiday_notes.append("추석 당일(9/25) 휴무")
                else:
                    holiday_notes.append(f"추석 연휴(9/{d}) 휴무")
        sles = s.get("storSlesTime") or ""
        if "임시휴업" in sles:
            holiday_notes.append("마트 임시휴업")
        elif "영업종료" in sles:
            holiday_notes.append("영업종료")

        rec = {
            "brand": "homeplus",
            "id": str(s.get("storId") or s.get("storCd")),
            "name": full_name,
            "area": area,
            "address": addr,
            "lat": lat,
            "lng": lng,
            "phone": (s.get("storTphnNo") or "").strip(),
            "hours": sles.strip(),
            "closure_rule": dayoff_raw.strip(),
            "closures": closures,
            "holiday_note": ", ".join(holiday_notes),
            "holiday_days": [int(d) for _, d in dates]
        }
        out.append(rec)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"fetched": time.strftime("%Y-%m-%d"), "stores": out}, ensure_ascii=False, indent=1))
    has_closures = sum(1 for r in out if r.get("closures"))
    has_coords = sum(1 for r in out if r.get("lat") is not None)
    print(f"homeplus stores: {len(out)}, with closures: {has_closures} ({has_closures/len(out):.1%}), with coords: {has_coords} ({has_coords/len(out):.1%})")


if __name__ == "__main__":
    main()
