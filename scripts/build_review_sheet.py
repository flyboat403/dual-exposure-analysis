# -*- coding: utf-8 -*-
"""任务表 → 教研组复核清单（Markdown + CSV + XLSX）。

本环节是判定质量的关键。一次真实运行的实践是：69 条任务里 42 条由教研组逐条人工判定，
其余 27 条沿用规则法结果——若跳过这一步，判定质量没有保障。

三条设计约束：
  · **编号冻结**：已判定条目保留原编号、留空位，绝不重排。使用者会跨多轮填写，
    一旦重排，他们手里的编号就再也对不上（2026-09-27 实际踩过这个坑）。
  · **只报真冲突**：「常规手工 + 交流」这类组合类型不构成冲突（组合里常规手工是
    主导），把它报出来只会制造噪声，让使用者疲于应付假问题。
  · **交付 xlsx 而非 csv**：`.csv` 是纯文本，**无法携带"数据有效性"（下拉列表）**，
    教研组只能手打取值，很容易与流水线取值不一致（多一个空格就对不上）。
    `.xlsx` 可以为「LLM 档」「自动化档」「类型修正」等列挂上下拉，属 Excel 工作簿特性。
    写入用自带的 `xlsx_min`（仅标准库），读回用 openpyxl。

用法：
    # 生成清单（md 人读 + xlsx 教研组填写）
    python scripts/build_review_sheet.py --tasks t.json \\
        --out-md sheet.md --out-xlsx sheet.xlsx
    # 需要扁平文本导出时再加 --out-csv sheet.csv（非默认，不供填写）

    # 教研组填完后读回，并回任务表
    python scripts/build_review_sheet.py --apply sheet.xlsx --tasks t.json --out t2.json
"""
import argparse
import collections
import csv
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import xlsx_min as xm  # noqa: E402

QORDER = ["Ⅰ 仅机器人高", "Ⅱ 双高", "Ⅲ 仅 LLM 高", "Ⅳ 双低", "待定"]
LEVELS = ["0.20", "0.55", "0.80"]
TYPES = ["常规手工", "非常规手工", "常规认知", "分析", "交流"]
CONF = 0.50


def quad_of(llm, robot):
    """与 render.quad_of 必须完全一致（自检里逐格比对）。"""
    hi_l, hi_r = llm >= CONF, robot >= CONF
    if hi_l and hi_r:
        return "Ⅱ 双高"
    if hi_r:
        return "Ⅰ 仅机器人高"
    if hi_l:
        return "Ⅲ 仅 LLM 高"
    return "Ⅳ 双低"


def conflict(r):
    """只判两类真冲突，返回提示文字；无冲突返回 None。"""
    types, quad = set(r.get("types") or []), r.get("quad")
    if quad in (None, "待定") or types == {"未分类"}:
        return None
    if "常规手工" in types and quad == "Ⅲ 仅 LLM 高":
        return "类型标为「常规手工」却判仅 LLM 高——是否应改为「分析」或「常规认知」？"
    if types in ({"交流"}, {"分析"}) and quad in ("Ⅰ 仅机器人高", "Ⅱ 双高"):
        return "类型仅标「%s」却判自动化侧高——是否应补「常规认知」？" % list(types)[0]
    return None


def build(rows):
    pending = [r for r in rows if r.get("quad") == "待定" or r.get("conf") == "待判定"]
    ids = {r["tid"] for r in pending}
    done = [r for r in rows if r["tid"] not in ids]
    confs = []
    for r in rows:
        why = conflict(r)
        if why:
            confs.append({"tid": r["tid"], "major": r["major"], "task": r["task"],
                          "types": r.get("types"), "quad": r.get("quad"), "why": why,
                          "llm": r.get("llm"), "robot": r.get("robot")})
    return {
        "pending": pending,
        "done": done,
        "conflicts": confs,
        "counts": {q: sum(1 for r in rows if r.get("quad") == q) for q in QORDER},
        "total": len(rows),
    }


def by_major_rows(res):
    """[专业, 条数, 象限分布, 跨象限]——Markdown 与 xlsx 共用。"""
    groups = collections.OrderedDict()
    for r in res["pending"] + res["done"]:
        groups.setdefault(r["major"], []).append(r)
    out = []
    for major, sub in groups.items():
        c = collections.Counter(r.get("quad") for r in sub)
        nq = len({q for q in c if q not in (None, "待定")})
        dist = "／".join("%s %d" % (q, c[q]) for q in QORDER if c.get(q))
        out.append([major, len(sub), dist,
                    "四象限全跨" if nq == 4 else ("跨 %d 象限" % nq if nq else "—")])
    return out


