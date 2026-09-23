#!/usr/bin/env python3
"""E-mart family (이마트·트레이더스·에브리데이·노브랜드·스타필드마켓) store list + this month's closures.
Source: store.emart.com public endpoints (listAll.do JSON, view.do HTML)."""
import html, json, re, sys, time, urllib.request, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/stores/emart.json"
UA = {"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"}


def post(url, data=b""):
    req = urllib.request.Request(url, data=data, headers=UA)
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")


def get(url):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")


def brand_of(name):
    for k, v in (("트레이더스", "traders"), ("에브리데이", "everyday"), ("노브랜드", "nobrand"), ("노브렌드", "nobrand"), ("스타필드", "starfield"), ("몰리스", "skip"), ("일렉트로마트", "skip"), ("토이킹덤", "skip")):
        if k in name: return v
    return "emart" if "이마트" in name else "other"


def parse_detail(h):
    t = html.unescape(re.sub(r"<[^>]+>", "\n", h))
    t = re.sub(r"\n\s*\n+", "\n", t)
    def after(label, n=2):
        m = re.search(re.escape(label) + r"\s*\n([^\n]*)(?:\n([^\n]*))?", t)
        return [x.strip() for x in (m.groups() if m else ()) if x and x.strip()][:n]
    hours = (after("쇼핑시간", 1) or [""])[0]
    rule = re.search(r"※\s*([^\n]*?휴점[^\n]*)", t)
    closed = (after("휴점일", 1) or [""])[0]
    dates = re.findall(r"(\d{1,2})/(\d{1,2})", closed)
    phone = (after("고객센터", 1) or [""])[0]
    parking = (after("주차시설", 1) or [""])[0]
    road = re.search(r'road-name.*?<dd class="data">([^<]+)</dd>', h, re.S)
    lot = re.search(r'lot-number.*?<dd class="data">([^<]+)</dd>', h, re.S)
    xy = re.search(r'data-x="([\d.]+)" data-y="([\d.]+)"', h)
    return {"hours": hours, "closure_rule": rule.group(1).strip() if rule else "", "closures_raw": closed,
            "closures": [f"{int(m)}/{int(d)}" for m, d in dates], "phone": phone, "parking": parking,
            "address": html.unescape(road.group(1).strip()) if road else "", "address_lot": html.unescape(lot.group(1).strip()) if lot else "",
            "lat": float(xy.group(1)) if xy else None, "lng": float(xy.group(2)) if xy else None}


# 에브리데이·노브랜드 상세(주소·좌표·영업시간·전화·주차)는 거의 안 바뀐다. 매일 519곳을 다 받으면 러너 제한
# (collect 240초)을 넘기므로 지난 결과를 재사용하고, 오래된 순으로 하루 SSM_REFRESH 곳씩만 다시 받는다.
# 휴점일은 여기서 받지 않는다 — SSM 휴점일은 지금처럼 목록의 holidayDay 로만 계산한다.
SSM_KEYS = ("address", "address_lot", "lat", "lng", "phone", "parking", "hours")
SSM_REFRESH = int(sys.argv[1]) if len(sys.argv) > 1 else 60
SSM_MAX_AGE = 14


def main():
    lst = json.loads(post("https://store.emart.com/branch/listAll.do"))["branchList"]
    prev = {}
    if OUT.exists():
        prev = {r["id"]: r for r in json.loads(OUT.read_text()).get("stores", []) if r.get("ssm_detail")}
    today = time.strftime("%Y-%m-%d")
    stale = sorted((r.get("ssm_detail", ""), i) for i, r in prev.items()
                   if r.get("ssm_detail", "") < time.strftime("%Y-%m-%d", time.localtime(time.time() - SSM_MAX_AGE * 86400)))
    refresh = {i for _, i in stale[:SSM_REFRESH]}
    fetched_ssm = 0
    out = []
    for i, b in enumerate(lst):
        brand = brand_of(b["jijumName"])
        if brand in ("skip", "other"): continue
        rec = {"brand": brand, "id": b["jijumId"], "name": b["jijumName"], "area": b["areaName"],
               "holiday_days": [d for d in (b["holidayDay1"], b["holidayDay2"], b["holidayDay3"]) if d]}
        if brand in ("emart", "traders", "starfield"):
            try:
                rec.update(parse_detail(get(f"https://store.emart.com/branch/view.do?id={b['jijumId']}&culture=f&popup=null")))
            except Exception as e:
                rec["error"] = str(e)[:80]
            time.sleep(0.15)
        elif brand in ("everyday", "nobrand"):
            p = prev.get(b["jijumId"])
            if p and b["jijumId"] not in refresh:
                rec.update({k: p[k] for k in SSM_KEYS if k in p}, ssm_detail=p["ssm_detail"])
            else:
                try:
                    d = parse_detail(get(f"https://store.emart.com/branch/view.do?id={b['jijumId']}&culture=f&popup=null"))
                    rec.update({k: d[k] for k in SSM_KEYS}, ssm_detail=today)
                    fetched_ssm += 1
                except Exception as e:
                    if p:
                        rec.update({k: p[k] for k in SSM_KEYS if k in p}, ssm_detail=p["ssm_detail"])
                time.sleep(0.15)
        out.append(rec)
        if i % 100 == 0: print(i, len(lst), file=sys.stderr)
    OUT.write_text(json.dumps({"fetched": time.strftime("%Y-%m-%d"), "stores": out}, ensure_ascii=False, indent=1))
    print("stores", len(out), "detail", sum(1 for r in out if r.get("hours")), "ssm fetched", fetched_ssm)


if __name__ == "__main__":
    main()
