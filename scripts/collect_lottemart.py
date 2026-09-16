#!/usr/bin/env python3
"""Lotte Mart stores list, hours, closures and addresses.
Source: company.lottemart.com/shop/shop_search.asp (public web search)."""
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/stores/lottemart.json"

UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://company.lottemart.com/shop/shop_search.asp"
}


def fetch_html():
    req = urllib.request.Request(
        "https://company.lottemart.com/shop/shop_search.asp?page=1&list_num=500",
        headers=UA
    )
    res = urllib.request.urlopen(req, timeout=30)
    return res.read().decode("utf-8", "replace")


def main():
    h = fetch_html()
    tbodies = re.findall(r"<tbody>(.*?)</tbody>", h, re.S)
    if len(tbodies) < 2:
        print("Error: Could not find store table", file=sys.stderr)
        sys.exit(1)

    rows = re.findall(r"<tr>(.*?)</tr>", tbodies[1], re.S)
    out = []

    for i, r in enumerate(rows):
        alt_m = re.search(r"alt=[\"\x27]([^\x27\"]+)[\"\x27]", r)
        brand_type = alt_m.group(1).strip() if alt_m else "롯데마트"

        name_m = re.search(r"<td>\s*([^<]+?[점|역|스])\s*</td>", r)
        raw_name = html.unescape(name_m.group(1).strip()) if name_m else f"점포-{i+1}"

        if not any(raw_name.startswith(b) for b in ["롯데마트", "토이저러스", "보틀벙커", "MAXX", "맥스"]):
            name = f"롯데마트 {raw_name}"
        else:
            name = raw_name

        time_m = re.search(r'<span class="time">([^<]*)</span>', r)
        hours = html.unescape(time_m.group(1).strip()) if time_m else ""

        call_m = re.search(r'<span class="call">([^<]*)</span>', r)
        phone = html.unescape(call_m.group(1).strip()) if call_m else ""

        memo_m = re.search(r'<span class="memo">([^<]*)</span>', r)
        memo = html.unescape(memo_m.group(1).strip()) if memo_m else ""

        dayoff_m = re.search(r'<span class="day-off">([^<]*)</span>', r)
        dayoff = html.unescape(dayoff_m.group(1).strip()) if dayoff_m else ""

        addr_matches = re.findall(r'<div class="address">([^<]*)</div>', r)
        addrs = [html.unescape(a.strip()) for a in addr_matches if a.strip()]
        addr = addrs[0] if addrs else ""
        addr_lot = addrs[1] if len(addrs) > 1 else ""

        area = addr.split()[0] if addr else ""

        dates = re.findall(r"(\d{1,2})/(\d{1,2})", dayoff)
        closures = [f"{int(m)}/{int(d)}" for m, d in dates]

        holiday_notes = []
        if memo:
            holiday_notes.append(memo)
        for m, d in dates:
            if int(m) == 9 and 24 <= int(d) <= 27:
                if int(d) == 25:
                    holiday_notes.append("추석 당일(9/25) 휴무")
                else:
                    holiday_notes.append(f"추석 연휴(9/{d}) 휴무")

        store_id = f"lm-{i+1:03d}"

        rec = {
            "brand": "lottemart",
            "id": store_id,
            "name": name,
            "area": area,
            "address": addr,
            "address_lot": addr_lot,
            "lat": None,
            "lng": None,
            "phone": phone,
            "hours": hours,
            "closure_rule": dayoff,
            "closures": closures,
            "holiday_note": ", ".join(holiday_notes),
            "holiday_days": [int(d) for _, d in dates]
        }
        out.append(rec)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"fetched": time.strftime("%Y-%m-%d"), "stores": out}, ensure_ascii=False, indent=1))
    has_closures = sum(1 for r in out if r.get("closures"))
    has_coords = sum(1 for r in out if r.get("lat") is not None)
    print(f"lottemart stores: {len(out)}, with closures: {has_closures} ({has_closures/len(out):.1%}), with coords: {has_coords} ({has_coords/len(out):.1%})")


if __name__ == "__main__":
    main()
