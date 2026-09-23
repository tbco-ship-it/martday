#!/usr/bin/env python3
"""Generate the static 마트휴무일 site into dist/."""
import argparse
import calendar
import datetime as dt
import hashlib
import json
import math
import shutil
from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
SITE = "마트휴무일"
KDAY = "월화수목금토일"
IKEA_CLOSED = ["2026-09-25", "2027-02-07"]  # 추석·설날 당일; 2027 설 이후엔 다음 해 날짜를 넣을 것


def kdate(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d.month}/{d.day}({KDAY[d.weekday()]})"


def km(a, b):
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b["lng"] - a["lng"]) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def alt_open(s, stores):
    """이 점포가 다음에 쉬는 날, 근처에서 문 여는 점포. 그 달 휴점일이 하나라도 확인된 점포만 '연다'고 센다
    (SSM 은 이번 달 휴점일만 알 수 있어서, 다음 달 날짜에 대해 휴점일이 없다는 건 '모른다'는 뜻이다)."""
    d = s.get("next_closure")
    if not (d and s.get("lat") and s.get("state", "open") == "open"):
        return None
    known = [x for x in stores if x is not s and x.get("lat") and x.get("state", "open") == "open"
             and any(c[:7] == d[:7] for c in x["closures"])]
    dist = [(km(s, x), x) for x in known]
    near3 = [x for k, x in dist if k <= 3]
    opens = sorted(((k, x) for k, x in dist if k <= 20 and d not in x["closures"]), key=lambda t: t[0])
    far = bool(opens) and opens[0][0] > 5  # 5km 안에 없으면 가장 가까운 두 곳만(20km 까지)
    opens = opens[:2] if far else [t for t in opens if t[0] <= 5][:4]
    return {"date": d, "n3": len(near3), "same3": sum(1 for x in near3 if d in x["closures"]), "far": far,
            "open": [(x, f"{k:.1f}") for k, x in opens]}


