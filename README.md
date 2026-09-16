# 마트휴무일

Static site: 전국 대형마트·창고형·기업형 슈퍼 점포별 휴무일·영업시간. Sources: store.emart.com (이마트 계열), costco.co.kr REST.

```
.venv/bin/python scripts/collect_emart.py && .venv/bin/python scripts/collect_costco.py && .venv/bin/python scripts/normalize.py
.venv/bin/python scripts/build.py --base / --origin https://<domain>
```
Daily refresh runs in GitHub Actions (data commits back to main). 홈플러스·롯데마트 collectors: TODO.
