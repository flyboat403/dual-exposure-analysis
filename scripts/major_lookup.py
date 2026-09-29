# -*- coding: utf-8 -*-
"""教育部职业教育专业文档索引：只读查询。不写文件、不联网、不做任何判定。

两个索引，**按优先级回退**（都是**专业级**、6 位代码）：

| 顺序 | 文件 | 内容 | 条目 |
|---|---|---|---|
| ① | `assets/moe_major_index.json` | 《职业教育专业教学标准》（2025 版，每专业一份 PDF） | 579 |
| ② | `assets/moe_introduction_Vocational_Education_Majors.json` | 《职业教育专业简介（2022 年修订）》（每**专业类**一份 PDF，已展开为逐专业记录） | 1340 |

两份链接都指向 `www.moe.gov.cn`。

**回退为什么必要**：① 是部分覆盖，部分常见专业未收录（如 `710204 数字媒体技术应用`、
`700402 航空服务`）；② 覆盖 19 个专业大类 × 3 个层次共 275 个专业类、1340 个专业，能兜住这些缺口。
② 里同一专业类的所有专业**共用同一个 PDF 链接**（官方就是按类发布简介的）。

两者的差别在**文档版本与章节标题**：① 是 2025 版教学标准，用「培养规格」（(1)(2)…）；
② 是 2022 修订版简介，用「主要专业能力要求」（1. 2. …）——**两者都含职业面向与逐条能力要求**，
都可作为步骤 1 的输入，但引用时应声明版本差异。

用法：
    python scripts/major_lookup.py --search 汽车
    python scripts/major_lookup.py --show 700206          # ① 命中
    python scripts/major_lookup.py --show 710204          # ① 未收录 -> ② 命中
    python scripts/major_lookup.py --level 中等职业教育
    python scripts/major_lookup.py --stats
    python scripts/major_lookup.py --show 710204 --json
"""
import argparse
import collections
import io
import json
import os

_CACHE = {}

LEVELS = ["中等职业教育", "高等职业教育专科", "高等职业教育本科"]

SRC_STANDARD = "专业教学标准"
SRC_INTRO = "专业简介"

# 专业代码前 4 位是专业类代码（用于「未收录」时列出同专业类的候选）
CLASS_LEN = 4


def load(path):
    """读入索引（带缓存）。"""
    if path not in _CACHE:
        _CACHE[path] = json.load(io.open(path, encoding="utf-8"))
    return _CACHE[path]


def search(index, keyword):
    """按名称子串或代码前缀检索。返回记录列表（按代码升序）。"""
    k = keyword.strip()
    hits = [r for r in index
            if k in r["major_name"] or r["major_code"].startswith(k)]
    return sorted(hits, key=lambda r: r["major_code"])


def show(index, code):
    """按代码精确取一条；不存在返回 None。

    官方专业代码可能带后缀字母（如 `570101K`，K = 国家控制布点专业）。
    用不带后缀的 6 位数字查询时，按前缀匹配到带后缀的那条。
    """
    code = code.strip()
    for r in index:
        if r["major_code"] == code:
            return r
    if len(code) == 6 and code.isdigit():
        for r in index:
            c = r["major_code"]
            if len(c) > 6 and c.startswith(code):
                return r
    return None


def show_with_fallback(code, primary, intro):
    """先查专业教学标准索引，未收录则查专业简介索引。

    返回 (记录, 来源)；两处都没有则返回 (None, None)。
    """
    r = show(primary, code)
    if r:
        return r, SRC_STANDARD
    r = show(intro, code)
    if r:
        return r, SRC_INTRO
    return None, None


def siblings(code, intro):
    """同一专业类下的其它专业，供「未收录」时给出候选。"""
    cls = code.strip()[:CLASS_LEN]
    return [r for r in intro
            if r["major_code"].startswith(cls) and r["major_code"] != code.strip()]


def by_level(index, level):
    """按教育层次取全部记录。"""
    return sorted([r for r in index if r["education_level"] == level],
                  key=lambda r: r["major_code"])


def stats(index):
    """索引覆盖情况。"""
    c = collections.Counter(r["education_level"] for r in index)
    return {"total": len(index),
            "classes": len({r["major_code"][:CLASS_LEN] for r in index}),
            "by_level": {lv: c.get(lv, 0) for lv in LEVELS}}


def format_line(rec, source=None):
    """确认面板用的一行摘要（单行，便于对齐阅读）。"""
    tag = ("%s " % source).ljust(13) if source else ""
    cat = ("［%s］ " % rec["category"]) if rec.get("category") else ""
    return "%s%-8s %-22s %-9s %s%s" % (
        tag, rec["major_code"], rec["major_name"],
        rec["education_level"], cat, rec["pdf_url"])


