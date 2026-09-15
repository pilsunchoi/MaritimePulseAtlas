"""로컬 주간 스냅샷: 수집 -> DuckDB -> 검증. Windows 작업 스케줄러가 매주 수요일 09:00에 부른다.

사이트 자료(docs/data)는 GitHub Actions가 만들어 올리므로 여기서는 만들지 않는다.
로컬에서는 수집 시각별 원자료 스냅샷을 쌓아 PortWatch의 사후 수정을 추적한다.
창 없이 돌도록 pythonw.exe로 부르고, 하위 스크립트도 창을 띄우지 않는다. 기록은 logs/weekly_local.log.

    pythonw scripts/weekly_local.py
"""
import os
import sys
import subprocess
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "logs" / "weekly_local.log"
ENV_DIR = Path(sys.executable).parent
PY = ENV_DIR / "python.exe"          # pythonw로 불려도 하위 스크립트는 python.exe로 돌려 출력을 받는다
STEPS = ["01_fetch_portwatch.py", "02_build_db.py", "05_validate.py"]


def log(msg):
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def main():
    # conda를 activate하지 않고 부르므로 환경의 DLL 경로를 직접 붙인다
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env["PATH"] = os.pathsep.join([str(ENV_DIR), str(ENV_DIR / "Library" / "bin"),
                                   str(ENV_DIR / "Scripts"), env.get("PATH", "")])
    log("===== 시작")
    for s in STEPS:
        r = subprocess.run([str(PY), str(ROOT / "scripts" / s)], cwd=ROOT, env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        tail = (r.stdout + r.stderr).strip().splitlines()[-2:]
        log(f"{s}: exit {r.returncode} | " + " / ".join(tail))
        if r.returncode:
            log("===== 실패, 중단")
            return r.returncode
    log("===== 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
