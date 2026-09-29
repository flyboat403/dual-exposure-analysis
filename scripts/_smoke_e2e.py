# -*- coding: utf-8 -*-
"""端到端冒烟测试：样例数据 → 任务表 → 复核清单 → 四图 + HTML。全流程不联网。

第一步必跑预检；预检不通过立即退出并打印缺失项。

运行：python scripts/_smoke_e2e.py
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import precheck  # noqa: E402

PY = sys.executable


def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise AssertionError("命令失败：%s\n--- stdout ---\n%s\n--- stderr ---\n%s"
                             % (cmd, (r.stdout or "")[-1500:], (r.stderr or "")[-1500:]))
    return r.stdout or ""


def main():
    # 步骤 0：预检
    pr = precheck.run(os.path.join(ROOT, "assets"))
    if not pr["ok"]:
        print("预检未通过，缺失项：")
        for f in pr["files"]:
            if not f["ok"]:
                print("   [X] %s" % f["path"])
        if not pr["matplotlib"]:
            print("   [X] matplotlib（出图必需）")
        raise SystemExit(1)
    idx = json.load(io.open(os.path.join(ROOT, "assets", "onet_ari.json"), encoding="utf-8"))
    print("预检通过（Python %s，O*NET 索引 %d 个职业）" % (pr["python"], idx["_meta"]["count"]))

    work = tempfile.mkdtemp(prefix="dxt_smoke_")
    S = os.path.join(ROOT, "assets", "sample")
    std = os.path.join(S, "standards.json")
    mj = os.path.join(S, "majors.json")

    # 步骤 3：标准文本 → 任务表
    tasks = os.path.join(work, "tasks.json")
    out = run('%s "%s/build_tasks.py" --standards "%s" --majors "%s" --out "%s"'
              % (PY, HERE, std, mj, tasks))
    assert os.path.getsize(tasks) > 500, "任务表未生成"
    print("   [1/5] 任务表  " + out.strip().splitlines()[0])

    # 步骤 2：映射校验与聚合（样例已确认的映射）
    mp = os.path.join(S, "mapping.json")
    out = run('%s "%s/build_mapping_prompt.py" --validate "%s" --aggregate "%s"'
              % (PY, HERE, mp, mp))
    assert "OK" in out, "映射校验未通过：%s" % out
    print("   [2/5] 映射校验  " + out.strip().splitlines()[0])

    # 步骤 5：复核清单（md 人读 / csv 机器读 / xlsx 教研组填写，带下拉）
    md = os.path.join(work, "sheet.md")
    csv = os.path.join(work, "sheet.csv")
    xlsx = os.path.join(work, "sheet.xlsx")
    out = run('%s "%s/build_review_sheet.py" --tasks "%s" --out-md "%s" --out-csv "%s" '
              '--out-xlsx "%s"' % (PY, HERE, tasks, md, csv, xlsx))
    print("   [3/5] 复核清单  " + out.strip().splitlines()[0])
    import zipfile
    _z = zipfile.ZipFile(xlsx)
    _s2 = _z.read("xl/worksheets/sheet2.xml").decode("utf-8")
    assert 'type="list"' in _s2 and "0.20,0.55,0.80" in _s2, "xlsx 待判定表应带下拉"
    _s3 = _z.read("xl/worksheets/sheet3.xml").decode("utf-8")
    assert 'type="list"' in _s3, "xlsx 冲突表应带下拉"

    # 步骤 6：出图与 HTML（用样例的已判定任务表）
    judged = os.path.join(S, "tasks.json")
    out = run('%s "%s/render.py" --tasks "%s" --majors "%s" --outdir "%s" '
              '--school "样例职业学校" --focus "汽车运用与维修,航空服务"'
              % (PY, HERE, judged, mj, work))
    assert os.path.exists(os.path.join(work, "report.html")), "HTML 未生成"
    print("   [4/5] 报告生成  " + out.strip())

    # 产物清点
    need = ["tasks.json", "sheet.md", "sheet.csv", "sheet.xlsx", "report.html",
            "contrast.png", "matrix.png", "shift.png",
            "structure_汽.png", "structure_航.png"]
    missing = [f for f in need if not os.path.exists(os.path.join(work, f))]
    assert not missing, "缺少产物：%s" % missing
    for f in need:
        p = os.path.join(work, f)
        assert os.path.getsize(p) > 500, "%s 体积过小" % f
    h = io.open(os.path.join(work, "report.html"), encoding="utf-8").read()
    assert h.count("data:image/png;base64,") == 5, "HTML 应内嵌 5 张图"
    assert "__" not in h.split("<style>")[0], "模板占位符未替换"
    print("   [5/5] 产物清点  %d 个文件，HTML %.0f KB"
          % (len(need), os.path.getsize(os.path.join(work, "report.html")) / 1024))

    print("\nOK: 端到端跑通。产物在 %s" % work)
    print("    （该目录为临时目录，可自行删除）")


if __name__ == "__main__":
    main()