# ─────────────────────────── Markdown ───────────────────────────
def write_md(res, path, title="教研组复核清单"):
    L = ["# %s" % title, "",
         "> 共 %d 条任务 ｜ 待判定 %d 条 ｜ 已判定 %d 条 ｜ 类型冲突 %d 条"
         % (res["total"], len(res["pending"]), len(res["done"]), len(res["conflicts"])),
         ">",
         "> **编号冻结**：已判定条目保留原编号、留空位，不重排。",
         ">",
         "> **填写请用同名 `.xlsx`**：「LLM 档」「自动化档」是下拉列（0.20／0.55／0.80），"
         "选完「象限」自动算出；类型修正在紧随的两列。csv 是纯文本，带不了下拉，**不作为填写渠道**。",
         ""]

    L += ["## 一、待判定（%d 条）" % len(res["pending"]), ""]
    if res["pending"]:
        L += ["| 编号 | 专业 | 任务 | 任务类型 | 需再拆 | 并列段数 | LLM 档 | 自动化档 | 类型修正 | 理由 |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for r in res["pending"]:
            n = r.get("n_parts") or 1
            L.append("| %s | %s | %s | %s | %s | %s | | | | |"
                     % (r["tid"], r["major"], r["task"], "/".join(r.get("types") or []),
                        "⚠" if r.get("split_hint") else "",
                        "**%d**" % n if n >= 3 else n))
    else:
        L.append("（无待判定条目）")
    L.append("")
    L += ["", "> **列说明**：「需再拆 ⚠」＝该条已被切开但某一片仍跨 ≥2 个任务类型（R1b）。",
          "> 「并列段数」＝原能力条目按顿号／逗号／分号切出的片段数，**≥3 加粗**表示可能是复合条目"
          "（如「旅游景区、旅游电子商务、旅行社、定制旅行、导游、酒店服务」实际含 5 个岗位群的任务）。",
          "> 脚本不敢据此自动切——「款式、色彩、材料」同样是 3 段却只是一条任务。", ""]

    L += ["## 二、类型与象限冲突（%d 条）" % len(res["conflicts"]), ""]
    if res["conflicts"]:
        L += ["| 编号 | 专业 | 任务 | 现类型 | 现判定 | 提示 |",
              "|---|---|---|---|---|---|"]
        for r in res["conflicts"]:
            L.append("| %s | %s | %s | %s | %s | %s |"
                     % (r["tid"], r["major"], r["task"], "/".join(r["types"] or []),
                        r["quad"], r["why"]))
    else:
        L.append("（无冲突）")
    L.append("")

    L += ["## 三、象限分布", "", "| 象限 | 条数 |", "|---|---|"]
    for q in QORDER:
        L.append("| %s | %d |" % (q, res["counts"].get(q, 0)))
    L.append("")

    L += ["## 四、按专业", "", "| 专业 | 条数 | 象限分布 | 跨象限 |", "|---|---|---|---|"]
    for major, n, dist, span in by_major_rows(res):
        L.append("| %s | %d | %s | %s |" % (major, n, dist, span))
    L.append("")

    io.open(path, "w", encoding="utf-8").write("\n".join(L) + "\n")


# ─────────────────────────── CSV（可选导出，非默认）───────────────────────────
def write_csv(res, path):
    """扁平文本导出，列与 xlsx 对齐。**不供教研组填写**（无下拉，见 pitfalls 16）。"""
    with io.open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["分区", "编号", "专业", "教育层次", "任务", "任务类型", "需再拆",
                    "并列段数", "现判定", "LLM", "自动化", "冲突提示",
                    "LLM 档", "自动化档", "类型修正1", "类型修正2", "理由"])
        for r in res["pending"]:
            w.writerow(["待判定", r["tid"], r["major"], r.get("level", ""), r["task"],
                        "/".join(r.get("types") or []),
                        "需再拆" if r.get("split_hint") else "", r.get("n_parts") or 1,
                        r.get("quad"), "", "", "", "", "", "", "", ""])
        for r in res["conflicts"]:
            w.writerow(["类型冲突", r["tid"], r["major"], "", r["task"],
                        "/".join(r["types"] or []), "", "", r["quad"],
                        r.get("llm"), r.get("robot"), r["why"], "", "", "", "", ""])


