"""DuckDB -> docs/data/*.js (대시보드 자료).

게시 환경은 fetch를 막을 수 있으므로 자료를 window.__PW 객체에 싣는 <script> 파일로 둔다.
모든 일별 배열은 2019-01-01부터 하루 간격이고 길이가 같다(빠진 날은 null).

- meta.js          수집일, 자료 끝 날짜, 기준선 연도, 사건 목록
- chokepoints.js   해협·운하 28곳 메타 + 주별 통과 척수·통과량(개관용)
- cp/<id>.js       해협 한 곳의 일별 통과 척수·통과량(천 톤) × 선종
- korea.js         한국 항만 메타 + 주별 입항·수입·수출, 한국 전체 일별(국가 층)
- port/<id>.js     한국 항만 한 곳의 일별 입항·수입·수출(천 톤) × 선종

    python scripts/10_export_site_data.py
"""
import sys
import json
import math
import datetime as dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.settings import DB_PATH, DOCS_DATA, KOR, BASELINE_YEARS
import duckdb
import numpy as np
import pandas as pd

D0 = dt.date(2019, 1, 1)
TYPES = ["container", "dry_bulk", "general_cargo", "roro", "tanker"]

CP_KO = {
    "Suez Canal": "수에즈 운하", "Panama Canal": "파나마 운하", "Bosporus Strait": "보스포루스 해협",
    "Bab el-Mandeb Strait": "바브엘만데브 해협", "Malacca Strait": "말라카 해협",
    "Strait of Hormuz": "호르무즈 해협", "Cape of Good Hope": "희망봉", "Gibraltar Strait": "지브롤터 해협",
    "Dover Strait": "도버 해협", "Oresund Strait": "외레순 해협", "Taiwan Strait": "대만 해협",
    "Korea Strait": "대한해협", "Tsugaru Strait": "쓰가루 해협", "Luzon Strait": "루손 해협",
    "Lombok Strait": "롬복 해협", "Ombai Strait": "옴바이 해협", "Bohai Strait": "보하이 해협",
    "Torres Strait": "토레스 해협", "Sunda Strait": "순다 해협", "Makassar Strait": "마카사르 해협",
    "Magellan Strait": "마젤란 해협", "Yucatan Channel": "유카탄 해협", "Windward Passage": "윈드워드 해협",
    "Mona Passage": "모나 해협", "Balabac Strait": "발라바크 해협", "Bering Strait": "베링 해협",
    "Mindoro Strait": "민도로 해협", "Kerch Strait": "케르치 해협",
}
PORT_KO = {
    "Busan": "부산", "Ulsan": "울산", "Gwangyang (Kwangyang)": "광양", "Incheon": "인천",
    "Pyeongtaek": "평택", "Daesan": "대산", "Pohang": "포항", "Donghae": "동해", "Gunsan": "군산",
    "Masan": "마산", "Mokpo": "목포", "Port of Yeosu": "여수", "Jeju": "제주", "Okpo (Geoje)": "옥포(거제)",
    "Okgye": "옥계", "Boryeong LNG Terminal": "보령 LNG 터미널", "Tongyeong LNG Terminal": "통영 LNG 터미널",
    "Samcheok LNG Terminal": "삼척 LNG 터미널", "Jinhae": "진해", "Seogwipo": "서귀포", "Wando": "완도",
    "Gonghyeonjin": "공현진",
}

# 사건 표식. cps: 표시할 해협 id('*'는 전부), kor: 한국 항만 화면에도 표시.
# PortWatch 교란 사건(OT)의 날짜를 따르고, 그 밖의 사건은 널리 알려진 날짜를 쓴다.
EVENTS = [
    {"d": "2020-03-11", "ko": "WHO 코로나19 팬데믹 선언", "cps": "*", "kor": True},
    {"d": "2021-03-23", "ko": "에버기븐호 수에즈 운하 좌초(~3/29)", "cps": ["chokepoint1", "chokepoint4"], "kor": False},
    {"d": "2022-02-24", "ko": "러시아 우크라이나 침공", "cps": ["chokepoint3", "chokepoint28"], "kor": False},
    {"d": "2023-11-03", "ko": "파나마 운하 가뭄 통항 제한(~2024/8/5, PortWatch)", "cps": ["chokepoint2"], "kor": False},
    {"d": "2023-12-16", "ko": "홍해 긴장, 선사들 수에즈 회피(PortWatch)",
     "cps": ["chokepoint1", "chokepoint4", "chokepoint7"], "kor": False},
    {"d": "2026-03-01", "ko": "호르무즈 해협 통항 급감(PortWatch HORMUZ-26)", "cps": ["chokepoint6"], "kor": True},
]


