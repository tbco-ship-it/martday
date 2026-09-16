#!/usr/bin/env python3
"""Merge collected sources into data/stores.json (one schema) and expand this month's closure days to ISO dates."""
import calendar
import datetime as dt
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRANDS = {
    "emart": {"name": "이마트", "short": "이마트", "color": "#ffd400"},
    "traders": {"name": "트레이더스 홀세일 클럽", "short": "트레이더스", "color": "#00a862"},
    "starfield": {"name": "스타필드 마켓", "short": "스타필드 마켓", "color": "#2f6df6"},
    "everyday": {"name": "이마트 에브리데이", "short": "에브리데이", "color": "#f26522"},
    "nobrand": {"name": "노브랜드", "short": "노브랜드", "color": "#f5c400"},
    "costco": {"name": "코스트코", "short": "코스트코", "color": "#e31837"},
}
AREA_ALIAS = {"서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기", "강원특별자치도": "강원", "강원도": "강원", "충청북도": "충북", "충청남도": "충남", "전라북도": "전북", "전북특별자치도": "전북", "전라남도": "전남", "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주", "충청": "충청", "경상": "경상", "전라": "전라"}


def slugify(name):
    s = re.sub(r"\s+", "-", name.strip())
    s = re.sub(r"[^\w\-가-힣]", "", s)
    return s.lower()


def month_dates(days, year, month):
    out = []
    for d in days:
        try:
            d = int(d)
            if 1 <= d <= calendar.monthrange(year, month)[1]:
                out.append(dt.date(year, month, d).isoformat())
        except ValueError:
            pass
    return out


def md_to_iso(md_list, today):
    out = []
    for md in md_list:
        m, d = md.split("/")
        y = today.year if int(m) >= today.month else today.year + 1
        try:
            out.append(dt.date(y, int(m), int(d)).isoformat())
        except ValueError:
            pass
    return out


def main():
    today = dt.date.today()
    stores = []
    em = json.loads((ROOT / "data/stores/emart.json").read_text())
    for s in em["stores"]:
        closures = md_to_iso(s.get("closures", []), today) or month_dates(s.get("holiday_days", []), today.year, today.month)
        stores.append({
            "brand": s["brand"], "id": s["id"], "name": s["name"], "slug": slugify(s["name"]),
            "area": AREA_ALIAS.get(s.get("area", ""), s.get("area", "")), "address": s.get("address", ""),
            "lat": s.get("lat"), "lng": s.get("lng"), "phone": s.get("phone", ""), "parking": s.get("parking", ""),
            "hours": s.get("hours", ""), "closure_rule": s.get("closure_rule", ""), "closures": sorted(set(closures)),
            "holiday_note": "", "detail": bool(s.get("hours")),
        })
    co = json.loads((ROOT / "data/stores/costco.json").read_text())
    for s in co["stores"]:
        stores.append({
            "brand": "costco", "id": s["id"], "name": s["name"], "slug": slugify(s["name"]),
            "area": AREA_ALIAS.get(s.get("area", ""), s.get("area", "")), "address": s.get("address", ""),
            "lat": s.get("lat"), "lng": s.get("lng"), "phone": s.get("phone", ""), "parking": "",
            "hours": s.get("hours", ""), "closure_rule": s.get("closure_rule", ""), "closures": sorted(set(s.get("closures_iso", []))),
            "holiday_note": s.get("holiday_note", ""), "detail": True,
        })
    # de-dup slugs
    seen = {}
    for s in stores:
        if s["slug"] in seen:
            s["slug"] = f"{s['slug']}-{s['id']}"
        seen[s["slug"]] = 1
    (ROOT / "data/stores.json").write_text(json.dumps({"generated": today.isoformat(), "sources": {"emart": em["fetched"], "costco": co["fetched"]}, "brands": BRANDS, "stores": stores}, ensure_ascii=False, indent=0))
    from collections import Counter
    print(len(stores), Counter(s["brand"] for s in stores), Counter(s["area"] for s in stores).most_common(6))


if __name__ == "__main__":
    main()
