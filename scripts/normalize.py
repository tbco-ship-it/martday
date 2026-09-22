#!/usr/bin/env python3
"""Merge collected sources into data/stores.json (one schema) and expand this month's closure days to ISO dates."""
import calendar
import datetime as dt
import hashlib
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
    "homeplus": {"name": "홈플러스", "short": "홈플러스", "color": "#e60012"},
    "lottemart": {"name": "롯데마트", "short": "롯데마트", "color": "#da291c"},
}
AREA_ALIAS = {"서울특별시": "서울", "서울시": "서울", "부산광역시": "부산", "부산시": "부산", "대구광역시": "대구", "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기", "강원특별자치도": "강원", "강원도": "강원", "충청북도": "충북", "충청남도": "충남", "전라북도": "전북", "전북특별자치도": "전북", "전라남도": "전남", "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주", "충청": "충청", "경상": "경상", "전라": "전라"}


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


def md_to_iso(md_list, ref):
    """Expand 'M/D' notices to ISO using the *source fetch date* as the year reference, so re-normalizing an
    older raw file after a failed collection never rolls a past notice into next year."""
    out = []
    for md in md_list:
        m, d = md.split("/")
        y = ref.year if int(m) >= ref.month else ref.year + 1
        try:
            out.append(dt.date(y, int(m), int(d)).isoformat())
        except ValueError:
            pass
    return out


def store_state(hours, note):
    """영업종료 > 임시휴업 > open. Homeplus publishes closures as free text in the hours field
    ('마트 임시휴업. 몰영업시간 10:00~21:00', '계룡점 영업종료로 단골매장을 변경해주세요.'); an empty closure
    list on such a store means 'no schedule', not 'open'."""
    t = f"{hours} {note}"
    if "영업종료" in t:
        return "closed"
    if "임시휴업" in t or "임시 휴업" in t:
        return "temp_closed"
    return "open"


def fetched_date(doc, today):
    try:
        return dt.date.fromisoformat(doc.get("fetched", "")[:10])
    except ValueError:
        return today


def main():
    today = dt.date.today()
    stores = []
    em = json.loads((ROOT / "data/stores/emart.json").read_text())
    em_ref = fetched_date(em, today)
    for s in em["stores"]:
        closures = md_to_iso(s.get("closures", []), em_ref) or month_dates(s.get("holiday_days", []), em_ref.year, em_ref.month)
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
    sources = {"emart": em["fetched"], "costco": co["fetched"]}
    hp_file = ROOT / "data/stores/homeplus.json"
    if hp_file.exists():
        hp = json.loads(hp_file.read_text())
        sources["homeplus"] = hp.get("fetched", today.isoformat())
        hp_ref = fetched_date(hp, today)
        for s in hp.get("stores", []):
            closures = md_to_iso(s.get("closures", []), hp_ref) or month_dates(s.get("holiday_days", []), hp_ref.year, hp_ref.month)
            stores.append({
                "brand": "homeplus", "id": s["id"], "name": s["name"], "slug": slugify(s["name"]),
                "area": AREA_ALIAS.get(s.get("area", ""), s.get("area", "")), "address": s.get("address", ""),
                "lat": s.get("lat"), "lng": s.get("lng"), "phone": s.get("phone", ""), "parking": "",
                "hours": s.get("hours", ""), "closure_rule": s.get("closure_rule", ""), "closures": sorted(set(closures)),
                "holiday_note": s.get("holiday_note", ""), "detail": bool(s.get("hours")),
            })
    lm_file = ROOT / "data/stores/lottemart.json"
    if lm_file.exists():
        lm = json.loads(lm_file.read_text())
        sources["lottemart"] = lm.get("fetched", today.isoformat())
        lm_ref = fetched_date(lm, today)
        for s in lm.get("stores", []):
            closures = md_to_iso(s.get("closures", []), lm_ref) or month_dates(s.get("holiday_days", []), lm_ref.year, lm_ref.month)
            stores.append({
                "brand": "lottemart", "id": s["id"], "name": s["name"], "slug": slugify(s["name"]),
                "area": AREA_ALIAS.get(s.get("area", ""), s.get("area", "")), "address": s.get("address", ""),
                "lat": s.get("lat"), "lng": s.get("lng"), "phone": s.get("phone", ""), "parking": "",
                "hours": s.get("hours", ""), "closure_rule": s.get("closure_rule", ""), "closures": sorted(set(closures)),
                "holiday_note": s.get("holiday_note", ""), "detail": bool(s.get("hours")),
            })
    # 영업 상태: 영업종료·임시휴업 점포는 hours 문구를 state_note로 옮기고 hours를 비운다(영업시간·스키마·"영업" 판정에 쓰지 않게)
    for s in stores:
        s["state"] = store_state(s["hours"], s["holiday_note"])
        s["state_note"] = ""
        if s["state"] != "open":
            s["state_note"] = re.sub(r"<[^>]+>", " ", s["hours"]).strip(" .")
            s["hours"] = ""
            s["closures"] = []
    # 수집 실패·빈 응답이 정상 데이터를 덮지 않게: 브랜드별 점포 수가 직전 통합본의 70% 미만이면 중단(워크플로가 기존 파일을 유지)
    prev_file = ROOT / "data/stores.json"
    if prev_file.exists():
        from collections import Counter as _C
        prev = _C(x["brand"] for x in json.loads(prev_file.read_text())["stores"])
        cur = _C(x["brand"] for x in stores)
        for b, n in prev.items():
            if cur.get(b, 0) < n * 0.7:
                raise SystemExit(f"refusing to write: {b} dropped {n} -> {cur.get(b, 0)}")
    # de-dup slugs
    seen = {}
    for s in stores:
        if s["slug"] in seen:
            s["slug"] = f"{s['slug']}-{s['id']}"
        seen[s["slug"]] = 1
    # 점포별 "내용이 마지막으로 바뀐 날". 사이트맵 lastmod 에 쓴다 — 구글은 lastmod 가
    # "consistently and verifiably accurate" 할 때만 쓴다고 문서에 적어 두었으므로, 빌드한 날이 아니라
    # 실제로 값이 바뀐 날을 넣는다. 해시가 그대로면 날짜도 그대로 둔다.
    changed_file = ROOT / "data/changed.json"
    prev_changed = json.loads(changed_file.read_text()) if changed_file.exists() else {}
    changed = {}
    for s in stores:
        key = f"{s['brand']}/{s['slug']}"
        fp = hashlib.sha1(json.dumps([s.get(k) for k in ("name", "area", "address", "hours", "closures",
                                                         "state", "state_note", "holiday_note")],
                                     ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
        old = prev_changed.get(key)
        changed[key] = {"h": fp, "d": old["d"] if old and old.get("h") == fp else today.isoformat()}
    changed_file.write_text(json.dumps(changed, ensure_ascii=False, indent=0, sort_keys=True))
    (ROOT / "data/stores.json").write_text(json.dumps({"generated": today.isoformat(), "sources": sources, "brands": BRANDS, "stores": stores}, ensure_ascii=False, indent=0))
    from collections import Counter
    print(len(stores), Counter(s["brand"] for s in stores), Counter(s["area"] for s in stores).most_common(6))


if __name__ == "__main__":
    main()