def clean(x, nd):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    x = round(float(x), nd)
    return int(x) if nd == 0 or x == int(x) else x


def daily(df, cols, d1, scale=None, nd=0):
    """date 인덱스 df -> {col: [값...]} (D0..d1 전 구간, 빠진 날 null)."""
    idx = pd.date_range(D0, d1, freq="D")
    df = df.set_index(pd.to_datetime(df["date"])).reindex(idx)
    out = {}
    for c in cols:
        s = df[c] / scale if scale else df[c]
        out[c] = [clean(v, nd) for v in s.tolist()]
    return out


def weekly(df, cols, d1, scale=None, nd=0):
    """월요일 시작 주 합계. 7일이 다 찬 주만."""
    s = df.set_index(pd.to_datetime(df["date"]))[cols].reindex(pd.date_range(D0, d1, freq="D"))
    w = s.resample("W-MON", label="left", closed="left")
    agg, cnt = w.sum(min_count=1), w.count()
    full = cnt[cols[0]] == 7
    agg = agg[full]
    if scale:
        agg = agg / scale
    return [d.strftime("%Y-%m-%d") for d in agg.index], {c: [clean(v, nd) for v in agg[c].tolist()] for c in cols}


# ---------- 세계 지도·국가 비교: 주 합과 4주 창의 평년 대비 ----------
# 편차를 10% 단위로 줄여 한 글자로 싣는다. A=-100%, K=0%, e=+200%(이상). 자료가 적어 계산하지 않은 주는 '.'
ALPH = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcde"
KO_COUNTRY = {
    "WLD": "세계", "110": "선진국", "119": "G7", "123": "기타 선진국", "163": "유로 지역", "998": "유럽연합",
    "200": "신흥·개발도상국", "205": "중남미·카리브", "400": "중동·중앙아시아", "505": "신흥·개발도상 아시아",
    "510": "ASEAN-5", "511": "아시아 선진국(일본 제외)", "512": "아시아 신흥국(중국 제외)", "513": "ASEAN-10",
    "603": "사하라 이남 아프리카", "903": "신흥·개발도상 유럽",
    "KOR": "한국", "CHN": "중국", "JPN": "일본", "USA": "미국", "TWN": "대만", "HKG": "홍콩", "IDN": "인도네시아",
    "SGP": "싱가포르", "MYS": "말레이시아", "VNM": "베트남", "THA": "태국", "PHL": "필리핀", "IND": "인도",
    "PAK": "파키스탄", "BGD": "방글라데시", "LKA": "스리랑카", "MMR": "미얀마", "KHM": "캄보디아", "BRN": "브루나이",
    "PRK": "북한", "AUS": "호주", "NZL": "뉴질랜드", "PNG": "파푸아뉴기니", "FJI": "피지",
    "NLD": "네덜란드", "DEU": "독일", "GBR": "영국", "FRA": "프랑스", "ITA": "이탈리아", "ESP": "스페인",
    "PRT": "포르투갈", "BEL": "벨기에", "GRC": "그리스", "NOR": "노르웨이", "SWE": "스웨덴", "DNK": "덴마크",
    "FIN": "핀란드", "POL": "폴란드", "IRL": "아일랜드", "ISL": "아이슬란드", "EST": "에스토니아", "LVA": "라트비아",
    "LTU": "리투아니아", "ROU": "루마니아", "BGR": "불가리아", "HRV": "크로아티아", "SVN": "슬로베니아",
    "MLT": "몰타", "CYP": "키프로스", "MNE": "몬테네그로", "ALB": "알바니아", "UKR": "우크라이나", "RUS": "러시아",
    "GEO": "조지아", "TUR": "튀르키예", "KAZ": "카자흐스탄", "AZE": "아제르바이잔", "TKM": "투르크메니스탄",
    "SAU": "사우디아라비아", "ARE": "아랍에미리트", "IRN": "이란", "IRQ": "이라크", "KWT": "쿠웨이트", "QAT": "카타르",
    "OMN": "오만", "BHR": "바레인", "YEM": "예멘", "ISR": "이스라엘", "JOR": "요르단", "LBN": "레바논", "SYR": "시리아",
    "EGY": "이집트", "LBY": "리비아", "TUN": "튀니지", "DZA": "알제리", "MAR": "모로코", "SDN": "수단", "DJI": "지부티",
    "KEN": "케냐", "TZA": "탄자니아", "MOZ": "모잠비크", "MDG": "마다가스카르", "MUS": "모리셔스", "ZAF": "남아프리카공화국",
    "AGO": "앙골라", "NGA": "나이지리아", "GHA": "가나", "CIV": "코트디부아르", "SEN": "세네갈",
    "CAN": "캐나다", "MEX": "멕시코", "PAN": "파나마", "CUB": "쿠바", "JAM": "자메이카", "DOM": "도미니카공화국",
    "BRA": "브라질", "ARG": "아르헨티나", "CHL": "칠레", "PER": "페루", "COL": "콜롬비아", "ECU": "에콰도르",
    "URY": "우루과이", "VEN": "베네수엘라",
}