# ─────────────────────────── XLSX（教研组实际填写用）───────────────────────────
def _lvl(v):
    """0.8 → '0.80'（与下拉选项一致）；None → ''。"""
    return "%.2f" % v if isinstance(v, (int, float)) else ""


def _quad_formula(r, cl, ca):
    """第 r 行的象限自动公式：两档都填了才出结果，否则「待定」。"""
    L, A = "%s%d" % (cl, r), "%s%d" % (ca, r)
    return ('=IF(OR(%s="",%s=""),"待定",'
            'IF(AND(%s+0>=0.5,%s+0>=0.5),"Ⅱ 双高",'
            'IF(%s+0>=0.5,"Ⅰ 仅机器人高",'
            'IF(%s+0>=0.5,"Ⅲ 仅 LLM 高","Ⅳ 双低"))))' % (L, A, L, A, A, L))


def write_xlsx(res, path, title="教研组复核清单"):
    wb = xm.Workbook()

    # ── 表 0：填写说明 ──
    g = wb.sheet("填写说明", freeze="A2", widths={"A": 18, "B": 104})
    g.row([title + " · 填写说明"], style="title")
    g.blank()
    g.row(["为什么是 xlsx"], style="bold")
    g.row(["", "csv 是纯文本，无法携带「数据有效性」（下拉列表），只能手打取值，"
               "很容易与流水线取值不一致（多一个空格就对不上）。本表的判定列都挂了下拉。"],
          styles=["wrap", "wrap"])
    g.blank()
    g.row(["编号冻结"], style="bold")
    g.row(["", "已判定条目保留原编号、留空位，绝不重排。请按「编号」列回填；"
               "不要插入／删除行、不要重编号——跨轮次填写时编号一旦变化就再也对不上。"],
          styles=["wrap", "wrap"])
    g.blank()
    g.row(["两张待填表"], style="bold")
    for a, b in [
        ("一、待判定", "尚未判定的条目。两档留空＝仍未判定。"),
        ("二、类型与象限冲突", "脚本认为「任务类型」与「象限判定」互相矛盾。两档已按现判定预填，"
                            "不改就留原样。"),
    ]:
        g.row([a, b], styles=["bold", "wrap"])
    g.blank()
    g.row(["怎么填"], style="bold")
    for i, t in enumerate([
        "① 「LLM 档」「自动化档」两列均从下拉选择（%s 低／%s 中／%s 高）。选好两档后，"
        "「象限」列会自动算出，用来对照核对。" % (LEVELS[0], LEVELS[1], LEVELS[2]),
        "② 若要修正任务类型，用「类型修正1／2」两列（下拉）。只改一个就只填第一列；"
        "第二个类型填在第二列（例如「常规手工」＋「交流」）。",
        "③ 「理由」列自由填写，建议写清判断依据（如：该能力是常规化的票据核对，非创意设计）。",
        "④ 不需要修改的行留空即可，不要删行、不要填「无」「同上」之类占位词。",
    ], 1):
        g.row(["", t], styles=["wrap", "wrap"])
    g.blank()
    g.row(["两轴与四象限"], style="bold")
    g.row(["象限", "含义"], style="header")
    for q, mean in [
        (QORDER[3], "两轴都低——生成式 AI 与自动化都不构成主要压力"),
        (QORDER[2], "只有生成式 AI 高——多为规则化的信息处理、文案与客服类任务"),
        (QORDER[0], "只有自动化高——多为常规化、重复性的物理操作"),
        (QORDER[1], "两轴都高——同一任务同时落入两类技术的射程"),
    ]:
        g.row([q, mean], styles=["center", "wrap"])
    g.blank()
    g.row(["档位含义"], style="bold")
    g.row(["档位", "含义"], style="header")
    g.row(["0.20", "低：当前技术基本够不着，或该任务的判断成分占主导"], styles=["num2", "wrap"])
    g.row(["0.55", "中：能承担一部分，仍需人主导"], styles=["num2", "wrap"])
    g.row(["0.80", "高：当前技术已能基本承担该任务的产出"], styles=["num2", "wrap"])
    g.blank()
    g.row(["回传"], style="bold")
    g.row(["", "填完后把本文件原样回传即可；编号不要改。任务表会按编号并回你的判定。"],
          styles=["wrap", "wrap"])
    g.blank()
    g.row(["数据与方法来源"], style="bold")
    g.row(["数据来源", "教育部《职业教育专业教学标准》；O*NET 职业数据库"
                     "（U.S. Department of Labor，CC BY 4.0）；《中华人民共和国职业分类大典》"
                     "（2022 年版，人力资源社会保障部）。"], styles=["bold", "wrap"])
    g.row(["方法学源头", "横轴：张丹丹等《中国人工智能技术暴露度的测算及其对劳动需求的影响》"
                     "《管理世界》2025 年第 7 期；纵轴口径：魏宏冰、李贺、马弘《工业机器人与结构性"
                     "就业变化》《世界经济》2025 年第 4 期。两篇为方法源头，非数据来源，"
                     "本表不使用其数值。"], styles=["bold", "wrap"])

    # ── 表 1：待判定 ──
    s1 = wb.sheet("一、待判定", freeze="A2",
                  widths={"A": 8, "B": 22, "C": 14, "D": 58, "E": 12, "F": 8, "G": 10,
                          "H": 10, "I": 12, "J": 16, "K": 12, "L": 12, "M": 40})
    s1.row(["编号", "专业", "教育层次", "任务", "脚本判定类型", "需再拆", "并列段数",
            "LLM 档", "自动化档", "象限（自动）", "类型修正1", "类型修正2", "理由"],
           style="header")
    r = 1
    for p in res["pending"]:
        r += 1
        n = p.get("n_parts") or 1
        s1.row([p["tid"], p["major"], p.get("level", ""), p["task"],
                "/".join(p.get("types") or []), "⚠" if p.get("split_hint") else "", n,
                p.get("llm"), p.get("robot"), None, None, None, None],
               styles=["center", "wrap", "center", "wrap", "center", "center", "center",
                       "num2", "num2", "wrap", "center", "center", "wrap"])
        s1.formula("J%d" % r, _quad_formula(r, "H", "I"))
    last = max(r, 2)
    s1.validate("H2:H%d" % (last + 40), LEVELS, title="LLM 档",
                msg="从下拉选择：0.20 低／0.55 中／0.80 高",
                error_title="取值不在档位内", error_msg="请从下拉列表中选择 0.20 / 0.55 / 0.80")
    s1.validate("I2:I%d" % (last + 40), LEVELS, title="自动化档",
                msg="从下拉选择：0.20 低／0.55 中／0.80 高",
                error_title="取值不在档位内", error_msg="请从下拉列表中选择 0.20 / 0.55 / 0.80")
    for col in ("K", "L"):
        s1.validate("%s2:%s%d" % (col, col, last + 40), TYPES, title="任务类型",
                    msg="从下拉选择（可按需留空）", error_title="取值不在类型表内",
                    error_msg="请从下拉列表中选择任务类型")

    # ── 表 2：类型与象限冲突（两档与类型按现判定预填）──
    s2 = wb.sheet("二、类型与象限冲突", freeze="A2",
                  widths={"A": 8, "B": 22, "C": 58, "D": 14, "E": 16, "F": 44, "G": 10,
                          "H": 12, "I": 16, "J": 12, "K": 12, "L": 40})
    s2.row(["编号", "专业", "任务", "现类型", "现判定", "冲突提示",
            "LLM 档", "自动化档", "象限（自动）", "类型修正1", "类型修正2", "理由"],
           style="header")
    r = 1
    for c in res["conflicts"]:
        r += 1
        ts = list(c.get("types") or [])
        t1 = ts[0] if ts and ts[0] in TYPES else None
        t2 = ts[1] if len(ts) > 1 and ts[1] in TYPES else None
        s2.row([c["tid"], c["major"], c["task"], "/".join(ts), c["quad"], c["why"],
                c.get("llm"), c.get("robot"), None, t1, t2, None],
               styles=["center", "wrap", "wrap", "center", "center", "wrap",
                       "num2", "num2", "wrap", "center", "center", "wrap"])
        s2.formula("I%d" % r, _quad_formula(r, "G", "H"))
    last = max(r, 2)
    for col, ttl in (("G", "LLM 档"), ("H", "自动化档")):
        s2.validate("%s2:%s%d" % (col, col, last + 20), LEVELS, title=ttl,
                    msg="已按现判定预填；不改就留原样",
                    error_title="取值不在档位内",
                    error_msg="请从下拉列表中选择 0.20 / 0.55 / 0.80")
    for col in ("J", "K"):
        s2.validate("%s2:%s%d" % (col, col, last + 20), TYPES, title="任务类型",
                    msg="已按现类型预填；不改就留原样", error_title="取值不在类型表内",
                    error_msg="请从下拉列表中选择任务类型")

    # ── 表 3、4：参考表 ──
    s3 = wb.sheet("三、象限分布", widths={"A": 18, "B": 10, "C": 60})
    s3.row(["象限", "条数", "说明"], style="header")
    s3.row([QORDER[3], res["counts"].get(QORDER[3], 0), "两轴都低于 %.2f" % CONF],
           styles=["center", "center", "wrap"])
    s3.row([QORDER[2], res["counts"].get(QORDER[2], 0), "生成式 AI 轴高于 %.2f，自动化轴低于" % CONF],
           styles=["center", "center", "wrap"])
    s3.row([QORDER[0], res["counts"].get(QORDER[0], 0), "自动化轴高于 %.2f，生成式 AI 轴低于" % CONF],
           styles=["center", "center", "wrap"])
    s3.row([QORDER[1], res["counts"].get(QORDER[1], 0), "两轴都高于 %.2f" % CONF],
           styles=["center", "center", "wrap"])
    s3.row([QORDER[4], res["counts"].get(QORDER[4], 0), "尚未判定"],
           styles=["center", "center", "wrap"])
    s3.blank()
    s3.row(["", "合计 %d 条" % res["total"]], styles=["wrap", "wrap"])

    s4 = wb.sheet("四、按专业", widths={"A": 24, "B": 8, "C": 46, "D": 14})
    s4.row(["专业", "条数", "象限分布", "跨象限"], style="header")
    for major, n, dist, span in by_major_rows(res):
        s4.row([major, n, dist, span], styles=["wrap", "center", "wrap", "center"])

    wb.save(path)
    return path