def ics(s, origin, base, b):
    """점포 휴무일 구독용 달력. 빌드마다 다시 쓰므로 구독한 달력 앱이 새 휴무일을 알아서 받는다."""
    url = f"{origin}{base}{b}/{s['slug']}/"
    uid = hashlib.md5(url.encode()).hexdigest()[:12]
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//martoday.com//holidays//KO", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", f"X-WR-CALNAME:{s['disp']} 휴무일", "X-WR-TIMEZONE:Asia/Seoul",
             "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H"]
    for c in s["closures"]:
        d = dt.date.fromisoformat(c)
        lines += ["BEGIN:VEVENT", f"UID:{uid}-{c}@martoday.com", f"DTSTAMP:{c.replace('-', '')}T000000Z",
                  f"DTSTART;VALUE=DATE:{d:%Y%m%d}", f"DTEND;VALUE=DATE:{d + dt.timedelta(days=1):%Y%m%d}",
                  f"SUMMARY:{s['disp']} 휴무", f"URL:{url}", "TRANSP:TRANSPARENT", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def month_grid(year, month):
    cal = calendar.Calendar(firstweekday=6)  # Sunday first
    return [[(d.isoformat() if d.month == month else "") for d in week] for week in cal.monthdatescalendar(year, month)]



def write_sitemaps(urls, origin, base, lastmod=None, limit=5000):
    """One sitemap index plus a file per section, so Search Console reports coverage per section
    instead of one opaque pile. urls is a list of (shard, path)."""
    shards = defaultdict(list)
    for shard, u in urls:
        shards[shard].append(u)
    for k in [k for k, v in shards.items() if len(v) < 10 and k != "core"]:
        shards["core"] += shards.pop(k)
    out = DIST / "sitemaps"
    out.mkdir(parents=True, exist_ok=True)
    names = []
    for shard in sorted(shards):
        rows = shards[shard]
        parts = [rows[i:i + limit] for i in range(0, len(rows), limit)] or [[]]
        for n, part in enumerate(parts, 1):
            fn = f"{shard}.xml" if len(parts) == 1 else f"{shard}-{n}.xml"
            def entry(u):
                d = lastmod.get(u) if isinstance(lastmod, dict) else lastmod
                return f"<url><loc>{escape(origin + base + u)}</loc>" + (f"<lastmod>{d}</lastmod>" if d else "") + "</url>"
            body = "\n".join(entry(u) for u in part)
            (out / fn).write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                                  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                  + body + "\n</urlset>")
            names.append(fn)
    idx = "".join(f"<sitemap><loc>{origin}{base}sitemaps/{n}</loc></sitemap>" for n in names)
    (DIST / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                                      '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                                      + idx + "</sitemapindex>")
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="/")
    ap.add_argument("--origin", default="https://martoday.com")
    ap.add_argument("--cname", default="martoday.com")
    ap.add_argument("--adsense-pub", default="pub-8425563704095379")
    args = ap.parse_args()
    base = args.base if args.base.endswith("/") else args.base + "/"
    origin = args.origin.rstrip("/")

    data = json.loads((ROOT / "data/stores.json").read_text())
    stores, brands = data["stores"], data["brands"]
    today = dt.date.today()
    months = [(today.year, today.month)]
    nm = today.replace(day=1) + dt.timedelta(days=32)
    months.append((nm.year, nm.month))
    tomorrow = (today + dt.timedelta(days=1)).isoformat()
    # 추석 2026-09-25: 당일 ±2일 동안만 제목·상태 문장에 추석 영업 여부를 앞세운다(지나면 자동 해제)
    chuseok = "2026-09-25"
    chuseok_live = "2026-09-10" <= today.isoformat() <= "2026-09-27"
    for s in stores:
        s["next_closure"] = next((c for c in s["closures"] if c >= today.isoformat()), None)
        s["brand_name"] = brands[s["brand"]]["short"]
        # 고시 데이터가 있는 점포만 판정: 휴무 / 영업 / None(미확인)
        s["chuseok"] = ("휴무" if chuseok in s["closures"] else "영업") if s["closures"] and s.get("state", "open") == "open" else None
    for s in stores:
        # 네이버 데이터랩: "에브리데이 남가좌점" 보다 "이마트에브리데이 남가좌" 가 45배 검색된다(OUTBOX/DATALAB_11TH_POPO_20260923.md).
        # URL(slug)은 그대로 두고 화면·제목 표기만 사람들이 치는 이름으로 쓴다.
        s["disp"] = "이마트" + s["name"] if s["brand"] == "everyday" and s["name"].startswith("에브리데이") else s["name"]
    for s in stores:
        s["alt"] = alt_open(s, stores)
    by_brand = defaultdict(list)
    by_area = defaultdict(list)
    for s in stores:
        by_brand[s["brand"]].append(s)
        by_area[s["area"] or "기타"].append(s)

    h = hashlib.md5()
    for f in sorted((ROOT / "static").glob("*")):
        h.update(f.read_bytes())
    v = h.hexdigest()[:8]
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]))
    env.filters["kdate"] = kdate
    env.globals.update(site=SITE, base=base, origin=origin, today=today.isoformat(), tomorrow=tomorrow, chuseok=chuseok, chuseok_live=chuseok_live, today_k=f"{today.month}월 {today.day}일({KDAY[today.weekday()]})", v=v,
                       adsense_pub=args.adsense_pub, brands=brands, months=months, month_grid=month_grid, KDAY=KDAY,
                       sources=data["sources"], coupang=json.loads((ROOT / "data/coupang.json").read_text()), n_stores=len(stores), areas=sorted(by_area, key=lambda a: -len(by_area[a])))

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    shutil.copytree(ROOT / "static", DIST / "static")
    slim = [{k: s.get(k, "") for k in ("brand", "name", "slug", "area", "lat", "lng", "hours", "closures", "holiday_note", "address", "state", "state_note")} for s in stores]
    (DIST / "static/stores.json").write_text(json.dumps({"brands": brands, "stores": slim}, ensure_ascii=False, separators=(",", ":")))

    urls = []

    def write(path, template, sm=None, **ctx):
        out = DIST / path
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(env.get_template(template).render(path=path, **ctx))
        urls.append((sm or path.split("/")[0] or "core", path))

    write("", "index.html", by_brand=by_brand)
    for page in ("about", "methodology", "privacy", "terms", "contact"):
        write(f"{page}/", f"{page}.html")
    write("guide/mandatory-closing/", "guide_mandatory.html")
    hdays = ["2026-09-24", "2026-09-25", "2026-09-26", "2026-09-27"]
    holiday_counts = {b: {d: sum(1 for s in lst if d in s["closures"]) for d in hdays} for b, lst in by_brand.items()}
    # 추석 당일 휴무 점포 목록(브랜드별) + 지역별 당일 휴무 수
    closed_day = {b: sorted([s for s in lst if chuseok in s["closures"]], key=lambda x: (x["area"], x["name"])) for b, lst in by_brand.items()}
    open_day = {b: sorted([s for s in lst if chuseok not in s["closures"] and s["closures"]], key=lambda x: (x["area"], x["name"])) for b, lst in by_brand.items()}
    area_counts = defaultdict(lambda: {"closed": 0, "total": 0, "inactive": 0, "unknown": 0})
    for s in stores:
        a = s["area"] or "기타"; area_counts[a]["total"] += 1
        if s.get("state", "open") != "open": area_counts[a]["inactive"] += 1
        elif chuseok in s["closures"]: area_counts[a]["closed"] += 1
        elif not s["closures"]: area_counts[a]["unknown"] += 1
    write("guide/holidays/", "guide_holidays.html", dept=json.loads((ROOT / "data/dept_chuseok_2026.json").read_text()), by_brand=by_brand, holiday_counts=holiday_counts, closed_day=closed_day, open_day=open_day,
          area_counts=dict(sorted(area_counts.items(), key=lambda kv: -kv[1]["total"])))

    for b, lst in by_brand.items():
        # brand calendar: dates where ≥1 store closes, with counts
        counts = defaultdict(int)
        for s in lst:
            for c in s["closures"]:
                counts[c] += 1
        rules = defaultdict(int)
        for s in lst:
            key = "둘째·넷째 일요일" if any(dt.date.fromisoformat(c).weekday() == 6 for c in s["closures"]) else ("평일" if s["closures"] else ("임시휴업·영업종료" if s.get("state", "open") != "open" else "미확인"))
            rules[key] += 1
        areas = defaultdict(list)
        for s in lst:
            areas[s["area"] or "기타"].append(s)
        write(f"{b}/", "brand.html", brand=b, info=brands[b], stores=lst, counts=dict(counts), rules=dict(rules), areas=areas,
              chuseok_closed=holiday_counts[b][chuseok], chuseok_known=sum(1 for s in lst if s["closures"]),
              n_inactive=sum(1 for s in lst if s.get("state", "open") != "open"))
        for s in lst:
            near = sorted([x for x in lst if x is not s and x["area"] == s["area"] and x.get("state", "open") == "open"], key=lambda x: x["name"])[:8]
            write(f"{b}/{s['slug']}/", "store.html", s=s, info=brands[b], near=near)
            if s["closures"] and s.get("state", "open") == "open":
                (DIST / b / s["slug"] / "holidays.ics").write_text(ics(s, origin, base, b))
    for a, lst in by_area.items():
        write(f"region/{a}/", "region.html", area=a, stores=sorted(lst, key=lambda x: (x["brand"], x["name"])))

    # 백화점·아울렛·몰: 체인별 페이지만 만든다(점포별 페이지 없음 — 검색 수요가 "롯데백화점 휴무일" 같은 체인명 쿼리다).
    dept_raw = json.loads((ROOT / "data/dept.json").read_text())
    dept_chains = []
    for key, c in dept_raw["chains"].items():
        t = today.isoformat()
        covered = sorted({m for s in c["stores"] for m in s.get("months", {})})
        counts = defaultdict(int)
        types = defaultdict(list)
        for s in c["stores"]:
            if key == "ikea":  # 이케아 정기 휴점 = 설날·추석 당일뿐(공식 고객센터 안내). 매장 페이지에 날짜를 안 올린 매장도 같다.
                s["policy"] = [d for d in IKEA_CLOSED if d not in s["closed"]]
                s["closed"] = sorted(s["closed"] + s["policy"])
            for d in s["closed"]:
                counts[d] += 1
            upcoming = [d for d in s["closed"] if d >= t]
            notes = [f"{kdate(x['date'])} {x['hours']} 영업" for x in s.get("special", []) if x["kind"] != "extend" and x["date"] >= t and x.get("hours")]
            if [d for d in s.get("policy", []) if d >= t]:
                notes.append("공지에 없는 날은 이케아 공통 규정(설날·추석 당일 휴무) 기준")
            ms = sorted(m for m in s.get("months", {}) if m >= t[:7])
            empty = "·".join(f"{int(m[5:])}월" for m in ms) + " 휴무 없음" if ms else "공지된 날짜 없음"
            types[s.get("type") or c["name"]].append({**s, "upcoming": upcoming, "notes": notes, "empty": empty})
        future = sorted(d for d in counts if d >= t)
        nxt = future[0] if future else None
        dept_chains.append({"key": key, "name": c["name"], "short": c["name"].split("·")[0], "source": c["source"], "note": c.get("note"),
                            "n": len(c["stores"]), "fetched": c.get("fetched_at", dept_raw["fetched_at"])[:10], "covered": covered, "counts": dict(counts), "types": dict(types),
                            "next": nxt, "next_n": counts.get(nxt, 0) if nxt else 0})
    fetched = min(c["fetched"] for c in dept_chains)
    for c in dept_chains:
        write(f"dept/{c['key']}/", "dept.html", c=c, fetched=c["fetched"], chains=dept_chains)
    write("dept/", "dept_hub.html", chains=dept_chains, fetched=fetched)

    # 주소가 "서울시"/"부산시"로 적힌 점포 때문에 한동안 별도 허브가 만들어졌다. 정규화로 합쳤으므로
    # 옛 URL 은 사이트맵에서 빼고 메타 리프레시만 남긴다(GitHub Pages 는 301 을 못 준다).
    tpl = env.get_template("redirect.html")
    for old, new in (("서울시", "서울"), ("부산시", "부산")):
        out = DIST / "region" / old
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(tpl.render(target=f"{base}region/{new}/",
                                                   canonical=f"{origin}{base}region/{new}/", name=new))

    # lastmod: 점포 페이지는 그 점포 데이터가 바뀐 날, 브랜드·지역 허브는 소속 점포 중 가장 최근 날.
    # 나머지(홈·가이드·정책)는 정직하게 댈 날짜가 없으므로 lastmod 를 붙이지 않는다.
    cf = ROOT / "data/changed.json"
    lastmod = {}
    if cf.exists():
        ch = json.loads(cf.read_text())
        by_page = {}
        for s in stores:
            d = ch.get(f"{s['brand']}/{s['slug']}", {}).get("d")
            if not d:
                continue
            by_page[f"{s['brand']}/{s['slug']}/"] = d
            for hub in (f"{s['brand']}/", f"region/{s['area'] or '기타'}/"):
                by_page[hub] = max(by_page.get(hub, ""), d)
        lastmod = by_page
    write_sitemaps(urls, origin, base, lastmod)
    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {origin}{base}sitemap.xml\n")
    (DIST / "404.html").write_text(env.get_template("404.html").render(path="404"))
    (DIST / ".nojekyll").write_text("")
    for f in (ROOT / "static").glob("naver*.html"):  # Naver Search Advisor ownership file at site root
        shutil.copy(f, DIST / f.name)
    key = (ROOT / "static/indexnow-key.txt").read_text().strip()
    (DIST / f"{key}.txt").write_text(key + "\n")
    if args.adsense_pub:
        (DIST / "ads.txt").write_text(f"google.com, {args.adsense_pub}, DIRECT, f08c47fec0942fa0\n")
    if args.cname:
        (DIST / "CNAME").write_text(args.cname + "\n")
    print(f"built {len(urls)} pages -> {DIST}")


if __name__ == "__main__":
    main()
