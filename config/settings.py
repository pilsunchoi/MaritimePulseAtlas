from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "portwatch"          # 수집일(vintage)별 스냅샷: RAW/<YYYY-MM-DD>/<table>.parquet
PROCESSED = ROOT / "data" / "processed"
DB_PATH = PROCESSED / "portwatch.duckdb"
LOGS = ROOT / "logs"
DOCS_DATA = ROOT / "docs" / "data"

# IMF PortWatch는 ArcGIS Online 피처 서비스로 공개된다. 모든 층은 layer 0.
ARCGIS_BASE = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services"

# DuckDB 테이블 이름 -> PortWatch 서비스 이름
LAYERS = {
    "ports":             "PortWatch_ports_database",                 # 항만 2,065곳 메타
    "chokepoints":       "PortWatch_chokepoints_database",           # 해협·운하 28곳 메타
    "ports_daily":       "Daily_Ports_Data",                         # 항만 × 일, 입항·수입·수출(톤) × 선종
    "chokepoints_daily": "Daily_Chokepoints_Data",                   # 해협 × 일, 통과 척수·통과량(톤) × 선종
    "country_daily":     "Daily_Trade_Data_REG",                     # 국가·권역 × 일
    "trade_monthly":     "Monthly_TradeNow",                         # 권역 × 월, 무역 금액·물량 지수
    "disruptions":       "portwatch_disruptions_database",           # 재해·교란 사건(GDACS)
    "port_links":        "Spillover_Simulator_Maritime_Connections", # 항만 간 연결(OxMarTrans 모형, 정적)
}

PAGE_SIZE = 5000       # maxRecordCount 1000 × maxRecordCountFactor 5. 32,000(standard)보다 행당 빠르다
WORKERS = 6
KOR = "KOR"

# 사이트 기준선: 이 해들의 같은 주(ISO week) 값으로 '평년 범위'를 만든다
BASELINE_YEARS = [2019, 2021, 2022, 2023]   # 2020(코로나 급락)은 뺀다
