# Maritime Pulse Atlas — 해협·운하와 한국 항만의 일별 해상 물동량 (2019–)

선박자동식별장치(AIS) 신호로 추정한 일별 해상 물동량을 해협·운하 28곳과 한국 항만(일별 자료가 있는 10곳과 국가 합계)에 대해 평년 범위와 견주어 본다. 자료는 IMF와 옥스퍼드대의 [IMF PortWatch](https://portwatch.imf.org/)이고, 매주 화요일 갱신된다. 짝 사이트 [Trade Network Atlas](https://pilsunchoi.github.io/TradeNetworkAtlas/)가 BACI로 연 단위 교역 네트워크를 본다면, 이 저장소는 같은 교역을 바다 위에서 일 단위로 본다.

## 무엇이 들어 있나

| 경로 | 내용 |
|---|---|
| `docs/index.html` | 대시보드(GitHub Pages). 해협·운하, 한국 항만, 호르무즈 × 한국 스토리, 정보 탭. 오른쪽 패널 위의 지구본이 고른 해협·항만으로 돌아가 위치를 보여 준다 |
| `docs/data/*.js` | 대시보드 자료. `meta.js`, `chokepoints.js`(28곳 주별), `korea.js`(한국 항만 주별·국가 일별), `cp/<id>.js`·`port/<id>.js`(한 곳의 일별, 고를 때 읽는다), `land110.js`·`land50.js`(지구본 육지 윤곽. 50m은 한국 항만 탭을 열 때 읽는다) |
| `scripts/` | PortWatch 수집부터 DuckDB 적재, 검증, 대시보드 자료까지 |
| `config/settings.py` | 경로, PortWatch 층 목록, 기준연도 |
| `.github/workflows/weekly.yml` | 매주 화요일 PortWatch 갱신 뒤 자료를 다시 만들어 커밋 |

## 자료

PortWatch는 ArcGIS 피처 서비스로 공개된다. 여덟 층을 받는다.

| DuckDB 테이블 | PortWatch 층 | 행 (2026-09-16) | 내용 |
|---|---|---:|---|
| `ports` | PortWatch_ports_database | 2,065 | 항만 메타(위경도, LOCODE, 전국 해상 수출입 중 비중, 주요 산업) |
| `chokepoints` | PortWatch_chokepoints_database | 28 | 해협·운하 메타 |
| `ports_daily` | Daily_Ports_Data | 3,722,000 | 항만 × 일. 입항 척수, 수입·수출(톤) × 선종 5개. 메타 2,065곳 중 1,325곳만 있다(한국 22곳 중 10곳). 입항 0인 날도 행이 있다 |
| `chokepoints_daily` | Daily_Chokepoints_Data | 78,764 | 해협 × 일. 통과 척수, 통과량(톤) × 선종 |
| `country_daily` | Daily_Trade_Data_REG | 약 55만 | 국가·권역 × 일 |
| `trade_monthly` | Monthly_TradeNow | 18,032 | 권역 × 월. 무역 금액·물량 지수 |
| `disruptions` | portwatch_disruptions_database | 132 | 재해·교란 사건(GDACS 태풍·지진 등과 파나마·홍해·호르무즈) |
| `port_links` | Spillover_Simulator_Maritime_Connections | 155,521 | 항만 간 연결(OxMarTrans 모형, 시간 불변) |

- 선종: 컨테이너, 건화물(벌크), 일반화물, 로로선, 탱커.
- `country_daily`는 일별 항만 층에 없는 항만까지 합한 값이라 항만 합계보다 크다(최근 1년 수입 기준 한국 0.96, 일본 0.96, 중국 0.87, 호주 1.00). 대시보드의 “한국 전체”는 국가 층이다.
- PortWatch 층의 `returnCountOnly`는 `Daily_Ports_Data`에서 틀린 값(342,000)을 돌려주므로, 수집 스크립트는 통계 쿼리로 행 수를 세고 ObjectId 구간으로 나눠 받는다.
- 수입·수출과 통과량은 선박의 재화중량톤수(DWT)와 흘수 변화로 추정한 적재량(메트릭톤)이다. 환적 화물이 섞이고, AIS를 끈 선박은 빠진다.
- **사후 수정**: PortWatch는 방법론을 고치면 과거 값도 바꾼다. 그래서 수집할 때마다 전 층을 `data/raw/portwatch/<수집일>/`에 Parquet으로 통째 남기고, DuckDB의 `<table>_vintages` 뷰로 스냅샷끼리 비교할 수 있게 했다.

## 다시 만들기

```
conda activate kcsdb                          # Python 3.12+, duckdb, pandas, pyarrow, requests
python scripts/01_fetch_portwatch.py          # 전 층 -> data/raw/portwatch/<오늘>/*.parquet (약 5분)
python scripts/02_build_db.py                 # 최신 스냅샷 -> data/processed/portwatch.duckdb
python scripts/05_validate.py                 # 행 수·키 중복·기간·해협 완전성·한국 합계 대조
python scripts/10_export_site_data.py         # docs/data/*.js
python scripts/11_fetch_land.py               # 지구본 육지 윤곽 docs/data/land110.js·land50.js (한 번만)
```

대시보드를 로컬에서 보려면:

```
python -m http.server 8766 --directory docs
```

## 평년 범위

기준연도(2019·2021·2022·2023) 같은 날짜의 이동평균 최솟값~최댓값을 회색 띠로, 그 평균을 점선으로 그린다. 2020년은 코로나19 급락으로 뺐다. “평년 대비”는 이 평균에 대한 비율이다. 기준연도는 `config/settings.py`의 `BASELINE_YEARS`.

## 출처와 이용 조건

- **자료**: IMF PortWatch (portwatch.imf.org). AIS 원자료는 UN Global Platform. 방법론 Arslanalp, Koepke, Verschuur (2021) IMF WP/21/225, Arslanalp 외 (2025) IMF WP/25/93. 이용은 [IMF 이용 조건](https://www.imf.org/external/terms.htm)을 따른다.
- **지도**: Natural Earth(퍼블릭 도메인)를 TopoJSON으로 묶은 world-atlas 2.0.2(110m·50m 육지). 브라우저에서 topojson-client 3.1.0(jsDelivr)으로 풀어 D3 정사영으로 그린다.
- 코드와 문서는 MIT 라이선스. `docs/data/`는 PortWatch의 파생물이므로 PortWatch의 조건을 따른다.