# ─────────────────────────── 读回（openpyxl）───────────────────────────
def read_xlsx(path):
    """读回教研组填写后的 xlsx。返回 {tid: {llm, robot, types, reason}}。

    按**表头名称**定位列（不依赖列序，教研组插列也不会错位）。
    """
    try:
        from openpyxl import load_workbook
    except ImportError:
        raise SystemExit("读回 xlsx 需要 openpyxl：pip install openpyxl\n"
                         "（生成 xlsx 不需要它；也可退回复核清单的 csv 走人工录入）")
    wb = load_workbook(path, data_only=False)
    out = {}
    for sheet, lcol, acol, t1col, t2col, rcol in (
            ("一、待判定", "LLM 档", "自动化档", "类型修正1", "类型修正2", "理由"),
            ("二、类型与象限冲突", "LLM 档", "自动化档", "类型修正1", "类型修正2", "理由")):
        if sheet not in wb.sheetnames:
            continue
        ws = wb[sheet]
        head = {}
        for c in ws[1]:
            if c.value:
                head[str(c.value).strip()] = c.column
        if "编号" not in head:
            continue
        need = {"编号", lcol, acol, t1col, t2col, rcol}
        miss = need - set(head)
        if miss:
            raise SystemExit("工作表「%s」缺少列：%s" % (sheet, "、".join(sorted(miss))))

        def cell(row, name):
            v = ws.cell(row=row, column=head[name]).value
            if isinstance(v, str):
                v = v.strip()
            return v

        for row in range(2, ws.max_row + 1):
            tid = cell(row, "编号")
            if not tid:
                continue
            tid = str(tid)
            lv, av = cell(row, lcol), cell(row, acol)
            e = {"llm": None, "robot": None, "types": None, "reason": ""}
            for key, v in (("llm", lv), ("robot", av)):
                if v is None or v == "":
                    continue
                try:
                    f = float(v)
                except (TypeError, ValueError):
                    raise SystemExit("编号 %s 的%s不是数字：%r" % (tid, key, v))
                if "%.2f" % f not in LEVELS:
                    raise SystemExit("编号 %s 的%s取值 %s 不在档位 %s 内"
                                     % (tid, key, v, "/".join(LEVELS)))
                e[key] = f
            ts = [cell(row, t1col), cell(row, t2col)]
            ts = [t for t in ts if t not in (None, "")]
            if ts:
                bad = [t for t in ts if t not in TYPES]
                if bad:
                    raise SystemExit("编号 %s 的类型取值不在类型表内：%s"
                                     % (tid, "、".join(map(str, bad))))
                e["types"] = ts
            rs = cell(row, rcol)
            e["reason"] = rs if rs else ""
            if e["llm"] is None and e["robot"] is None and e["types"] is None and not e["reason"]:
                continue
            out.setdefault(tid, e)
    return out


