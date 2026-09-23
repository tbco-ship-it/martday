(async function () {
  const cssHref = document.querySelector('link[href*="static/style.css"]').getAttribute('href');
  const v = (cssHref.match(/\?v=([^&]+)/) || [])[1] || '';
  const base = cssHref.replace(/static\/style\.css.*$/, '');
  const D = await (await fetch(base + 'static/stores.json?v=' + v)).json();
  const out = document.getElementById('result');
  const $ = id => document.getElementById(id);
  // 검색어 정규화: 공백 제거 + 실제 유입 표기(e마트·emart·홈플·롯마·코슷코) → 데이터 표기
  const norm = s => s.toLowerCase().replace(/\s+/g, '').replace(/^e마트|^emart|^e-mart/, '이마트').replace(/^홈플(?!러스)/, '홈플러스').replace(/^롯마/, '롯데마트').replace(/^costco/, '코스트코').replace(/^traders/, '트레이더스');
  const KDAY = '일월화수목금토';
  const now = new Date();
  const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const todayIso = iso(now);
  const kdate = s => { const d = new Date(s + 'T00:00:00'); return `${d.getMonth() + 1}/${d.getDate()}(${KDAY[d.getDay()]})`; };

  function status(s) {
    if (s.state && s.state !== 'open') return { closedToday: true, next: null, open: false, note: '', inactive: s.state };
    const closedToday = s.closures.includes(todayIso);
    const next = s.closures.find(c => c > todayIso);
    let open = null, note = '';
    if (s.hours) {
      const m = s.hours.match(/(\d{1,2}):(\d{2})~(\d{1,2}):(\d{2})/);
      if (m) {
        const mins = now.getHours() * 60 + now.getMinutes(), o = +m[1] * 60 + +m[2], c = +m[3] * 60 + +m[4];
        open = !closedToday && mins >= o && mins < c;
        note = closedToday ? '' : mins < o ? `${m[1]}:${m[2]}에 문을 엽니다` : mins >= c ? `오늘 영업은 ${m[3]}:${m[4]}에 끝났습니다` : `${m[3]}:${m[4]}까지 영업`;
      }
    }
    return { closedToday, next, open, note };
  }

  function card(s, extra = '') {
    const st = status(s), b = D.brands[s.brand];
    const cls = st.closedToday ? 'severe' : (st.open === false ? 'mild' : 'balanced');
    const head = st.inactive ? (st.inactive === 'closed' ? '영업종료' : '임시휴업') : st.closedToday ? '오늘 휴무' : st.open === true ? '영업 중' : st.open === false ? '영업 시간 아님' : '영업일';
    const line = st.inactive ? `${s.state_note}.` : st.closedToday ? `정기 휴무일입니다.${st.next ? ` 다음 휴무 ${kdate(st.next)}.` : ''}` : `${st.note ? st.note + '. ' : ''}${st.next ? `다음 휴무 ${kdate(st.next)}.` : '이번 달 고시된 휴무일이 없습니다.'}`;
    return `<section class="sheet ${cls}"><p class="sheet-label">${b.short}${extra}</p><div class="sheet-num"><span class="num small-num">${head}</span></div><p class="sheet-title">${s.name}</p><p class="sheet-text">${line}${s.hours ? ` 영업시간 ${s.hours}.` : ''}${s.holiday_note ? ' ' + s.holiday_note + '.' : ''}</p><p class="sheet-actions"><a class="next" href="${base}${s.brand}/${encodeURIComponent(s.slug)}/">점포 상세와 달력</a>${s.lat ? `<a class="next" href="https://map.naver.com/p/search/${encodeURIComponent(s.name)}" target="_blank" rel="noopener">네이버 지도</a>` : ''}</p></section>`;
  }

  // typeahead
  // Home search only exists on the home page; store pages load this file for the live status word below, so
  // everything that touches the search UI is guarded (an unguarded addEventListener on null used to throw here).
  const input = $('store'), menu = $('store-menu');
  if (input) {
  let items = [], active = -1;
  const label = s => s.name;
  function open(q) {
    const nq = norm(q).replace(/^이마트에브리데이/, '에브리데이');
    // "민락 노브랜드", "이마트에브리데이 목동"처럼 브랜드를 앞뒤 어디에 쳐도 찾는다
    const bm = nq.match(/노브랜드|에브리데이/), rest = bm ? nq.replace(bm[0], '') : '';
    const hit = s => { const n = norm(s.name); return bm ? n.includes(bm[0]) && n.includes(rest) : n.includes(nq); };
    items = (nq ? D.stores.filter(s => hit(s) || (s.address && norm(s.address).includes(nq))) : D.stores.filter(s => s.brand === 'emart')).slice(0, 8);
    menu.innerHTML = items.length ? items.map((s, i) => `<li role="option" data-i="${i}" ${i === active ? 'aria-selected="true"' : ''}>${s.name}<small class="muted"> ${s.area || ''}</small></li>`).join('') : '<li class="empty">해당 점포가 없어요. 동네 이름으로도 찾아보세요.</li>';
    menu.hidden = false; input.setAttribute('aria-expanded', 'true');
  }
  function close() { menu.hidden = true; active = -1; input.setAttribute('aria-expanded', 'false'); }
  // Home: the first result ends the landing state — hero + card glide up from centre (FLIP on transform); the lists below rise in.
  function leaveLanding() {
    const html = document.documentElement; if (!html.classList.contains('landing')) return;
    const stage = $('stage'), hero = stage.firstElementChild;
    const y0 = hero.getBoundingClientRect().top;
    html.classList.remove('landing');
    const dy = y0 - hero.getBoundingClientRect().top;
    if (dy > 0 && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
      // transform, not padding: the glide must not register as layout shift (CLS)
      stage.style.transition = 'none'; stage.style.transform = `translateY(${dy}px)`; void stage.offsetHeight;
      stage.style.transition = 'transform 1s cubic-bezier(.16,1,.3,1)'; stage.style.transform = 'translateY(0)';
      stage.addEventListener('transitionend', () => { stage.style.transition = ''; stage.style.transform = ''; }, { once: true });
    }
    if (window.__reveal) window.__reveal($('below'), true, 500);
  }
  // Result rises in Toss-style: each card, then its children, 90ms apart.
  function show(html) {
    leaveLanding(); out.innerHTML = html;
    out.classList.remove('is-in'); out.classList.add('reveal');
    let i = 0; out.querySelectorAll(':scope > *').forEach(c => { [c, ...c.children].forEach(el => { el.classList.add('rv'); el.style.setProperty('--d', (i++ * 90) + 'ms'); }); });
    void out.offsetHeight; out.classList.add('is-in');
  }
  // On a phone the result sits below the form (often behind the browser's bottom bar): bring it into view so a tap visibly did something.
  // Layout position (offsetTop chain), not the rendered box: right after the first result the stage is mid-glide (translateY) and
  // scrollIntoView would land ~100px too far down; scroll-margin-top keeps the target below the sticky header.
  const bringIntoView = el => { if (innerWidth >= 900) return; setTimeout(() => { let y = 0; for (let e = el; e; e = e.offsetParent) y += e.offsetTop; y -= parseFloat(getComputedStyle(el).scrollMarginTop) || 0; scrollTo({ top: y, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' }); }, 60); };
  function choose(s) { input.value = s.name; close(); show(card(s)); localStorage.setItem('martday.store', s.slug); bringIntoView(out); }
  input.addEventListener('focus', () => { setTimeout(() => input.select(), 0); open(input.value); });
  input.addEventListener('input', () => { active = -1; open(input.value); });
  input.addEventListener('keydown', e => {
    if (menu.hidden) return;
    if (e.key === 'ArrowDown') { active = Math.min(active + 1, items.length - 1); open(input.value); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { active = Math.max(active - 1, 0); open(input.value); e.preventDefault(); }
    else if (e.key === 'Enter') { const it = items[active >= 0 ? active : 0]; if (it) choose(it); e.preventDefault(); }
    else if (e.key === 'Escape') close();
  });
  menu.addEventListener('mousedown', e => { const li = e.target.closest('li[data-i]'); if (li) { choose(items[+li.dataset.i]); e.preventDefault(); } });
  input.addEventListener('blur', () => setTimeout(close, 120));

  // geolocation
  const geoBtn = $('geo'), geoIdle = geoBtn.textContent;
  const busy = on => { geoBtn.disabled = on; geoBtn.classList.toggle('busy', on); geoBtn.textContent = on ? '위치를 확인하는 중…' : geoIdle; };
  geoBtn.addEventListener('click', () => {
    const msg = $('geo-msg'); msg.hidden = true;
    if (!navigator.geolocation) { msg.hidden = false; msg.textContent = '이 브라우저는 위치를 지원하지 않아요. 점포 이름으로 찾아 주세요.'; return; }
    busy(true);
    navigator.geolocation.getCurrentPosition(pos => {
      busy(false); msg.hidden = false;
      const { latitude: la, longitude: lo } = pos.coords;
      const dist = s => { const dLat = (s.lat - la) * Math.PI / 180, dLng = (s.lng - lo) * Math.PI / 180; const a = Math.sin(dLat / 2) ** 2 + Math.cos(la * Math.PI / 180) * Math.cos(s.lat * Math.PI / 180) * Math.sin(dLng / 2) ** 2; return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)); };
      const near = D.stores.filter(s => s.lat).map(s => ({ s, d: dist(s) })).sort((a, b) => a.d - b.d).slice(0, 4);
      msg.textContent = `가까운 점포 ${near.length}곳`;
      show(near.map(({ s, d }) => card(s, ` · ${d < 1 ? Math.round(d * 1000) + ' m' : d.toFixed(1) + ' km'}`)).join(''));
      bringIntoView(msg);  // GPS list: the '가까운 점포 N곳' line first, cards right under it
    }, () => { busy(false); msg.hidden = false; msg.textContent = '위치 권한이 없어요. 점포 이름으로 찾아 주세요.'; }, { timeout: 8000 });
  });

  // First visit: only the centred search card, nothing pre-filled (the old 이마트 왕십리 sample is gone). A remembered store is offered as a one-tap chip.
  const remembered = D.stores.find(s => s.slug === localStorage.getItem('martday.store'));
  if (remembered) { $('last-name').textContent = remembered.name; $('last').hidden = false; $('last').addEventListener('click', () => choose(remembered)); }

  }

  // store page: live status word
  const sheet = document.querySelector('.sheet[data-store]');
  if (sheet) { const s = D.stores.find(x => x.slug === sheet.dataset.store); if (s) { const st = status(s); const el = document.getElementById('status'); if (el && st.open !== null && !st.closedToday) el.textContent = st.open ? '영업 중' : '영업 시간 아님'; } }
})();
