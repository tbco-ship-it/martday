#!/usr/bin/env python3
"""백화점·아울렛·몰·이케아 monthly closures (휴점일) and special-hours days -> data/dept.json.
Sources (all public, no login): lotteshopping.com store pages (inline calendarInfo JSON),
shinsegae.com store pages (calendar HTML), ehyundai.com SetCalender.do (JSON),
dept.galleria.co.kr store-info pages, akplaza.com store/introduce pages, ikea.com/kr store pages (hydrate JSON).
A store that fails goes to "errors" and is left out; it is never written as "no closures".
A chain that yields no stores keeps its previous entry from data/dept.json."""
import html, json, re, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/dept.json"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
KST = timezone(timedelta(hours=9))
PACE = 0.6  # seconds between requests to the same host
_last_hit = {}

LOTTE_URL = "https://www.lotteshopping.com/store/main?cstrCd={}"
SSG_URL = "https://www.shinsegae.com/store/main.do?storeCd={}"
SSG_CODES = [f"SC{n:05d}" for n in range(1, 14)] + ["SC00060"]
HD_CAL_URL = "https://www.ehyundai.com/newPortal/uplex/DP/SetCalender.do"
HD_STORE_URL = "https://www.ehyundai.com/newPortal/DP/DP000000_V.do?branchCd=B00121000"
GALLERIA_URL = "https://dept.galleria.co.kr/store-info/{}"
GALLERIA_SLUGS = ["luxuryhall", "timeworld", "gwanggyo", "centercity", "jinju"]
AK_URL = "https://www.akplaza.com/store/introduce?store={}"
AK_CODES = ["02", "03", "04", "05", "51", "52", "11", "12", "53"]
IKEA_URL = "https://www.ikea.com/kr/ko/stores/{}/"
IKEA_SLUGS = ["gwangmyeong", "goyang", "giheung", "dong-busan", "gangdong"]
IKEA_NOTE = "설날·추석 당일 휴무 (체인 공통 규정). 매장 페이지에 날짜가 없는 매장도 이 두 날은 쉰다."