def apply_edits(rows, edits):
    """把填好的清单并回任务表。返回 (变更日志, 未知编号, 警告)。"""
    by_tid = {r["tid"]: r for r in rows}
    unknown = sorted(t for t in edits if t not in by_tid)
    log, warn = [], []
    for tid, e in edits.items():
        r = by_tid.get(tid)
        if r is None:
            continue
        before = (r.get("llm"), r.get("robot"), tuple(r.get("types") or []), r.get("quad"))
        if e["llm"] is not None:
            r["llm"] = e["llm"]
        if e["robot"] is not None:
            r["robot"] = e["robot"]
        if e["types"]:
            r["types"] = list(e["types"])
        if r.get("llm") is None or r.get("robot") is None:
            if e["llm"] is not None or e["robot"] is not None:
                warn.append("%s：只填了一个档位，无法算出象限，仍为待定" % tid)
        else:
            r["quad"] = quad_of(r["llm"], r["robot"])
        if e["reason"]:
            r["note"] = ((r.get("note") or "").rstrip() + " ｜ 教研组：" + e["reason"]).strip(" ｜")
        r["src"], r["conf"] = "教研组", "教研组"
        after = (r.get("llm"), r.get("robot"), tuple(r.get("types") or []), r.get("quad"))
        if before != after:
            log.append("%s：%s/%s %s → %s/%s %s"
                       % (tid, _lvl(before[0]) or "—", _lvl(before[1]) or "—",
                          before[2] or "—", _lvl(after[0]) or "—", _lvl(after[1]) or "—",
                          after[3]))
    return log, unknown, warn


