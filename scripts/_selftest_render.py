# -*- coding: utf-8 -*-
"""自检：四图产出、轴序校验、HTML 自包含。

运行：python scripts/_selftest_render.py
"""
import collections
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import render  # noqa: E402


def main():
    S = os.path.join(ROOT, "assets", "sample")
    rows = json.load(io.open(os.path.join(S, "tasks.json"), encoding="utf-8"))
    cfg = json.load(io.open(os.path.join(S, "majors.json"), encoding="utf-8"))

    # 轴序校验：按分数反推的象限必须与任务表一致（曾因 levels 顺序写反而整体反向）
    got = render.quad_counts(rows)
    want = collections.Counter(r["quad"] for r in rows)
    assert got == want, "象限不一致——按分数反推 %s，任务表 %s（检查 LEVELS 顺序）" % (
        dict(got), dict(want))

    # quad_of 的四个分支
    assert render.quad_of(0.8, 0.8) == "Ⅱ 双高"
    assert render.quad_of(0.2, 0.8) == "Ⅰ 仅机器人高"
    assert render.quad_of(0.8, 0.2) == "Ⅲ 仅 LLM 高"
    assert render.quad_of(0.2, 0.2) == "Ⅳ 双低"
    assert render.quad_of(None, 0.2) == "待定"
    # 分界值 0.50 本身归入「高」
    assert render.quad_of(0.5, 0.5) == "Ⅱ 双高"

    # LEVELS 顺序必须与刻度标签一致
    assert render.LEVELS == [0.20, 0.55, 0.80]
    assert render.LEVEL_LABELS == ["0.20", "0.55", "0.80"]

    d = tempfile.mkdtemp()
    focus = ["汽车运用与维修", "航空服务"]
    paths = render.figures(rows, cfg, d, focus)
    names = sorted(os.path.basename(p) for p in paths)
    for need in ("contrast.png", "matrix.png", "shift.png", "structure_汽.png", "structure_航.png"):
        assert need in names, "缺少图 %s，实为 %s" % (need, names)
    for p in paths:
        assert os.path.getsize(p) > 8000, "%s 体积过小，可能渲染失败" % p

    # HTML 必须自包含（图 base64 内嵌）、无模板残留、含来源声明
    p = render.html(rows, cfg, d, school="样例职业学校", focus_majors=focus)
    h = io.open(p, encoding="utf-8").read()
    n_img = h.count("data:image/png;base64,")
    assert n_img == 5, "应内嵌 5 张图（对照/两张结构/矩阵/下移），实为 %d" % n_img
    assert "__" not in h.replace("__", "", 0) or "{{" not in h, "模板占位符应全部替换"
    for ph in ("__SCHOOL__", "__TOTAL__", "__FIG_CONTRAST__", "__MAJOR_ROWS__"):
        assert ph not in h, "占位符未替换：%s" % ph
    assert "样例职业学校" in h, "学校名未写入"
    assert "O*NET" in h and "CC BY 4.0" in h, "页脚应含 O*NET 来源与许可声明"
    assert str(len(rows)) in h, "任务总数未出现在报告中"
    assert "为什么图要在任务层画" in h, "报告应含图示原则说明"

    print("OK: 四图 + HTML 通过；象限计数 %s；HTML %.0f KB"
          % (dict(want), os.path.getsize(p) / 1024))


if __name__ == "__main__":
    main()
