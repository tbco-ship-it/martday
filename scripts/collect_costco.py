#!/usr/bin/env python3
"""Costco Korea warehouses: hours, closures (specialDayOpeningList), rule text, address, geo. Public REST."""
import json, re, time, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/stores/costco.json"
req = urllib.request.Request("https://www.costco.co.kr/rest/v2/korea/stores?fields=FULL&pageSize=50", headers={"User-Agent": "Mozilla/5.0"})
d = json.load(urllib.request.urlopen(req, timeout=30))
out = []
for s in d["stores"]:
    oh = s.get("openingHours", {})
    wd = oh.get("weekDayOpeningList", [])
    hours = ""
    if wd:
        o, c = wd[0].get("openingTime", {}), wd[0].get("closingTime", {})
        hours = f"{o.get('formattedHour','')}~{c.get('formattedHour','')}".replace("오전 ", "").replace("오후 ", "")
        try:
            h1, h2 = o["hour"], c["hour"] + (12 if "오후" in c.get("formattedHour", "") and c["hour"] < 12 else 0)
            hours = f"{h1:02d}:{o['minute']:02d}~{h2:02d}:{c['minute']:02d}"
        except Exception: pass
    closures = [x["date"][:10] for x in oh.get("specialDayOpeningList", []) if x.get("closed")]
    rule = re.sub(r"<[^>]+>", "", s.get("warehouseInformation") or "")
    out.append({"brand": "costco", "id": s.get("warehouseCode") or s["name"], "name": "코스트코 " + s["displayName"],
                "area": (s["address"].get("line1") or "").split()[0], "address": s["address"].get("line1", ""),
                "address_lot": s["address"].get("line2", ""), "lat": s["geoPoint"]["latitude"], "lng": s["geoPoint"]["longitude"],
                "phone": s["address"].get("phone", ""), "hours": hours, "closure_rule": rule.strip(), "closures_iso": closures,
                "holiday_note": "명절(설·추석) 당일 휴무, 전날은 19:00까지 영업" if "전일" in rule else ""})
OUT.write_text(json.dumps({"fetched": time.strftime("%Y-%m-%d"), "stores": out}, ensure_ascii=False, indent=1))
print("costco", len(out), out[0]["name"], out[0]["hours"], out[0]["closures_iso"][:3])
