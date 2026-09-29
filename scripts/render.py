# -*- coding: utf-8 -*-
"""任务表 → 四张图 + 一份自包含 HTML 报告。

四张图（按论文出现顺序编号）：
    1. contrast.png        专业层 vs 任务层对照——用图形说明"专业层均值丢掉了什么"
    2. structure_<专业>.png  指定专业的任务结构图（底色＝象限，横条＝两侧暴露度）
    3. matrix.png          任务层象限分布矩阵（3×3，格内列任务编号与条数）
    4. shift.png           分析单位下移示意

**图一律在任务层展开。** 除第 1 张的对照图外，不以专业层均值作图——本方法的核心
主张就是"专业层的单一分数会掩盖专业内部的任务异质性"，在专业层作图等于自相矛盾。

HTML 报告把四张图以 base64 内嵌，保证断网打开与内置预览都能显示。

用法：
    python scripts/render.py --tasks <tasks.json> --majors <majors.json> --outdir <dir>
    python scripts/render.py --tasks ... --only figures
"""
import argparse
import base64
import collections
import io
import json
import os
import random

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402

# 中文字体候选：Windows / macOS / Linux 各取常见者，缺字体时降级并提示
FONT_CANDIDATES = ["Microsoft YaHei", "SimHei", "PingFang SC", "Heiti SC",
                   "Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Zen Hei",
                   "DejaVu Sans"]
plt.rcParams["font.sans-serif"] = FONT_CANDIDATES
plt.rcParams["axes.unicode_minus"] = False

# 两轴取值固定为三档，分界 0.50。
# 注意：LEVELS 的顺序必须与刻度标签的顺序严格一致——曾因两者不一致导致两轴整体反向。
LEVELS = [0.20, 0.55, 0.80]
LEVEL_LABELS = ["0.20", "0.55", "0.80"]
CUT = 0.50

QORDER = ["Ⅰ 仅机器人高", "Ⅱ 双高", "Ⅲ 仅 LLM 高", "Ⅳ 双低", "待定"]
QCOL = {"Ⅰ 仅机器人高": "#DCE6F0", "Ⅱ 双高": "#F3D9DC",
        "Ⅲ 仅 LLM 高": "#E4EFE2", "Ⅳ 双低": "#F2EFE4", "待定": "#EFEFEF"}


def quad_of(llm, robot):
    """由两侧分数反推象限。用于与任务表里的 quad 字段交叉核对。"""
    if llm is None or robot is None:
        return "待定"
    if llm >= CUT and robot >= CUT:
        return "Ⅱ 双高"
    if robot >= CUT:
        return "Ⅰ 仅机器人高"
    if llm >= CUT:
        return "Ⅲ 仅 LLM 高"
    return "Ⅳ 双低"


def quad_counts(rows):
    """按分数反推的象限计数。出图后必须与任务表的 quad 字段核对，防止轴序写反。"""
    return collections.Counter(quad_of(r["llm"], r["robot"]) for r in rows)


def _major_order(rows, cfg):
    order = [m for m in cfg if any(r["major"] == m for r in rows)]
    for r in rows:
        if r["major"] not in order:
            order.append(r["major"])
    return order


def _check_font():
    from matplotlib.font_manager import findfont, FontProperties
    for name in FONT_CANDIDATES:
        try:
            p = findfont(FontProperties(family=name), fallback_to_default=False)
            if p:
                return name
        except Exception:
            continue
    print("[警告] 未找到中文字体，图中中文可能显示为方框。"
          "请安装 Microsoft YaHei / SimHei / Noto Sans CJK SC 之一。")
    return None


