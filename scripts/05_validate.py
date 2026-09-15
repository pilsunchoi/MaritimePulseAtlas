"""적재 검증. 실패하면 0이 아닌 코드로 끝난다(주간 자동 갱신에서 게시를 막는다).

- 층별 행 수가 manifest와 같은가, 키 중복이 없는가
- 날짜 범위: 2019-01-01부터 시작하고, 마지막 날짜가 수집일에서 14일 이내인가
- 해협 28곳 × 모든 날짜가 빠짐없이 있는가
- 한국 항만이 있고, 항만 일별 합계(KOR)가 국가 일별(KOR)과 맞는가
- 직전 스냅샷 대비 과거 구간 수정 규모(참고용, 실패 조건 아님)
"""
import sys
import datetime as dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.settings import DB_PATH, KOR
import duckdb

fails = []


def check(name, ok, detail=""):
    print(f"[{'OK' if ok else 'FAIL'}] {name}  {detail}")
    if not ok:
        fails.append(name)


def main():
    con = duckdb.connect(str(DB_PATH), read_only=True)
    q = lambda s, *a: con.execute(s, list(a)).fetchall()
    fetched = q("SELECT max(fetched_at) FROM snapshots WHERE loaded")[0][0].date()

    for t, rows in q("SELECT tbl, rows FROM snapshots WHERE loaded ORDER BY tbl"):
        n = q(f"SELECT count(*) FROM {t}")[0][0]
        check(f"{t} 행 수", n == rows, f"{n:,}")

    for t, key in [("ports_daily", "date, portid"), ("chokepoints_daily", "date, portid"),
                   ("country_daily", "date, ISO3"), ("ports", "portid"), ("chokepoints", "portid")]:
        d = q(f"SELECT count(*) FROM (SELECT {key} FROM {t} GROUP BY ALL HAVING count(*) > 1)")[0][0]
        check(f"{t} 키 중복 없음 ({key})", d == 0, f"중복 {d}")

    for t in ["ports_daily", "chokepoints_daily", "country_daily"]:
        lo, hi = q(f"SELECT min(date), max(date) FROM {t}")[0]
        lag = (fetched - hi).days
        check(f"{t} 기간", lo == dt.date(2019, 1, 1) and lag <= 14, f"{lo} ~ {hi} (수집일 대비 {lag}일)")

    n_cp, n_days, n_rows = q("""SELECT count(DISTINCT portid), count(DISTINCT date), count(*)
                                FROM chokepoints_daily""")[0]
    check("해협 × 날짜 완전", n_cp == 28 and n_rows == n_cp * n_days, f"{n_cp}곳 × {n_days}일 = {n_rows:,}")

    n_kor = q("SELECT count(*) FROM ports WHERE ISO3 = ?", KOR)[0][0]
    check("한국 항만 메타", n_kor >= 15, f"{n_kor}곳")

    # 일별 항만 층에는 메타의 항만 중 일부만 있을 수 있다(2026-09-15 17:58 UTC 수정 전 한국 22곳 중 10곳,
    # 이후 22곳 모두). 국가 층은 전 항만 합이므로 항만 합계 <= 국가 합계이고, 한국은 큰 항만이 다 들어 있어
    # 수입 비율이 0.9를 넘어야 한다.
    n_pd = q("SELECT count(DISTINCT portid) FROM ports_daily WHERE ISO3 = ?", KOR)[0][0]
    missing = [r[0] for r in q("""SELECT portname FROM ports WHERE ISO3 = ? AND portid NOT IN
                                  (SELECT DISTINCT portid FROM ports_daily) ORDER BY vessel_count_total DESC""", KOR)]
    print(f"[INFO] 한국 항만 일별 자료 {n_pd}곳, 없음 {len(missing)}곳: {', '.join(missing)}")
    r = q("""WITH p AS (SELECT date, sum(portcalls) AS pc, sum("import") AS im FROM ports_daily
                        WHERE ISO3 = ? GROUP BY date),
                  c AS (SELECT date, portcalls AS pc, "import" AS im FROM country_daily WHERE ISO3 = ?)
             SELECT count(*), max(p.pc - c.pc), sum(p.im) / nullif(sum(c.im), 0)
             FROM p JOIN c USING (date) WHERE date > (SELECT max(date) FROM c) - 365""", KOR, KOR)[0]
    check("한국: 항만 합계 <= 국가 합계, 수입 비율 >= 0.9", r[0] > 300 and r[1] <= 0 and 0.9 <= r[2] <= 1.0001,
          f"{r[0]}일, 입항(항만-국가) 최대 {r[1]}, 수입 비율 {r[2]:.4f}")

    # 직전 스냅샷 대비 수정 규모 (참고)
    vs = [v for (v,) in q("SELECT DISTINCT vintage FROM snapshots ORDER BY vintage")]
    if len(vs) >= 2:
        prev, cur = vs[-2], vs[-1]
        r = q("""SELECT count(*), sum(abs(a."import" - b."import")) / nullif(sum(b."import"), 0)
                 FROM ports_daily_vintages a JOIN ports_daily_vintages b USING (date, portid)
                 WHERE a.vintage = ? AND b.vintage = ? AND a."import" IS DISTINCT FROM b."import" """, cur, prev)[0]
        print(f"[INFO] {prev} -> {cur}: 수입 값이 바뀐 항만·일 {r[0]:,}개, 절대 수정 비율 {r[1] or 0:.4%}")

    con.close()
    if fails:
        print(f"\n실패 {len(fails)}건: {fails}")
        sys.exit(1)
    print("\n모든 검증 통과")


if __name__ == "__main__":
    main()