def main():
    samples = ["assets", "sample", "tasks.json"]
    here = os.path.dirname(HERE)
    ap = argparse.ArgumentParser(description="任务表 → 教研组复核清单")
    ap.add_argument("--tasks", default=os.path.join(here, *samples))
    ap.add_argument("--out-md", help="Markdown 清单（人读／可打印）")
    ap.add_argument("--out-csv", help="可选的 CSV 扁平导出（纯文本、无下拉，"
                                      "不供教研组填写；不给则不产出）")
    ap.add_argument("--out-xlsx", help="Excel 清单（教研组填写用，带下拉）；"
                                      "未给且给了 --out-md 时，自动取同名 .xlsx")
    ap.add_argument("--apply", help="读回教研组填写后的 xlsx")
    ap.add_argument("--out", help="--apply 时的输出任务表（默认 <tasks>.reviewed.json）")
    a = ap.parse_args()

    if a.apply:
        rows = json.load(io.open(a.tasks, encoding="utf-8"))
        edits = read_xlsx(a.apply)
        log, unknown, warn = apply_edits(rows, edits)
        out = a.out or (os.path.splitext(a.tasks)[0] + ".reviewed.json")
        io.open(out, "w", encoding="utf-8").write(
            json.dumps(rows, ensure_ascii=False, indent=1))
        print("读回 %d 条填写 ｜ 实际变更 %d 条" % (len(edits), len(log)))
        for line in log[:20]:
            print("   " + line)
        if len(log) > 20:
            print("   … 还有 %d 条" % (len(log) - 20))
        for w in warn:
            print("   [警告] " + w)
        for u in unknown:
            print("   [忽略] 编号 %s 不在任务表中（编号冻结：不得新增编号）" % u)
        print("wrote %s" % out)
        return

    xlsx = a.out_xlsx
    if not xlsx and a.out_md:
        xlsx = os.path.splitext(a.out_md)[0] + ".xlsx"

    rows = json.load(io.open(a.tasks, encoding="utf-8"))
    res = build(rows)

    for p in (a.out_md, a.out_csv, xlsx):
        if p:
            d = os.path.dirname(os.path.abspath(p))
            if d:
                os.makedirs(d, exist_ok=True)
    if a.out_md:
        write_md(res, a.out_md)
    if a.out_csv:
        write_csv(res, a.out_csv)
    if xlsx:
        write_xlsx(res, xlsx)

    print("待判定 %d ｜ 已判定 %d ｜ 类型冲突 %d ｜ 合计 %d"
          % (len(res["pending"]), len(res["done"]), len(res["conflicts"]), res["total"]))
    print("象限：" + "  ".join("%s %d" % (q, res["counts"][q]) for q in QORDER if res["counts"][q]))
    wrote = [p for p in (a.out_md, a.out_csv, xlsx) if p]
    print("wrote " + "\n      ".join(wrote))
    if xlsx:
        print("      教研组请填 %s（两档为下拉列；csv 是可选导出，不供填写）"
              % os.path.basename(xlsx))


if __name__ == "__main__":
    main()
