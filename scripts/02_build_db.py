"""Parquet 스냅샷 -> DuckDB.

가장 최근 스냅샷(또는 --vintage)을 층 이름 그대로의 테이블로 적재한다(원본 열 그대로).
- snapshots: 스냅샷별·층별 행 수, 서비스 최종 수정 시각, 수집 시각
- <table>_vintages: 모든 스냅샷을 vintage 열과 함께 읽는 뷰 (시계열 층만). 사후 수정 추적용
- v_ports_daily: ports_daily + 항만 메타(대륙·위경도·LOCODE)

기존 파일 안에서 테이블을 바꾸면 옛 테이블 자리가 빈 채로 남아 파일이 계속 커진다.
그래서 매번 임시 파일에 새로 만든 뒤 기존 DB와 바꿔 끼운다. 만드는 도중 실패하면 기존 DB는 그대로다.
모든 내용은 data/raw의 스냅샷에서 다시 만들어지므로 DB 파일에만 있는 자료는 없다.

    python scripts/02_build_db.py
    python scripts/02_build_db.py --vintage 2026-09-16
"""
import os
import sys
import json
import argparse
import datetime as dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.settings import RAW, DB_PATH, PROCESSED, LAYERS, LOGS
import duckdb

SERIES = ["ports_daily", "chokepoints_daily", "country_daily", "trade_monthly"]


def log(msg):
    line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    LOGS.mkdir(exist_ok=True)
    with open(LOGS / "02_build_db.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def vintages():
    return sorted(p.name for p in RAW.iterdir() if (p / "manifest.json").exists())


def main(vintage=None):
    vs = vintages()
    assert vs, f"스냅샷 없음: {RAW}"
    vintage = vintage or vs[-1]
    snap = RAW / vintage
    manifest = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    missing = [t for t in LAYERS if t not in manifest]
    assert not missing, f"{vintage}에 없는 층: {missing}"

    PROCESSED.mkdir(parents=True, exist_ok=True)
    tmp = DB_PATH.with_name(DB_PATH.stem + ".building.duckdb")
    for f in (tmp, Path(str(tmp) + ".wal")):   # 지난번에 실패하고 남은 임시 파일
        f.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    for t in LAYERS:
        p = (snap / f"{t}.parquet").as_posix()
        con.execute(f"CREATE TABLE {t} AS SELECT * FROM read_parquet('{p}')")
        n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        assert n == manifest[t]["rows"], f"{t}: 적재 {n} != manifest {manifest[t]['rows']}"
        log(f"{t:18s} {n:>10,}행  (vintage {vintage})")

    con.execute("""CREATE TABLE snapshots(
        vintage DATE, tbl VARCHAR, service VARCHAR, rows BIGINT,
        data_last_edit TIMESTAMP, fetched_at TIMESTAMP, loaded BOOLEAN,
        PRIMARY KEY (vintage, tbl))""")
    for v in vs:
        for t, m in json.loads((RAW / v / "manifest.json").read_text(encoding="utf-8")).items():
            con.execute("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?)",
                        [v, t, m["service"], m["rows"], m["data_last_edit"], m["fetched_at"], v == vintage])

    glob = RAW.as_posix()
    for t in SERIES:
        con.execute(f"""CREATE OR REPLACE VIEW {t}_vintages AS
            SELECT CAST(regexp_extract(filename, '(\\d{{4}}-\\d{{2}}-\\d{{2}})/[^/]+$', 1) AS DATE) AS vintage,
                   * EXCLUDE (filename)
            FROM read_parquet('{glob}/*/{t}.parquet', filename = true, union_by_name = true)""")

    con.execute("""CREATE OR REPLACE VIEW v_ports_daily AS
        SELECT d.*, p.continent, p.lat, p.lon, p.LOCODE
        FROM ports_daily d LEFT JOIN ports p USING (portid)""")

    lo, hi = con.execute("SELECT min(date), max(date) FROM ports_daily").fetchone()
    con.close()
    try:
        os.replace(tmp, DB_PATH)
    except PermissionError:
        raise SystemExit(f"{DB_PATH}를 다른 프로그램이 열고 있어 바꿀 수 없다. 닫고 다시 실행한다. "
                         f"새로 만든 DB는 {tmp}에 있다.")
    log(f"ports_daily {lo} ~ {hi}, 스냅샷 {len(vs)}개 ({vs[0]} ~ {vs[-1]}) -> {DB_PATH} "
        f"({DB_PATH.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--vintage")
    main(ap.parse_args().vintage)