def fig_contrast(rows, cfg, outdir):
    """图 1：专业层 vs 任务层对照。"""
    majors = _major_order(rows, cfg)
    fig, axes = plt.subplots(1, 2, figsize=(13.6, 6.2), sharex=True, sharey=True)

    ax = axes[0]
    ax.axvline(CUT, color="#8A8A8A", lw=1.2, ls="--")
    ax.axhline(CUT, color="#8A8A8A", lw=1.2, ls="--")
    off = [(11, 6, "left"), (11, -16, "left"), (-11, 6, "right"), (-11, -16, "right")]
    tbl = ["专业层均值（LLM 暴露度, 自动化替代暴露度）"]
    for i, m in enumerate(majors):
        sub = [r for r in rows if r["major"] == m]
        mx = sum(r["llm"] for r in sub) / len(sub)
        my = sum(r["robot"] for r in sub) / len(sub)
        ax.scatter([mx], [my], s=190, c=cfg[m]["color"], edgecolors="white",
                   linewidths=1.3, zorder=3)
        dx, dy, ha = off[i % 4]
        ax.annotate(m, (mx, my), textcoords="offset points", xytext=(dx, dy),
                    fontsize=8.8, color="#333333", ha=ha)
        tbl.append("%s  (%.2f, %.2f)" % (m, mx, my))
    ax.text(0.015, 1.055, "\n".join(tbl), transform=ax.transData, fontsize=8.6,
            color="#333333", va="top", ha="left", linespacing=1.45,
            bbox=dict(boxstyle="round,pad=0.42", fc="white", ec="#CCCCCC", alpha=0.94))
    ax.set_xlim(-0.06, 1.12)
    ax.set_ylim(-0.06, 1.12)
    ax.set_xticks([0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0])
    ax.set_yticks([0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0])
    ax.tick_params(labelsize=10.5)
    ax.grid(alpha=0.2, ls=":")
    ax.set_title("（a）专业层：每个专业一个均值 → 全部挤在中部", fontsize=13)
    ax.set_xlabel("生成式人工智能（LLM）暴露度", fontsize=12)
    ax.set_ylabel("自动化替代暴露度", fontsize=12)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    ax = axes[1]
    ax.axvline(CUT, color="#8A8A8A", lw=1.2, ls="--")
    ax.axhline(CUT, color="#8A8A8A", lw=1.2, ls="--")
    rng = random.Random(20260929)
    for m in majors:
        sub = [r for r in rows if r["major"] == m]
        xs = [r["llm"] + rng.uniform(-0.025, 0.025) for r in sub]
        ys = [r["robot"] + rng.uniform(-0.025, 0.025) for r in sub]
        ax.scatter(xs, ys, s=95, c=cfg[m]["color"], edgecolors="white",
                   linewidths=1.0, alpha=0.88, label=m, zorder=3)
    ax.set_xticks([0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0])
    ax.set_yticks([0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0])
    ax.tick_params(labelsize=10.5)
    ax.grid(alpha=0.2, ls=":")
    ax.set_title("（b）任务层：%d 条任务 → 四象限全部铺开" % len(rows), fontsize=13)
    ax.set_xlabel("生成式人工智能（LLM）暴露度", fontsize=12)
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=9.2, frameon=False)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    fig.suptitle("图 1　同一批数据在两种分析单位下的面貌", fontsize=14, y=1.00)
    plt.tight_layout()
    p = os.path.join(outdir, "contrast.png")
    plt.savefig(p, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return p


def fig_structure(rows, cfg, outdir, major):
    """图 2：单个专业的任务结构图。"""
    sub = [r for r in rows if r["major"] == major][::-1]
    if not sub:
        return None
    fig, ax = plt.subplots(figsize=(9.4, max(3.2, 0.52 * len(sub) + 1.8)))
    ys = list(range(len(sub)))
    for i, r in zip(ys, sub):
        ax.axhspan(i - 0.45, i + 0.45, color=QCOL.get(r["quad"], "#EFEFEF"),
                   alpha=0.9, zorder=0)
    ax.barh([i + 0.16 for i in ys], [r["llm"] for r in sub], height=0.30,
            color="#B23A48", alpha=0.88, zorder=3, label="LLM 暴露度")
    ax.barh([i - 0.16 for i in ys], [r["robot"] for r in sub], height=0.30,
            color="#2E6E8E", alpha=0.88, zorder=3, label="自动化替代暴露度")
    labs = []
    for r in sub:
        t = r["task"].replace("具有", "").replace("具备", "").replace("的能力", "")
        labs.append("%s（%s）" % (r["tid"], t[:22]))
    ax.set_yticks(ys)
    ax.set_yticklabels(labs, fontsize=9.4)
    ax.set_xlim(0, 1.0)
    ax.set_xticks([0, 0.2, 0.5, 0.8, 1.0])
    ax.tick_params(axis="x", labelsize=10)
    ax.axvline(CUT, color="#8A8A8A", lw=1.0, ls="--", zorder=2)
    ax.set_title("%s 的任务结构（底色＝象限）" % major, fontsize=12.5)
    ax.grid(axis="x", alpha=0.2, ls=":")
    ax.legend(loc="lower right", fontsize=9.6, framealpha=0.9)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    plt.tight_layout()
    p = os.path.join(outdir, "structure_%s.png" % cfg[major]["abbr"])
    plt.savefig(p, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return p


def fig_matrix(rows, cfg, outdir):
    """图 3：任务层象限分布矩阵（3×3，格内列任务编号与条数）。"""
    cells = collections.defaultdict(list)
    for r in rows:
        cells[(r["llm"], r["robot"])].append(r["tid"])

    fig, ax = plt.subplots(figsize=(11.8, 8.6))
    ax.set_xlim(-0.78, 2.78)
    ax.set_ylim(-1.02, 3.02)
    ax.set_xticks(range(3))
    ax.set_yticks(range(3))
    ax.set_xticklabels(LEVEL_LABELS, fontsize=13)
    ax.set_yticklabels(LEVEL_LABELS, fontsize=13)
    ax.set_xlabel("生成式人工智能（LLM）暴露度", fontsize=13.5, labelpad=8)
    ax.set_ylabel("自动化替代暴露度", fontsize=13.5, labelpad=8)
    ax.set_title("图 3　%d 条任务的象限分布\n（格内为任务编号，左上角为该格条数）" % len(rows),
                 fontsize=13, pad=14)
    ax.set_xticks([i - 0.5 for i in range(4)], minor=True)
    ax.set_yticks([i - 0.5 for i in range(4)], minor=True)
    ax.grid(which="minor", color="#8A8A8A", lw=1.2)
    ax.tick_params(which="minor", length=0)
    ax.tick_params(axis="both", length=0)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_bounds(-0.5, 2.5)
    ax.spines["left"].set_bounds(-0.5, 2.5)

    for (lx, ly), tids in cells.items():
        if lx not in LEVELS or ly not in LEVELS:
            continue
        xi, yi = LEVELS.index(lx), LEVELS.index(ly)
        n = len(tids)
        ax.add_patch(Rectangle((xi - 0.5, yi - 0.5), 1, 1, fc="#3D6B8E",
                               alpha=min(0.08 + 0.026 * n, 0.50), ec="none", zorder=0))
        per = 4 if n > 12 else 5
        lines, cur = [], ""
        for w in tids:
            if cur and len(cur.split()) >= per:
                lines.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        if cur:
            lines.append(cur)
        fs = 10.6 if n <= 8 else (9.6 if n <= 14 else 8.9)
        ax.text(xi - 0.44, yi + 0.42, "%d 条" % n, ha="left", va="top",
                fontsize=11.5, color="#17384F", fontweight="bold", zorder=3)
        ax.text(xi, yi - 0.06, "\n".join(lines), ha="center", va="center",
                fontsize=fs, color="#1A1A1A", linespacing=1.65, zorder=3)

    for t, x, y in [("Ⅰ 仅自动化高", 0.5, 2.80), ("Ⅱ 双高", 1.5, 2.80),
                    ("Ⅳ 双低", 0.5, -0.82), ("Ⅲ 仅生成式AI高", 1.5, -0.82)]:
        ax.text(x, y, t, ha="center", va="center", fontsize=13.5, color="#444444")
    plt.tight_layout()
    p = os.path.join(outdir, "matrix.png")
    plt.savefig(p, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return p


def fig_shift(outdir):
    """图 4：分析单位下移示意。"""
    fig, ax = plt.subplots(figsize=(10.2, 5.4))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5.4)
    ax.axis("off")

    def box(x, y, w, h, text, fc, ec, fs=11.5, tc="#222222"):
        ax.add_patch(FancyBboxPatch((x, y), w, h,
                                    boxstyle="round,pad=0.10,rounding_size=0.14",
                                    fc=fc, ec=ec, lw=1.4))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
                fontsize=fs, color=tc)

    ax.text(0.15, 4.85, "（一）现行做法：以“专业”为分析单位", fontsize=13, color="#555555")
    box(0.35, 3.55, 2.5, 1.0, "专业\n（一个风险分数）", "#EFEFEF", "#9A9A9A", 12)
    ax.add_patch(FancyArrowPatch((2.95, 4.05), (4.15, 4.05), arrowstyle="-|>",
                                 mutation_scale=18, color="#8A8A8A", lw=1.6))
    box(4.25, 3.55, 2.5, 1.0, "排序 / 红黄牌", "#EFEFEF", "#9A9A9A", 12)
    ax.text(6.95, 4.05, "→ 只能回答“调不调”，\n    不能回答“调什么”",
            fontsize=11.5, color="#7A3B3B", va="center")

    ax.text(0.15, 3.05, "（二）本文做法：以“任务”为分析单位", fontsize=13, color="#555555")
    for i, (t, c) in enumerate([("Ⅰ 仅自动化高", QCOL["Ⅰ 仅机器人高"]),
                                ("Ⅱ 双高", QCOL["Ⅱ 双高"]),
                                ("Ⅲ 仅生成式AI高", QCOL["Ⅲ 仅 LLM 高"]),
                                ("Ⅳ 双低", QCOL["Ⅳ 双低"])]):
        box(0.35 + i * 1.72, 1.85, 1.55, 0.85, t, c, "#8A8A8A", 10.5)
    ax.text(7.55, 2.27, "← 同一专业的任务\n     分属四个象限",
            fontsize=11.5, color="#2F5D3A", va="center")
    ax.add_patch(FancyArrowPatch((3.7, 1.72), (3.7, 1.28), arrowstyle="-|>",
                                 mutation_scale=16, color="#4C7FA8", lw=1.6))
    box(1.35, 0.35, 4.7, 0.85, "同一专业：重配任务权重（而非更换专业）",
        "#FFFFFF", "#4C7FA8", 12, "#1F4E6B")
    ax.text(6.35, 0.77, "→ 能回答“调什么、怎么调”", fontsize=11.5, color="#1F4E6B",
            va="center")
    plt.tight_layout()
    p = os.path.join(outdir, "shift.png")
    plt.savefig(p, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return p


def figures(rows, cfg, outdir, focus_majors=None):
    """产出全部图，返回文件路径列表。focus 未指定时自动取跨象限最多的专业。"""
    os.makedirs(outdir, exist_ok=True)
    _check_font()
    if not focus_majors:
        ranked = sorted(_major_order(rows, cfg),
                        key=lambda m: -len({r["quad"] for r in rows
                                            if r["major"] == m and r["quad"] != "待定"}))
        focus_majors = ranked[:2]
    out = [fig_contrast(rows, cfg, outdir), fig_matrix(rows, cfg, outdir), fig_shift(outdir)]
    for m in focus_majors:
        p = fig_structure(rows, cfg, outdir, m)
        if p:
            out.insert(1, p)
    return [p for p in out if p]


def _b64(path):
    return "data:image/png;base64," + base64.b64encode(
        io.open(path, "rb").read()).decode()


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def html(rows, cfg, outdir, school="某职业学校", focus_majors=None, title=None):
    """生成自包含 HTML 报告（图片 base64 内嵌，断网可看）。"""
    os.makedirs(outdir, exist_ok=True)
    fig_paths = figures(rows, cfg, outdir, focus_majors)
    by_name = {os.path.basename(p): p for p in fig_paths}
    tpl = io.open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "assets", "templates", "report.html.j2"), encoding="utf-8").read()

    majors = _major_order(rows, cfg)
    cnt = collections.Counter(r["quad"] for r in rows)
    rows_html = []
    for m in majors:
        sub = [r for r in rows if r["major"] == m]
        c = collections.Counter(r["quad"] for r in sub)
        nq = len({q for q in c if q != "待定"})
        dist = "／".join("%s %d" % (q.split()[0], c[q]) for q in QORDER if c.get(q))
        quad = ("<b class='hl'>四象限全跨</b>" if nq == 4 else
                ("跨 %d 象限" % nq if nq else "—"))
        rows_html.append(
            "<tr><td>%s</td><td class='c'>%s</td><td class='c'>%d</td>"
            "<td class='c'>%s</td><td class='c'>%s</td></tr>"
            % (_esc(m), _esc(cfg[m]["level"]), len(sub), quad, dist))

    struct_imgs = "".join(
        "<figure><img src='%s' alt='%s 任务结构'><figcaption>%s 的逐条任务数据。"
        "底色为该任务所属象限，横条为两侧暴露度。</figcaption></figure>"
        % (_b64(p), _esc(m), _esc(m))
        for m in (focus_majors or [])
        for p in [os.path.join(outdir, "structure_%s.png" % cfg[m]["abbr"])]
        if os.path.isfile(p)
    )

    repl = {
        "__SCHOOL__": _esc(school),
        "__TITLE__": _esc(title or "任务层双暴露度分析"),
        "__TOTAL__": str(len(rows)),
        "__N_MAJOR__": str(len(majors)),
        "__N_SPAN__": str(sum(1 for m in majors if len(
            {r["quad"] for r in rows if r["major"] == m and r["quad"] != "待定"}) >= 2)),
        "__N_FOUR__": str(sum(1 for m in majors if len(
            {r["quad"] for r in rows if r["major"] == m and r["quad"] != "待定"}) == 4)),
        "__N_PENDING__": str(cnt.get("待定", 0)),
        "__C_I__": str(cnt.get("Ⅰ 仅机器人高", 0)),
        "__C_II__": str(cnt.get("Ⅱ 双高", 0)),
        "__C_III__": str(cnt.get("Ⅲ 仅 LLM 高", 0)),
        "__C_IV__": str(cnt.get("Ⅳ 双低", 0)),
        "__FIG_CONTRAST__": _b64(by_name["contrast.png"]),
        "__FIG_MATRIX__": _b64(by_name["matrix.png"]),
        "__FIG_SHIFT__": _b64(by_name["shift.png"]),
        "__FIG_STRUCT__": struct_imgs,
        "__MAJOR_ROWS__": "".join(rows_html),
    }
    for k, v in repl.items():
        tpl = tpl.replace(k, v)
    p = os.path.join(outdir, "report.html")
    io.open(p, "w", encoding="utf-8").write(tpl)
    return p


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description="任务表 → 四图 + HTML 报告")
    ap.add_argument("--tasks", default=os.path.join(here, "assets", "sample", "tasks.json"))
    ap.add_argument("--majors", default=os.path.join(here, "assets", "sample", "majors.json"))
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--school", default="某职业学校")
    ap.add_argument("--focus", help="要画任务结构图的专业，逗号分隔（默认自动取跨象限最多者）")
    ap.add_argument("--only", choices=["figures", "html"], help="只出图或只出 HTML")
    a = ap.parse_args()

    rows = json.load(io.open(a.tasks, encoding="utf-8"))
    cfg = json.load(io.open(a.majors, encoding="utf-8"))
    focus = [s.strip() for s in a.focus.split(",")] if a.focus else None

    # 轴序校验：按分数反推的象限必须与任务表里的 quad 一致
    got, want = quad_counts(rows), collections.Counter(r["quad"] for r in rows)
    if got != want:
        print("[错误] 象限不一致——按分数反推为 %s，任务表记为 %s。"
              "请检查 LEVELS 顺序是否与刻度标签一致。" % (dict(got), dict(want)))
        raise SystemExit(1)

    if a.only == "figures":
        for p in figures(rows, cfg, a.outdir, focus):
            print("wrote %s" % p)
    elif a.only == "html":
        print("wrote %s" % html(rows, cfg, a.outdir, a.school, focus))
    else:
        print("wrote %s" % html(rows, cfg, a.outdir, a.school, focus))


if __name__ == "__main__":
    main()