def fetch(url, data=None, headers=None):
    """Return (final_url, text). Waits PACE seconds per host; one retry on network errors (not on HTTP 4xx)."""
    host = urllib.parse.urlsplit(url).netloc
    for attempt in (1, 2):
        wait = PACE - (time.monotonic() - _last_hit.get(host, 0))
        if wait > 0: time.sleep(wait)
        _last_hit[host] = time.monotonic()
        req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.geturl(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == 2: raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2: raise
        time.sleep(2)


def get(url):
    return fetch(url)[1]


def month_keys(today):
    """['YYYY-MM' of this month, 'YYYY-MM' of next month]."""
    nxt = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
    return [today.strftime("%Y-%m"), nxt.strftime("%Y-%m")]


def year_for(month, today):
    """Year of a month shown on a 'this month / next month' page (handles Dec -> Jan)."""
    if month < today.month - 6: return today.year + 1
    if month > today.month + 6: return today.year - 1
    return today.year


def iso(y, m, d):
    return date(int(y), int(m), int(d)).isoformat()


def hours(t):
    return re.sub(r"\s*~\s*", "~", t.strip())


def text(h):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()


def store(id_, name, type_, url, closed, special, months):
    return {"id": id_, "name": name, "type": type_, "url": url, "closed": sorted(set(closed)),
            "special": sorted(special, key=lambda s: (s["date"], s["kind"])), "months": months}


# ---------- 롯데 ----------
LOTTE_KINDS = (("holiday", "holiday"), ("shorten_1", "shorten"), ("shorten_2", "shorten"), ("extend_0", "extend"),
               ("extend_1", "extend"), ("extend_2", "extend"), ("manualInput", "manual"), ("closure", "closure"))


def parse_lotte_stores(h):
    """Ordered [(cstrCd, name, type)] from the changeCstrInfo({...}) calls in any store page."""
    out = {}
    for m in re.finditer(r"changeCstrInfo\((\{.*?\})\)", h):
        j = json.loads(m.group(1))
        out.setdefault(j["cstrCd"], (j["cstrCd"], j["cstrDspNm"], j["mstrlrclsNm"]))
    if not out: raise ValueError("changeCstrInfo store list not found")
    return list(out.values())


def lotte_date(s):
    return iso(*s.split("."))


def parse_lotte_page(h, today, expect_name=None):
    """{'closed','special','months'} from `const calendarInfo = {...};`. Keys: closed=휴점, holiday=명절당일,
    shorten_*=단축, extend_*=연장, manualInput=기타 (+_txt), closure=영업종료 (no time)."""
    if expect_name:
        m = re.search(r"encodeURIComponent\('[^']*' \+ ' ' \+ '([^']*)'\)", h)
        if not m or m.group(1).removesuffix("점") != expect_name.removesuffix("점"):  # 타임빌라스 page says '수원' for '수원점'
            raise ValueError(f"page is for {m.group(1) if m else '?'}, expected {expect_name}")
    m = re.search(r"const calendarInfo = (\{.*?\});\s*\n\s*const today", h, re.S)
    if not m: raise ValueError("calendarInfo not found")
    cal = json.loads(m.group(1))
    closed, special, months = [], [], {}
    for mk in month_keys(today):
        d = cal.get(f"{int(mk[:4])}.{int(mk[5:])}")
        if not d or not any(d.values()):  # month missing or all lists empty (some outlets have no running_time, only extend_*)
            months[mk] = "unpublished"
            continue
        months[mk] = "ok"
        closed += [lotte_date(x) for x in d.get("closed", [])]
        for src, kind in LOTTE_KINDS:
            dates, times, txts = d.get(src, []), d.get(src + "_time", []), d.get(src + "_txt", [])
            if kind != "closure" and len(times) != len(dates):
                raise ValueError(f"{mk} {src}: {len(dates)} dates but {len(times)} times")
            for i, x in enumerate(dates):
                s = {"date": lotte_date(x), "kind": kind}
                if kind != "closure": s["hours"] = hours(times[i])
                if i < len(txts) and txts[i]: s["note"] = txts[i].strip()
                special.append(s)
    return {"closed": closed, "special": special, "months": months}


def collect_lotte(today, errs):
    first = get(LOTTE_URL.format("0001"))
    out = []
    for code, name, type_ in parse_lotte_stores(first):
        url = LOTTE_URL.format(code)
        try:
            p = parse_lotte_page(first if code == "0001" else get(url), today, name)
            out.append(store(code, name, type_, url, p["closed"], p["special"], p["months"]))
        except Exception as e:
            errs.append({"store": f"{code} {name}", "error": str(e)[:200]})
    return out


# ---------- 신세계 ----------
def parse_ssg_page(h, today):
    """None if the code has no store (empty-name template). Else {'name','closed','months'}.
    Calendar cells: <span class="sr-only">{label}</span><span>{day}</span>; closed iff label starts with 휴점일."""
    t = re.search(r"<title>\s*신세계백화점(.*?)한눈에 보기", h, re.S)
    name = t.group(1).strip() if t else ""
    if not name: return None
    heads = dict(re.findall(r'<div class="cal([12])"[^>]*>\s*<span class="num">(\d+)</span>', h))
    mnums = [int(heads[k]) for k in ("1", "2") if k in heads]
    start = h.find('<div class="day cal1"')
    if start < 0 or not mnums: raise ValueError("calendar not found")
    region = h[start:h.find("</li>", start)]
    cells = re.findall(r'<div[^>]*>\s*(?:<span class="sr-only">([^<]*)</span>)?\s*<span>(\d+)</span>\s*</div>', region)
    if not cells: raise ValueError("no calendar cells")
    idx, prev, closed, labelled = 0, 0, [], set()
    for label, day in cells:
        day = int(day)
        if day <= prev: idx += 1  # day number dropped -> next month
        prev = day
        if idx >= len(mnums): raise ValueError(f"more month blocks than month headers {mnums}")
        label = html.unescape(label).strip()
        if label and label != "오늘": labelled.add(idx)
        if label.startswith("휴점일"):
            mon = mnums[idx]
            closed.append(iso(year_for(mon, today), mon, day))
    months = {}
    for i, mon in enumerate(mnums[:idx + 1]):
        # next month with no marks at all (not even 연장영업) is treated as not yet published
        months[f"{year_for(mon, today)}-{mon:02d}"] = "ok" if i == 0 or i in labelled else "unpublished"
    return {"name": name, "closed": closed, "months": months}


def collect_shinsegae(today, errs):
    out = []
    for code in SSG_CODES:
        url = SSG_URL.format(code)
        try:
            final, h = fetch(url)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print("shinsegae skip", code, "404", file=sys.stderr); continue
            errs.append({"store": code, "error": str(e)[:200]}); continue
        except Exception as e:
            errs.append({"store": code, "error": str(e)[:200]}); continue
        if final != url:
            print("shinsegae skip", code, "redirect", final, file=sys.stderr); continue
        try:
            p = parse_ssg_page(h, today)
        except Exception as e:
            errs.append({"store": code, "error": str(e)[:200]}); continue
        if p is None:
            print("shinsegae skip", code, "empty store page", file=sys.stderr); continue
        out.append(store(code, p["name"], "백화점", url, p["closed"], [], p["months"]))
    return out


# ---------- 현대 ----------
def parse_hyundai_branches(h):
    """Ordered [(branchCd, name, group, url)] from the store page's branch_list blocks."""
    out = []
    for grp, body in re.findall(r'<h2 class="branch_tit">([^<]+)</h2>\s*<ul class="branch_list">(.*?)</ul>', h, re.S):
        for href, code, name in re.findall(r'<a href="([^"]*branchCd=(B\d+))"><span>([^<]+)</span>', body):
            out.append((code, name.strip(), grp.strip(), urllib.parse.urljoin("https://www.ehyundai.com/", href)))
    if not out: raise ValueError("branch_list not found")
    return out


def parse_hyundai_month(j, code, ym):
    """(status, closed, special, problems) for one SetCalender.do response. extendBreakTy 2=휴점, 1/3=연장, 9=당월 무휴.
    An empty holyDay list means the month is not published yet."""
    rows = [r for r in j["holyDay"] if r.get("branchCd") == code and r.get("yearmonth") == ym and r.get("delYn", "N") == "N"]
    if not rows: return "unpublished", [], [], []
    closed, special, problems = [], [], []
    for r in rows:
        d, ty = r["theDay"], str(r["extendBreakTy"])
        day = iso(d[:4], d[4:6], d[6:])
        if ty == "2": closed.append(day)
        elif ty in ("1", "3"): special.append({"date": day, "kind": "extend", "extend_minutes": int(r.get("extendTerem") or 0)})
        elif ty == "9": pass
        else: problems.append(f"unknown extendBreakTy {ty} on {day}")
    return "ok", closed, special, problems


def collect_hyundai(today, errs):
    out = []
    for code, name, grp, url in parse_hyundai_branches(get(HD_STORE_URL)):
        closed, special, months, bad = [], [], {}, None
        for mk in month_keys(today):
            y, m = mk.split("-")
            try:
                body = urllib.parse.urlencode({"year": y, "month": str(int(m)), "branchCd": code}).encode()
                j = json.loads(fetch(HD_CAL_URL, body, {"X-Requested-With": "XMLHttpRequest"})[1])
                status, c, s, problems = parse_hyundai_month(j, code, y + m)
            except Exception as e:
                bad = f"{mk}: {e}"[:200]; break
            months[mk] = status
            closed += c; special += s
            errs += [{"store": f"{code} {name}", "error": p} for p in problems]
        if bad:
            errs.append({"store": f"{code} {name}", "error": bad}); continue
        out.append(store(code, name, grp, url, closed, special, months))
    return out


# ---------- 갤러리아 ----------
def parse_galleria_page(h, slug, today):
    """{'name','closed','months'} from this store's block: <dd class="dd dd--holiday"><b class="num">MM.DD</b>. Current month only."""
    for seg in h.split('class="btn-open"')[1:]:
        if f"/store-info/{slug}/" not in seg: continue
        name = re.search(r'<b class="t">([^<]+)</b>', seg)
        dd = re.search(r'<dd class="dd dd--holiday">(.*?)</dd>', seg, re.S)
        if not name or not dd: raise ValueError("휴점일 block not found")
        closed = [iso(year_for(int(m), today), m, d) for m, d in re.findall(r'<b class="num">\s*(\d{1,2})\.(\d{1,2})\s*</b>', dd.group(1))]
        if not closed and text(dd.group(1)):
            raise ValueError(f"unparsed 휴점일 text: {text(dd.group(1))[:60]}")
        months = {c[:7]: "ok" for c in closed} or {today.strftime("%Y-%m"): "ok"}
        return {"name": name.group(1).strip(), "closed": closed, "months": months}
    raise ValueError(f"store block for {slug} not found")


def collect_galleria(today, errs):
    out = []
    for slug in GALLERIA_SLUGS:
        url = GALLERIA_URL.format(slug)
        try:
            p = parse_galleria_page(get(url), slug, today)
            out.append(store(slug, p["name"], "백화점", url, p["closed"], [], p["months"]))
        except Exception as e:
            errs.append({"store": slug, "error": str(e)[:200]})
    return out


# ---------- AK ----------
def parse_ak_nav(h):
    """{code: (name, type)} from the 지점안내 menu (백화점 / 쇼핑몰)."""
    out = {}
    for type_, body in re.findall(r"<strong>(백화점|쇼핑몰)</strong>\s*<ul>(.*?)</ul>", h, re.S):
        for code, name in re.findall(r'/store/introduce\?store=(\d+)">([^<]+)</a>', body):
            out.setdefault(code, (name.strip(), type_))
    return out


def parse_ak_page(h, today):
    """{'closed','months'}: <p class="offDay">이달의 휴점일 <span>25일</span> ('무휴' = none), cross-checked
    against calendar <td title="OFF">…<i>DD</i>. Current month only."""
    off = re.search(r'<p class="offDay">이달의 휴점일(.*?)</p>', h, re.S)
    mon = re.search(r'<div class="titArea">\s*<em>(\d{1,2})</em>', h)
    if not off or not mon: raise ValueError("offDay or calendar month not found")
    t = text(off.group(1))
    if "무휴" in t: days = set()
    else:
        days = {int(d) for d in re.findall(r"(\d{1,2})\s*일", t)}
        if not days: raise ValueError(f"unparsed offDay text: {t[:60]}")
    cal = {int(d) for d in re.findall(r'<td title="OFF">(?:(?!</td>).)*?<i>(\d{1,2})</i>', h, re.S)}
    if cal != days: raise ValueError(f"offDay {sorted(days)} != calendar OFF {sorted(cal)}")
    m = int(mon.group(1)); y = year_for(m, today)
    return {"closed": [iso(y, m, d) for d in days], "months": {f"{y}-{m:02d}": "ok"}}


def collect_ak(today, errs):
    out, nav = [], None
    for code in AK_CODES:
        url = AK_URL.format(code)
        try:
            h = get(url)
            nav = nav or parse_ak_nav(h)
            if code not in nav: raise ValueError("store not in site menu")
            p = parse_ak_page(h, today)
            out.append(store(code, nav[code][0], nav[code][1], url, p["closed"], [], p["months"]))
        except Exception as e:
            errs.append({"store": code, "error": str(e)[:200]})
    return out


# ---------- 이케아 ----------
def ikea_date(s):
    m = re.match(r"\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?\s*$", s)
    if not m: raise ValueError(f"bad date {s!r}")
    return iso(*m.groups())


def parse_ikea_page(h):
    """{'name','closed','special'} from the hydrate JSON data.storeConfig.hours.{closed,exceptions}."""
    for b in re.findall(r'<script type="text/hydrate"[^>]*>(.*?)</script>', h, re.S):
        if '"storeConfig"' not in b: continue
        cfg = json.loads(b)["data"]["storeConfig"]
        hrs = cfg["hours"]
        closed = [ikea_date(c["date"]) for c in hrs["closed"]]
        special = [{"date": ikea_date(x["date"]), "kind": "exception", "hours": f"{x['open']}~{x['close']}",
                    **({"note": x["reason"].strip()} if x.get("reason") else {})} for x in hrs["exceptions"]]
        return {"name": cfg["displayName"].strip(), "closed": closed, "special": special}
    raise ValueError("storeConfig hydrate JSON not found")


def collect_ikea(today, errs):
    out = []
    for slug in IKEA_SLUGS:
        url = IKEA_URL.format(slug)
        try:
            p = parse_ikea_page(get(url))
            out.append(store(slug, p["name"], "이케아", url, p["closed"], p["special"], {}))
        except Exception as e:
            errs.append({"store": slug, "error": str(e)[:200]})
    return out


CHAINS = (
    ("lotte", "롯데백화점·아울렛·몰", "https://www.lotteshopping.com/store/main", collect_lotte),
    ("shinsegae", "신세계백화점", "https://www.shinsegae.com/store/main.do", collect_shinsegae),
    ("hyundai", "현대백화점·더현대·커넥트현대·아울렛", HD_CAL_URL, collect_hyundai),
    ("galleria", "갤러리아백화점", "https://dept.galleria.co.kr/store-info/", collect_galleria),
    ("ak", "AK플라자·AK&", "https://www.akplaza.com/store/introduce", collect_ak),
    ("ikea", "이케아", "https://www.ikea.com/kr/ko/stores/", collect_ikea),
)


def main():
    now = datetime.now(KST)
    today = now.date()
    prev = json.loads(OUT.read_text()) if OUT.exists() else {}
    res = {"fetched_at": now.isoformat(timespec="seconds"), "chains": {}, "errors": []}
    # --only a,b: collect just these chains and carry the rest over unchanged. The GitHub runner gets lotte·shinsegae·hyundai;
    # galleria·ak·ikea time out from there and are collected weekly from the Mac (scripts/ori_ops/lottemart_weekly.sh).
    only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else None
    for key, name, source, fn in CHAINS:
        if only and key not in only:
            if key in prev.get("chains", {}):
                res["chains"][key] = {"fetched_at": prev.get("fetched_at"), **prev["chains"][key]}
            continue
        errs = []
        try:
            stores = fn(today, errs)
        except Exception as e:
            stores = []
            errs.append({"store": None, "error": f"chain failed: {str(e)[:200]}"})
        res["errors"] += [{"chain": key, **e} for e in errs]
        if not stores:
            old = prev.get("chains", {}).get(key)
            if old:
                old = {"fetched_at": prev.get("fetched_at"), **old, "stale": True, "stale_fetched_at": old.get("stale_fetched_at", prev.get("fetched_at"))}
                res["chains"][key] = old
                res["errors"].append({"chain": key, "store": None, "error": f"no stores collected; kept data from {old['stale_fetched_at']}"})
            else:
                res["errors"].append({"chain": key, "store": None, "error": "no stores collected and no previous data"})
            continue
        months = sorted({m for s in stores for m, v in s["months"].items() if v == "ok"})
        res["chains"][key] = {"name": name, "source": source, "fetched_at": res["fetched_at"], "months_covered": months, "stores": stores}
        if key == "ikea": res["chains"][key]["note"] = IKEA_NOTE
        print(f"{key:10} stores {len(stores):3}  with closure {sum(1 for s in stores if s['closed']):3}  errors {len(errs)}", file=sys.stderr)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print("chains", len(res["chains"]), "stores", sum(len(c["stores"]) for c in res["chains"].values()), "errors", len(res["errors"]))


if __name__ == "__main__":
    main()
