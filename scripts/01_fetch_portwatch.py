"""PortWatch ArcGIS 피처 서비스 -> 수집 시각(vintage)별 Parquet 스냅샷.

층마다 전체 행을 ObjectId 순으로 페이지 단위(5,000행) 병렬 수집해
data/raw/portwatch/<vintage>/<table>.parquet 로 저장한다. 파생 없음.
PortWatch는 방법론 개선 때 과거 값도 고치므로, 매 수집을 통째 스냅샷으로 남긴다.
manifest.json에 층별 행 수·서비스 최종 수정 시각·수집 시각을 남긴다.

vintage는 수집을 시작한 UTC 시각(YYYY-MM-DDTHHMMZ). 로컬(한국 시간)과 GitHub Actions(UTC)가
같은 이름 규칙을 쓰고, 같은 날 두 번 받아도 앞의 스냅샷을 덮어쓰지 않는다. 글자 순서가 곧 시간 순서다.

    python scripts/01_fetch_portwatch.py                  # 전 층, vintage=지금(UTC)
    python scripts/01_fetch_portwatch.py --only ports chokepoints
"""
import sys
import json
import time
import argparse
import datetime as dt
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.settings import ARCGIS_BASE, LAYERS, RAW, LOGS, PAGE_SIZE, WORKERS
import requests
import pandas as pd
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def log(msg):
    line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    LOGS.mkdir(exist_ok=True)
    with open(LOGS / "01_fetch_portwatch.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def session():
    s = requests.Session()
    retry = Retry(total=6, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods=["GET"])
    s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=WORKERS * 2))
    return s


def get_json(s, url, params):
    for attempt in range(5):
        r = s.get(url, params=params, timeout=120)
        r.raise_for_status()
        d = r.json()
        if "error" not in d:
            return d
        log(f"   ArcGIS 오류 {d['error']} (재시도 {attempt + 1})")
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"ArcGIS 오류 반복: {url} {params}")


def fetch_layer(s, service):
    url = f"{ARCGIS_BASE}/{service}/FeatureServer/0"
    meta = get_json(s, url, {"f": "json"})
    fields = {f["name"]: f["type"] for f in meta["fields"]}
    oid = meta.get("objectIdField", "ObjectId")
    last_edit = (meta.get("editingInfo") or {}).get("dataLastEditDate")
    # returnCountOnly는 큰 층(Daily_Ports_Data)에서 틀린 값(342,000)을 돌려주므로 통계 쿼리로 센다
    stats = json.dumps([{"statisticType": t, "onStatisticField": oid, "outStatisticFieldName": t}
                        for t in ("count", "min", "max")])
    a = get_json(s, f"{url}/query", {"where": "1=1", "outStatistics": stats, "f": "json"})["features"][0]["attributes"]
    n, lo, hi = a["count"], a["min"], a["max"]

    # resultOffset은 깊어질수록 서버가 느려져(200만 행 부근에서 오류) ObjectId 구간으로 나눈다.
    # 구간 폭이 PAGE_SIZE이므로 한 구간의 행 수는 PAGE_SIZE를 넘지 않는다.
    def page(start):
        d = get_json(s, f"{url}/query", {
            "where": f"{oid} >= {start} AND {oid} < {start + PAGE_SIZE}", "outFields": "*",
            "resultRecordCount": PAGE_SIZE, "maxRecordCountFactor": 5,
            "returnGeometry": "false", "f": "json"})
        if d.get("exceededTransferLimit"):
            raise RuntimeError(f"{service}: 구간 {start}에서 전송 한도 초과")
        return [f["attributes"] for f in d["features"]]

    starts = list(range(lo, hi + 1, PAGE_SIZE))
    with ThreadPoolExecutor(WORKERS) as ex:
        rows = [r for chunk in ex.map(page, starts) for r in chunk]

    df = pd.DataFrame(rows, columns=list(fields))
    if df[oid].duplicated().any() or len(df) != n:
        raise RuntimeError(f"{service}: 행 수 불일치 또는 중복 (count={n}, got={len(df)}, "
                           f"dup={int(df[oid].duplicated().sum())})")
    for c, t in fields.items():
        if t == "esriFieldTypeDate":        # epoch ms
            df[c] = pd.to_datetime(df[c], unit="ms", utc=True).dt.tz_localize(None)
        elif t == "esriFieldTypeDateOnly":  # 'YYYY-MM-DD'
            df[c] = pd.to_datetime(df[c]).dt.date
    return df.sort_values(oid).reset_index(drop=True), fields, last_edit


def main(only=None, vintage=None):
    vintage = vintage or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    out = RAW / vintage
    out.mkdir(parents=True, exist_ok=True)
    man_path = out / "manifest.json"
    manifest = json.loads(man_path.read_text(encoding="utf-8")) if man_path.exists() else {}
    s = session()
    for table, service in LAYERS.items():
        if only and table not in only:
            continue
        t0 = time.time()
        df, fields, last_edit = fetch_layer(s, service)
        p = out / f"{table}.parquet"
        df.to_parquet(p, index=False, compression="zstd")
        manifest[table] = {
            "service": service, "rows": len(df), "columns": list(fields),
            "data_last_edit": (dt.datetime.fromtimestamp(last_edit / 1000, dt.timezone.utc)
                               .strftime("%Y-%m-%dT%H:%M:%SZ") if last_edit else None),
            "fetched_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "bytes": p.stat().st_size,
        }
        log(f"{table:18s} {len(df):>10,}행  {p.stat().st_size / 1e6:7.1f} MB  {time.time() - t0:6.1f}s")
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"스냅샷 {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", choices=list(LAYERS))
    ap.add_argument("--vintage", help="스냅샷 폴더 이름 (기본: 지금 UTC, YYYY-MM-DDTHHMMZ)")
    a = ap.parse_args()
    main(a.only, a.vintage)
