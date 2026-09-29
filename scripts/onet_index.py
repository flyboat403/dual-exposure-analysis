# -*- coding: utf-8 -*-
"""O*NET 客观指标索引：只读查询。不写文件、不联网、不做任何判定。

四个指标（均来自 O*NET 的 Importance 评分，构造见 assets/onet_ari.json 的 _meta）：
    ari          自动化可及性指数 = 常规侧 7 项工作活动均值 − 非常规侧 8 项均值
    pml          感知—操作负担 = Abilities 中 Psychomotor(10) + Physical(9) 的均值
    manual       常规手工分量（对应工业机器人等物理自动化）
    routine_cog  常规认知分量（对应规则化业务系统）

用法：
    python scripts/onet_index.py --search Automotive
    python scripts/onet_index.py --show 41-3041.00
    python scripts/onet_index.py --list            # 列出全部 896 个职业（长）
"""
import argparse
import io
import json
import os

_CACHE = {}


def load(path):
    """读入索引（带缓存）。path 指向 assets/onet_ari.json。"""
    if path not in _CACHE:
        _CACHE[path] = json.load(io.open(path, encoding="utf-8"))
    return _CACHE[path]


def lookup(index, soc):
    """按 SOC 取单条记录；不存在返回 None。"""
    return index["occupations"].get(soc)


def search(index, keyword):
    """按职业名关键词检索，返回 [(soc, title), ...]，按 SOC 升序。"""
    k = keyword.lower()
    return sorted(
        (s, r["title"]) for s, r in index["occupations"].items()
        if k in r["title"].lower()
    )


def percentile(index, key, value):
    """value 在全部 896 个职业的 key 指标中的百分位（0—100）。"""
    vals = sorted(r[key] for r in index["occupations"].values())
    n = sum(1 for v in vals if v <= value)
    return round(100.0 * n / len(vals), 1)


def format_line(index, soc):
    """确认面板用的一行摘要。

    映射环节把这个展示给使用者，让他们用 O*NET 指标反推候选职业是否真的对得上
    本校该专业的岗位群——这是"语义推断"之外的第二道校验。
    """
    r = index["occupations"].get(soc)
    if not r:
        return "未找到 %s" % soc
    return ("%-11s %-50s ARI %6.1f(%5.1f%%)  PML %5.1f(%5.1f%%)  "
            "常规手工 %5.1f  常规认知 %5.1f"
            % (soc, r["title"][:50], r["ari"], percentile(index, "ari", r["ari"]),
               r["pml"], percentile(index, "pml", r["pml"]),
               r["manual"], r["routine_cog"]))


def default_index_path():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "assets", "onet_ari.json")


def main():
    ap = argparse.ArgumentParser(description="O*NET 客观指标查询（896 个职业）")
    ap.add_argument("--index", default=default_index_path())
    ap.add_argument("--search", help="按职业名关键词检索 SOC")
    ap.add_argument("--show", help="显示某个 SOC 的完整指标")
    ap.add_argument("--list", action="store_true", help="列出全部职业")
    a = ap.parse_args()

    idx = load(a.index)
    n = idx["_meta"]["count"]

    if a.search:
        hits = search(idx, a.search)
        print("命中 %d 条（共 %d 个职业）：" % (len(hits), n))
        for s, _ in hits:
            print("  " + format_line(idx, s))
    elif a.show:
        r = lookup(idx, a.show)
        if not r:
            print("未找到 %s" % a.show)
            return
        print(json.dumps(r, ensure_ascii=False, indent=1))
        print()
        print(format_line(idx, a.show))
    elif a.list:
        for s in sorted(idx["occupations"]):
            print(format_line(idx, s))
    else:
        print("共 %d 个职业。用 --search / --show / --list 查询。" % n)


if __name__ == "__main__":
    main()
