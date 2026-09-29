# -*- coding: utf-8 -*-
"""重建 assets/sample/tasks.json。

样例 = 3 个专业 26 条能力条目 → 19 条任务。判定沿用一次已核验的真实判定结果，
在**新边界**上重新对齐（旧边界把「…拆装、检测与更换」切成了两条，本版合为一条）。

运行：python scripts/_make_sample_tasks.py
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import build_tasks  # noqa: E402
import render  # noqa: E402

NOTE = "样例判定，沿用一次已核验的真实判定结果（在新任务边界上重新对齐）"

# 键 = 任务文本前缀（按出现顺序匹配），值 = (llm, robot, src, conf)
SCORES = [
    # 汽车运用与维修
    ("具备正确选择并熟练使用汽车维修常用工具", 0.80, 0.20, "人工校对", "人工"),
    ("具备阅读汽车维修设备使用说明书", 0.80, 0.20, "人工校对", "人工"),
    ("具备汽车维护作业的能力", 0.20, 0.55, "模拟", "低"),
    ("具备汽车发动机总成及其零部件拆装", 0.20, 0.80, "模拟", "中"),
    ("具备汽车发动机控制系统检查", 0.20, 0.80, "模拟", "中"),
    ("具备汽车底盘及底盘控制系统维修检查", 0.80, 0.80, "人工校对", "人工"),
    ("具备汽车车身电气设备及其电路拆装", 0.20, 0.80, "模拟", "中"),
    # 服装设计与工艺
    ("具有整合服装款式、色彩、材料", 0.80, 0.20, "人工校对", "人工"),
    ("具有服装造型设计与款式绘制表达", 0.80, 0.20, "人工校对", "人工"),
    ("具有操作常用服装缝纫设备", 0.20, 0.80, "模拟", "中"),
    ("具有制作常见典型品类服装", 0.20, 0.80, "人工校对", "人工"),
    ("具有运用电脑辅助软件绘制服装款式图", 0.80, 0.80, "模拟", "低"),
    ("具有适应产业数字化发展需求的专业信息技术应用", 0.80, 0.20, "人工校对", "人工"),
    ("具有一般服装销售、导购、陈列", 0.20, 0.20, "人工校对", "人工"),
    # 航空服务
    ("具有熟练使用离港系统为旅客办理乘机登记", 0.80, 0.80, "人工校对", "人工"),
    ("具有通过对旅客和行李进行检查", 0.80, 0.80, "人工校对", "人工"),
    ("具有按工作流程和服务程序进行机上旅客服务", 0.20, 0.20, "人工校对", "人工"),
    ("具有为进港旅客提供行李发放服务", 0.80, 0.80, "人工校对", "人工"),
    ("具有读懂英文业务文件", 0.80, 0.80, "人工校对", "人工"),
]


def main():
    S = os.path.join(ROOT, "assets", "sample")
    st = json.load(io.open(os.path.join(S, "standards.json"), encoding="utf-8"))
    cfg = json.load(io.open(os.path.join(S, "majors.json"), encoding="utf-8"))
    abbr = {k: v["abbr"] for k, v in cfg.items()}

    rows = build_tasks.build(st, abbr)
    assert len(rows) == len(SCORES), "任务 %d 条，判定表 %d 条——请同步" % (len(rows), len(SCORES))

    for r, (pre, llm, robot, src, conf) in zip(rows, SCORES):
        assert r["task"].startswith(pre), \
            "顺序错位：任务为「%s」，判定表为「%s」" % (r["task"][:30], pre)
        r["llm"], r["robot"] = llm, robot
        r["quad"] = render.quad_of(llm, robot)
        r["src"], r["conf"], r["note"] = src, conf, NOTE

    out = os.path.join(S, "tasks.json")
    with io.open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)

    import collections
    c = collections.Counter(r["quad"] for r in rows)
    print("wrote %s ｜ %d 条 ｜ %s" % (out, len(rows), dict(c)))


if __name__ == "__main__":
    main()