def default_paths():
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "assets")
    return (os.path.join(root, "moe_major_index.json"),
            os.path.join(root, "moe_introduction_Vocational_Education_Majors.json"))


def main():
    ap = argparse.ArgumentParser(
        description="教育部职业教育专业文档索引查询"
                    "（专业教学标准 579 + 专业简介 1340，按优先级回退）")
    std_idx, intro_idx = default_paths()
    ap.add_argument("--index", default=std_idx, help="专业教学标准索引")
    ap.add_argument("--intro", default=intro_idx, help="专业简介索引（回退用）")
    ap.add_argument("--search", help="按名称子串或代码前缀检索")
    ap.add_argument("--show", help="按专业代码查询（未收录则回退到专业简介）")
    ap.add_argument("--level", choices=LEVELS, help="按教育层次列出")
    ap.add_argument("--source", choices=["all", "standard", "intro"], default="all",
                    help="限定检索哪个索引（默认 all）")
    ap.add_argument("--stats", action="store_true", help="显示两个索引的覆盖情况")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出（供程序消费）")
    a = ap.parse_args()

    wanted = ([a.index] if a.source == "intro" else
              [a.intro] if a.source == "standard" else [a.index, a.intro])
    for p in wanted:
        if not os.path.isfile(p):
            print("[错误] 找不到索引文件：%s" % p)
            raise SystemExit(1)

    prim = load(a.index) if a.source in ("all", "standard") else []
    intro = load(a.intro) if a.source in ("all", "intro") else []

    if a.stats:
        for name, idx in [(SRC_STANDARD, prim), (SRC_INTRO, intro)]:
            if not idx:
                continue
            s = stats(idx)
            print("%s：共 %d 个专业，覆盖 %d 个专业类" % (name, s["total"], s["classes"]))
            for lv in LEVELS:
                print("   %-14s %d" % (lv, s["by_level"][lv]))
        if prim and intro:
            ps = {r["major_code"] for r in prim}
            is_ = {r["major_code"] for r in intro}
            print("\n回退覆盖：① 的 %d 个专业中，%d 个也在 ② 里；仅 ① 有的 %d 个"
                  % (len(ps), len(ps & is_), len(ps - is_)))
        return

    if a.show:
        fell_back = False
        if a.source == "intro":
            r, src = show(intro, a.show), SRC_INTRO
        elif a.source == "standard":
            r, src = show(prim, a.show), SRC_STANDARD
        else:
            r, src = show_with_fallback(a.show, prim, intro)
            fell_back = (src == SRC_INTRO)
        if not r:
            print("未找到专业代码 %s。" % a.show)
            cand = siblings(a.show, intro) if intro else []
            if cand:
                print("该代码所属专业类（%s）下，专业简介索引收录了 %d 个专业："
                      % (a.show[:CLASS_LEN], len(cand)))
                for x in cand[:12]:
                    print("  " + format_line(x, SRC_INTRO))
            print("也可用 --search 按专业名称查找。")
            raise SystemExit(1)
        if a.json:
            print(json.dumps({"source": src, "record": r}, ensure_ascii=False, indent=1))
            return
        if fell_back:
            print("[%s] 未收录 %s。" % (SRC_STANDARD, a.show))
            print("[%s] 命中：该专业与其专业类下全部专业共用同一份简介 PDF。" % SRC_INTRO)
        print(format_line(r, src))
        return

    if a.search or a.level:
        if a.json:
            out = {}
            if prim:
                out[SRC_STANDARD] = search(prim, a.search) if a.search else by_level(prim, a.level)
            if intro:
                out[SRC_INTRO] = search(intro, a.search) if a.search else by_level(intro, a.level)
            print(json.dumps(out, ensure_ascii=False, indent=1))
            return
        for name, idx in [(SRC_STANDARD, prim), (SRC_INTRO, intro)]:
            if not idx:
                continue
            hits = search(idx, a.search) if a.search else by_level(idx, a.level)
            print("【%s】命中 %d 条：" % (name, len(hits)))
            for r in hits:
                print("  " + format_line(r, name))
            if not hits:
                print("  （无命中）")
        return

    for name, idx in [(SRC_STANDARD, prim), (SRC_INTRO, intro)]:
        if not idx:
            continue
        s = stats(idx)
        print("%s：%d 个专业（中职 %d / 高职专科 %d / 职教本科 %d），覆盖 %d 个专业类"
              % (name, s["total"], s["by_level"]["中等职业教育"],
                 s["by_level"]["高等职业教育专科"],
                 s["by_level"]["高等职业教育本科"], s["classes"]))
    print("用 --search <名称或代码前缀> / --show <专业代码> / --level <层次> 查询。")


if __name__ == "__main__":
    main()