def weekly_sum(daily, d1):
    """date 인덱스 × 개체 일별 값 -> 월요일 시작 주 합(7일이 다 찬 주만)."""
    daily = daily.reindex(pd.date_range(D0, d1, freq="D"))
    s = daily.resample("W-MON", label="left", closed="left").sum(min_count=1)
    return s[(s.index >= pd.Timestamp(D0)) & (s.index + pd.Timedelta(days=6) <= pd.Timestamp(d1))]


def dev4(W, min_base):
    """주 × 개체 합 W -> 4주 창 합의 평년 대비 편차(주 × 개체)와 평년 값.
    평년은 기준연도마다 같은 달·일에 가장 가까운 주(±4일)의 4주 창 합을 평균한 것.
    평년 값이 min_base보다 작으면(작은 항만·나라의 잡음) 편차를 비워 둔다."""
    R = W.rolling(4, min_periods=4).sum().to_numpy(dtype=float)
    weeks = W.index
    t = weeks.values.astype("datetime64[D]").astype(np.int64)
    acc, cnt = np.zeros_like(R), np.zeros_like(R)
    for y in BASELINE_YEARS:
        tg = np.array([np.datetime64(dt.date(y, w.month, min(w.day, 28) if w.month == 2 else w.day), "D")
                       for w in weeks]).astype(np.int64)
        j = np.clip(np.searchsorted(t, tg), 1, len(t) - 1)
        j = np.where(np.abs(t[j - 1] - tg) < np.abs(t[j] - tg), j - 1, j)
        v = R[j].copy()
        v[np.abs(t[j] - tg) > 4] = np.nan
        ok = ~np.isnan(v)
        acc += np.where(ok, v, 0)
        cnt += ok
    B = np.where(cnt > 0, acc / np.maximum(cnt, 1), np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        D = np.where(B >= min_base, R / B - 1, np.nan)
    return D, B


def encode(col):
    out = []
    for v in col:
        out.append("." if np.isnan(v) else ALPH[int(np.clip(np.round(v * 10), -10, 20)) + 10])
    return "".join(out)


def export_world(con, d1, sizes):
    """세계 항만 지도: 항만 2,065곳 × 주, 4주 창 평년 대비를 글자로. 입항(pc)과 물동량(vol, 수입+수출) 두 층."""
    meta = con.execute("""SELECT portid, portname, country, ISO3, round(lat, 3) AS lat, round(lon, 3) AS lon
                          FROM ports ORDER BY portid""").df()
    d = con.execute("""SELECT date, portid, portcalls AS pc, "import" + export AS vol FROM ports_daily""").df()
    d["date"] = pd.to_datetime(d["date"])
    w = con.execute("""SELECT date, portcalls AS pc, "import" + export AS vol FROM country_daily WHERE ISO3 = 'WLD'""").df()
    w["date"] = pd.to_datetime(w["date"])
    layers, weeks = {}, None
    for m, min_base in [("pc", 8), ("vol", 40_000)]:      # 4주에 입항 8척(주 2척), 물동량 4만 톤 미만은 계산하지 않는다
        W = weekly_sum(d.pivot(index="date", columns="portid", values=m), d1)[meta["portid"]].fillna(0)
        D, _ = dev4(W, min_base)
        weeks = W.index
        size = W.iloc[-52:].mean()                          # 점 크기: 최근 52주 주평균
        WW = weekly_sum(w.set_index("date")[[m]], d1)
        DW, _ = dev4(WW, 0)
        layers[m] = {"size": [clean(v / (1 if m == "pc" else 1000), 1) for v in size.tolist()],
                     "dev": [encode(D[:, k]) for k in range(D.shape[1])],
                     "world": [clean(v, 3) for v in DW[:, 0].tolist()]}
    ports = [[r.portid, PORT_KO.get(r.portname, r.portname), KO_COUNTRY.get(r.ISO3, r.country), r.ISO3, r.lat, r.lon]
             for r in meta.itertuples()]
    base = {"weeks": [x.strftime("%Y-%m-%d") for x in weeks], "alph": ALPH, "ports": ports}
    sizes["world.js"] = write_js(DOCS_DATA / "world.js", "world", {**base, "pc": layers["pc"]})
    sizes["world_vol.js"] = write_js(DOCS_DATA / "world_vol.js", "world:vol", layers["vol"])
    return len(ports), len(weeks)


def export_countries(con, d1, sizes):
    """국가 비교: 국가·권역 196개. 개관(countries.js)과 나라별 주간·월간 자료(country/<ISO3>.js)."""
    c = con.execute("""SELECT date, ISO3, country, portcalls AS pc, "import" / 1000 AS im, export / 1000 AS ex
                       FROM country_daily""").df()
    c["date"] = pd.to_datetime(c["date"])
    names = c.groupby("ISO3")["country"].first()
    ids = sorted(names.index)
    W = {m: weekly_sum(c.pivot(index="date", columns="ISO3", values=m), d1)[ids] for m in ("pc", "im", "ex")}
    weeks = W["pc"].index
    D = {m: dev4(W[m], mb)[0] for m, mb in (("pc", 8), ("im", 10), ("ex", 10))}   # im·ex는 천 톤
    tn = con.execute("""SELECT ISO3, strftime(date, '%Y-%m') AS m, value_import_total AS v_im, value_export_total AS v_ex,
                               volume_import_total AS q_im, volume_export_total AS q_ex, trade_value AS v, trade_volume AS q
                        FROM trade_monthly ORDER BY m""").df()
    months = sorted(tn["m"].unique())
    lst = []
    for k, iso in enumerate(ids):
        agg = iso == "WLD" or not iso.isalpha()
        rec = {"id": iso, "name": names[iso], "ko": KO_COUNTRY.get(iso, names[iso]), "agg": agg,
               "pc_day": clean(W["pc"][iso].iloc[-52:].mean() / 7, 1)}
        rec["dev"] = {m: clean(D[m][-1, k], 3) for m in W}
        rec["spark"] = {m: [clean(v, 0) for v in W[m][iso].iloc[-104:].tolist()] for m in W}
        lst.append(rec)
        t = tn[tn.ISO3 == iso].set_index("m").reindex(months)
        sizes[f"country/{iso}.js"] = write_js(DOCS_DATA / "country" / f"{iso}.js", f"country:{iso}", {
            "id": iso, "name": names[iso], "ko": rec["ko"],
            **{m: [clean(v, 0 if m == "pc" else 1) for v in W[m][iso].tolist()] for m in W},
            "dev": {m: [clean(v, 3) for v in D[m][:, k].tolist()] for m in W},
            "tn": {"months": months, **{col: [clean(v, 1) for v in t[col].tolist()]
                                         for col in ("v_im", "v_ex", "q_im", "q_ex", "v", "q")}}})
    sizes["countries.js"] = write_js(DOCS_DATA / "countries.js", "countries",
                                     {"weeks": [x.strftime("%Y-%m-%d") for x in weeks], "list": lst})
    return len(ids)


def write_js(path, key, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    path.write_text(f'window.__PW=window.__PW||{{}};window.__PW["{key}"]={body};\n', encoding="utf-8")
    return path.stat().st_size


def main():
    con = duckdb.connect(str(DB_PATH), read_only=True)
    df = lambda s, *a: con.execute(s, list(a)).df()
    one = lambda s, *a: con.execute(s, list(a)).fetchone()
    sizes = {}

    vintage, data_edit, fetched = one("""SELECT vintage, max(data_last_edit), max(fetched_at) FROM snapshots
                                         WHERE loaded GROUP BY vintage""")
    cp_d1 = one("SELECT max(date) FROM chokepoints_daily")[0]
    pt_d1 = one("SELECT max(date) FROM ports_daily")[0]

    # ---------- 해협·운하 ----------
    cps = df("SELECT portid AS id, portname AS name, lat, lon FROM chokepoints ORDER BY portid")
    n_cols = ["n_total"] + [f"n_{t}" for t in TYPES]
    c_cols = ["capacity"] + [f"capacity_{t}" for t in TYPES]
    cp_list = []
    for r in cps.itertuples():
        d = df("SELECT * FROM chokepoints_daily WHERE portid = ? ORDER BY date", r.id)
        rec = {"id": r.id, "name": r.name, "ko": CP_KO.get(r.name, r.name), "lat": r.lat, "lon": r.lon}
        sizes[f"cp/{r.id}.js"] = write_js(DOCS_DATA / "cp" / f"{r.id}.js", f"cp:{r.id}", {
            **rec, "d0": D0.isoformat(),
            "n": daily(d, n_cols, cp_d1),
            "cap": daily(d, c_cols, cp_d1, scale=1000, nd=1)})
        weeks, w = weekly(d, ["n_total", "capacity"], cp_d1)
        rec.update({"wk_n": w["n_total"], "wk_cap": [clean(v / 1000, 0) if v is not None else None
                                                      for v in w["capacity"]]})
        cp_list.append(rec)
    sizes["chokepoints.js"] = write_js(DOCS_DATA / "chokepoints.js", "chokepoints",
                                       {"weeks": weeks, "list": cp_list})

    # ---------- 한국 항만 ----------
    ports = df("""SELECT portid AS id, portname AS name, lat, lon, vessel_count_total AS vessels,
                         share_country_maritime_import AS sh_imp, share_country_maritime_export AS sh_exp,
                         industry_top1, industry_top2, industry_top3, LOCODE AS locode
                  FROM ports WHERE ISO3 = ? ORDER BY vessel_count_total DESC""", KOR)
    pc_cols = ["portcalls"] + [f"portcalls_{t}" for t in TYPES]
    im_cols = ["import"] + [f"import_{t}" for t in TYPES]
    ex_cols = ["export"] + [f"export_{t}" for t in TYPES]
    # ports_daily에 메타의 모든 항만이 있지는 않을 수 있다(2026-09-15 17:58 UTC 수정 전에는 한국 22곳 중 10곳).
    # 있는 항만은 입항 0인 날도 행이 있으나 혹시 빠진 날은 0으로 채운다. 일별 자료가 없는 항만은 메타만 싣고
    # (국가 합계에는 포함), 대시보드는 그 목록을 자료에서 세어 보여 준다.
    events_kor = df("""WITH k AS (SELECT portid FROM ports WHERE ISO3 = ?)
        SELECT d.eventname AS name, d.eventtype AS type, CAST(d.fromdate AS DATE) AS f, CAST(d.todate AS DATE) AS t,
               d.alertlevel AS alert, list(k.portid) AS ports
        FROM disruptions d, k
        WHERE list_contains(string_split(replace(d.affectedports, ' ', ''), ';'), k.portid)
        GROUP BY ALL ORDER BY f""", KOR)
    port_list = []
    for r in ports.itertuples():
        d = df("SELECT * FROM ports_daily WHERE portid = ? ORDER BY date", r.id)
        rec = {"id": r.id, "name": r.name, "ko": PORT_KO.get(r.name, r.name),
               "lat": clean(r.lat, 5), "lon": clean(r.lon, 5), "vessels": clean(r.vessels, 0) or 0,
               "sh_imp": clean(r.sh_imp, 2), "sh_exp": clean(r.sh_exp, 2),
               "locode": r.locode if isinstance(r.locode, str) else None,
               "industry": [x for x in (r.industry_top1, r.industry_top2, r.industry_top3) if isinstance(x, str)],
               "days": len(d)}
        if len(d):
            d["date"] = pd.to_datetime(d["date"])
            full = pd.DataFrame({"date": pd.date_range(D0, pt_d1, freq="D")})
            d = full.merge(d, on="date", how="left")
            d[pc_cols + im_cols + ex_cols] = d[pc_cols + im_cols + ex_cols].fillna(0)
            sizes[f"port/{r.id}.js"] = write_js(DOCS_DATA / "port" / f"{r.id}.js", f"port:{r.id}", {
                **rec, "d0": D0.isoformat(),
                "pc": daily(d, pc_cols, pt_d1),
                "im": daily(d, im_cols, pt_d1, scale=1000, nd=1),
                "ex": daily(d, ex_cols, pt_d1, scale=1000, nd=1)})
            kweeks, w = weekly(d, ["portcalls", "import", "export", "import_tanker"], pt_d1)
            rec.update({"wk_pc": w["portcalls"],
                        "wk_im": [clean(v / 1000, 1) for v in w["import"]],
                        "wk_ex": [clean(v / 1000, 1) for v in w["export"]],
                        "wk_imt": [clean(v / 1000, 1) for v in w["import_tanker"]]})
        port_list.append(rec)

    kd = df("SELECT * FROM country_daily WHERE ISO3 = ? ORDER BY date", KOR)
    kor_total = {"id": "KOR", "name": "Korea (all ports)", "ko": "한국 전체", "d0": D0.isoformat(),
                 "pc": daily(kd, pc_cols, pt_d1),
                 "im": daily(kd, im_cols, pt_d1, scale=1000, nd=1),
                 "ex": daily(kd, ex_cols, pt_d1, scale=1000, nd=1)}
    # 이웃 나라와 견주기: 국가 층 월평균(천 톤/일), 다 찬 달만
    last_full = (pd.Timestamp(pt_d1) + pd.Timedelta(days=1)).to_period("M") - 1
    pm = df("""SELECT ISO3, date_trunc('month', date) AS m, avg(import_tanker) / 1000 AS tk, avg("import") / 1000 AS tot
               FROM country_daily WHERE ISO3 IN ('KOR', 'JPN', 'CHN', 'TWN', 'IND') AND date <= ?
               GROUP BY ALL ORDER BY m""", last_full.end_time.date())
    months = sorted({str(m)[:7] for m in pm["m"]})
    peer_ko = {"KOR": "한국", "JPN": "일본", "CHN": "중국", "TWN": "대만", "IND": "인도"}
    peers = {"months": months, "series": {}}
    for iso3, ko in peer_ko.items():
        sub = pm[pm.ISO3 == iso3]
        s = sub.set_index(sub["m"].astype(str).str[:7])
        peers["series"][iso3] = {"ko": ko, "tk": [clean(s["tk"].get(m), 1) for m in months],
                                 "tot": [clean(s["tot"].get(m), 1) for m in months]}

    ev = [{"f": str(e.f)[:10], "t": str(e.t)[:10] if pd.notna(e.t) else None, "name": e.name, "type": e.type,
           "alert": e.alert, "ports": list(e.ports)} for e in events_kor.itertuples()]
    sizes["korea.js"] = write_js(DOCS_DATA / "korea.js", "korea",
                                 {"weeks": kweeks, "ports": port_list, "total": kor_total, "events": ev,
                                  "peers": peers})

    # ---------- 세계 항만 지도·국가 비교 ----------
    n_ports, n_weeks = export_world(con, pt_d1, sizes)
    n_countries = export_countries(con, pt_d1, sizes)

    # ---------- 메타 ----------
    sizes["meta.js"] = write_js(DOCS_DATA / "meta.js", "meta", {
        "vintage": str(vintage),
        "fetched_at": fetched.strftime("%Y-%m-%d %H:%M UTC") if fetched else None,
        "data_last_edit": data_edit.strftime("%Y-%m-%d %H:%M UTC") if data_edit else None,
        "d0": D0.isoformat(), "cp_d1": str(cp_d1), "pt_d1": str(pt_d1),
        "baseline_years": BASELINE_YEARS, "events": EVENTS,
        "types": TYPES,
        # 정보 탭이 자료에서 세어 보여 주는 규모(PortWatch가 범위를 바꾸면 달라진다)
        "n_ports": n_ports, "n_chokepoints": len(cps), "n_countries": n_countries, "n_weeks": n_weeks})

    con.close()
    total = sum(sizes.values())
    n_ct = sum(1 for k in sizes if k.startswith("country/"))
    print(f"country/*.js {n_ct}개  {sum(v for k, v in sizes.items() if k.startswith('country/')) / 1e6:6.2f} MB")
    for k in ["meta.js", "chokepoints.js", "korea.js", "world.js", "world_vol.js", "countries.js"]:
        print(f"{k:22s} {sizes[k] / 1e3:8.1f} KB")
    n_cp = sum(1 for k in sizes if k.startswith("cp/"))
    n_pt = sum(1 for k in sizes if k.startswith("port/"))
    print(f"cp/*.js   {n_cp}개  {sum(v for k, v in sizes.items() if k.startswith('cp/')) / 1e6:6.2f} MB")
    print(f"port/*.js {n_pt}개  {sum(v for k, v in sizes.items() if k.startswith('port/')) / 1e6:6.2f} MB")
    print(f"합계 {total / 1e6:.2f} MB -> {DOCS_DATA}")


if __name__ == "__main__":
    main()
