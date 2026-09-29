# -*- coding: utf-8 -*-
"""自检：专业文档索引查询（major_lookup）——含「标准未收录 → 回退专业简介」。

运行：python scripts/_selftest_major_lookup.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import major_lookup as ml  # noqa: E402

A = os.path.join(ROOT, "assets")
STD = os.path.join(A, "moe_major_index.json")
INTRO = os.path.join(A, "moe_introduction_Vocational_Education_Majors.json")


def check_index(path, want_total, want_levels, want_classes):
    assert os.path.isfile(path), "索引文件缺失：%s" % path
    idx = ml.load(path)
    name = os.path.basename(path)
    assert len(idx) == want_total, "%s 应为 %d 条，实为 %d" % (name, want_total, len(idx))

    for r in idx:
        for k in ("major_code", "major_name", "education_level", "pdf_url"):
            assert r.get(k), "%s 记录缺字段 %s：%s" % (name, k, r)
        assert re.match(r"^\d{6}[A-Z]?$", r["major_code"]), \
            "%s 的代码应为 6 位数字（可带 1 个后缀字母）：%s" % (name, r["major_code"])
        assert "moe.gov.cn" in r["pdf_url"], "%s 的 pdf_url 非教育部官网：%s" % (name, r["pdf_url"])

    codes = [r["major_code"] for r in idx]
    assert len(codes) == len(set(codes)), "%s 代码有重复" % name

    s = ml.stats(idx)
    assert s["total"] == want_total
    assert s["classes"] == want_classes, "%s 专业类数应为 %d，实为 %d" % (
        name, want_classes, s["classes"])
    for lv, n in want_levels.items():
        assert s["by_level"][lv] == n, "%s %s 应为 %d，实为 %d" % (
            name, lv, n, s["by_level"][lv])
    assert sum(s["by_level"].values()) == want_total
    return idx


def main():
    # ── ① 专业教学标准索引：579 个专业
    std = check_index(
        STD, 579,
        {"中等职业教育": 201, "高等职业教育专科": 316, "高等职业教育本科": 62}, 202)

    # ── ② 专业简介索引：1340 个专业（按专业类展开，6 位代码）
    intro = check_index(
        INTRO, 1340,
        {"中等职业教育": 356, "高等职业教育专科": 744, "高等职业教育本科": 240}, 275)
    for r in intro:
        assert r.get("category"), "专业简介记录缺 category（专业大类）：%s" % r
    assert len({r["category"] for r in intro}) == 19, "专业简介应覆盖 19 个专业大类"
    # 同一专业类共用一份 PDF
    urls = {r["pdf_url"] for r in intro}
    assert len(urls) == 275, "专业简介的 PDF 去重后应为 275 份，实为 %d" % len(urls)

    # ── ③ 检索
    hits = ml.search(std, "汽车")
    assert len(hits) >= 5 and "700206" in {r["major_code"] for r in hits}
    assert hits == sorted(hits, key=lambda r: r["major_code"]), "结果应按代码升序"
    assert ml.search(std, "7004"), "代码前缀检索应有结果"
    assert len(ml.search(intro, "汽车")) >= 5

    # ── ④ 精确查询 + 代码后缀容忍（官方有 9 个带 K 后缀的）
    r = ml.show(std, "700206")
    assert r and r["major_name"] == "汽车运用与维修", r
    assert ml.show(std, "999999") is None
    ksuf = [x for x in std if re.match(r"^\d{6}[A-Z]$", x["major_code"])]
    assert len(ksuf) == 9, "带后缀的代码应为 9 个，实为 %d" % len(ksuf)
    rk = ml.show(std, ksuf[0]["major_code"][:6])
    assert rk and rk["major_code"] == ksuf[0]["major_code"], rk

    # ── ⑤ 回退：标准索引命中时不回退
    rec, src = ml.show_with_fallback("700206", std, intro)
    assert src == ml.SRC_STANDARD and rec["major_name"] == "汽车运用与维修", (src, rec)

    # ── ⑥ 回退：标准未收录 -> 专业简介（精确命中，非前缀）
    for major, name in [("710204", "数字媒体技术应用"), ("700402", "航空服务"),
                        ("610118", "休闲农业生产与经营"), ("750110", "美发与形象设计")]:
        assert ml.show(std, major) is None, "%s 本应不在标准索引中" % major
        assert ml.show(intro, major) is not None, "%s 应在专业简介索引中" % major
        rec, src = ml.show_with_fallback(major, std, intro)
        assert src == ml.SRC_INTRO, "%s 应回退到专业简介，实为 %s" % (major, src)
        assert rec["major_name"] == name, (major, rec["major_name"])
        assert "moe.gov.cn" in rec["pdf_url"]

    # ── ⑦ 同一专业类共用 PDF
    n = [r for r in intro if r["major_code"].startswith("7102")]
    assert len(n) >= 8 and len({r["pdf_url"] for r in n}) == 1, \
        "7102 计算机类的专业应共用一份 PDF"

    # ── ⑧ 两处都没有 -> 不返回；但能给出同专业类候选
    rec, src = ml.show_with_fallback("710299", std, intro)
    assert rec is None and src is None
    sib = ml.siblings("710299", intro)
    assert len(sib) >= 8 and all(x["major_code"].startswith("7102") for x in sib), sib

    # ── ⑨ 按层次
    zz = ml.by_level(intro, "中等职业教育")
    assert len(zz) == 356 and all(x["education_level"] == "中等职业教育" for x in zz)

    # ── ⑩ format_line 单行且含关键字段
    line = ml.format_line(ml.show(std, "700206"), ml.SRC_STANDARD)
    assert "\n" not in line, "format_line 应为单行"
    for token in ("700206", "汽车运用与维修", "中等职业教育", "http", ml.SRC_STANDARD):
        assert token in line, "format_line 缺 %s：%s" % (token, line)

    # ── ⑪ 回退覆盖面：① 的专业绝大多数也在 ② 里
    ps = {r["major_code"] for r in std}
    is_ = {r["major_code"] for r in intro}
    only_std = sorted(ps - is_)
    print("OK: ① 教学标准 %d 个专业 / %d 个类；② 专业简介 %d 个专业 / %d 个类"
          % (len(std), len({r["major_code"][:4] for r in std}),
             len(intro), len({r["major_code"][:4] for r in intro})))
    print("    回退覆盖：① 的 %d 个专业中 %d 个也在 ② 里，仅 ① 有的 %d 个 %s"
          % (len(ps), len(ps & is_), len(only_std), only_std if only_std else ""))
    print("    回退验证：710204 数字媒体技术应用 ｜ 700402 航空服务 ｜ "
          "750110 美发与形象设计 ｜ 610118 休闲农业生产与经营")
    print("    同专业类共用 PDF：7102 计算机类下 %d 个专业 -> 1 份 PDF" % len(n))


if __name__ == "__main__":
    main()
