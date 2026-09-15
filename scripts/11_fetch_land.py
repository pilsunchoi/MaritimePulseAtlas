"""지구본용 육지 윤곽 -> docs/data/land110.js, land50.js (index_globe.html 전용).

Natural Earth(퍼블릭 도메인)를 TopoJSON으로 묶은 world-atlas(버전 고정)를 받아
window.__PW["land110"], window.__PW["land50"]에 싣는다. 한 번만 돌리면 된다.

    python scripts/11_fetch_land.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.settings import DOCS_DATA
import requests

SRC = "https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/{}.json"


def main():
    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    for name, key in [("land-110m", "land110"), ("land-50m", "land50")]:
        r = requests.get(SRC.format(name), timeout=60)
        r.raise_for_status()
        topo = r.text.strip()
        assert topo.startswith("{") and '"land"' in topo, f"{name}: TopoJSON이 아님"
        p = DOCS_DATA / f"{key}.js"
        p.write_text(f'window.__PW=window.__PW||{{}};window.__PW["{key}"]={topo};\n', encoding="utf-8")
        print(f"{p.name:12s} {p.stat().st_size / 1e3:7.1f} KB  <- {SRC.format(name)}")


if __name__ == "__main__":
    main()
