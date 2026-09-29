# -*- coding: utf-8 -*-
"""自检：拆解规则 R1 / R1a / R1b + R2—R5 的行为。

运行：python scripts/_selftest_build_tasks.py
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import build_tasks  # noqa: E402


def test_split_rules():
    """R1a 三条判据的单元断言——2026-09-29 修过这里的一个真缺陷。"""
    sp = build_tasks.split_item

    # ① 尾段（以「…能力」结尾）是前段的补足，不得切成独立任务。
    #    旧规则只看"两侧是否都含任务词"，会把下面这些切出「检测与更换的能力」
    #    这类残片——它不是一个可独立判定的任务。
    for it, want in [
        ("具备汽车发动机总成及其零部件拆装、检测与更换的能力", 1),
        ("具备汽车车身电气设备及其电路拆装、检测、修理和更换的能力", 1),
        ("具有物联网产品装配、焊接、检测与调试的能力", 1),
        ("具有使用常用工量具、机械识图、拆装调试机械的能力", 1),
        ("具有休闲农业园区（景区）中常用植物育苗、种植和管护的能力", 1),
        ("具备色彩搭配、平面构成、版面设计等美术设计能力", 1),
        ("具有旅游景区、旅游电子商务、旅行社、定制旅行、导游、酒店服务的能力", 1),
    ]:
        got = sp(it)
        assert len(got) == want, "「%s」应切为 %d 条，实为 %d：%s" % (it, want, len(got), got)

    # ② 连词起首的片段是延续，不单独成条
    got = sp("具有休闲农业导游、讲解和服务的能力，并能够及时处理休闲农业导游中的突发事件")
    assert len(got) == 1, "「并能够…」不应单独成条，实为 %s" % got

    # ③ 分号一定是句级边界，无条件切
    got = sp("具有物联网产品装配、焊接的能力；具有设备安装与调试的能力")
    assert len(got) == 2, "分号应无条件切，实为 %s" % got

    # ④ 类型不同的并列片段仍要切（R1b 的前提）
    got = sp("具备洗、剪、吹、染、烫、盘以及发型设计的基础能力")
    assert len(got) == 1, "本句按 R1a ① 合并为一条（跨类型，交由 split_hint 提示），实为 %s" % got

    # ⑤ 名词枚举不拆（R1）
    got = sp("具有整合服装款式、色彩、材料等多重要素的能力")
    assert len(got) == 1, "名词枚举不应拆开，实为 %s" % got


def test_build():
    S = os.path.join(ROOT, "assets", "sample")
    st = json.load(io.open(os.path.join(S, "standards.json"), encoding="utf-8"))
    cfg = json.load(io.open(os.path.join(S, "majors.json"), encoding="utf-8"))
    abbr = {k: v["abbr"] for k, v in cfg.items()}

    rows = build_tasks.build(st, abbr)
    gen = build_tasks.generic_rows(st)

    # R3：通用素养必须被剔除，且单列可查
    assert any("终身学习" in g["item"] for g in gen), "「终身学习」应进入通用素养"
    assert not any("终身学习" in r["item"] for r in rows), "通用素养不应留在任务表里"

    # 汽修：9 条能力条目，剔除 2 条通用素养后至少 7 条任务
    qi = [r for r in rows if r["major"] == "汽车运用与维修"]
    assert len(qi) >= 7, "汽修应至少 7 条任务，实为 %d" % len(qi)

    # 编号连续且带专业缩写
    assert [r["tid"] for r in qi] == ["汽%d" % i for i in range(1, len(qi) + 1)], \
        "汽修编号应为 汽1—汽%d，实为 %s" % (len(qi), [r["tid"] for r in qi])

    # R5 + 分层架构：拆解阶段一律待定，不得预设任何分数
    assert all(r["llm"] is None and r["robot"] is None and r["quad"] == "待定"
               for r in rows), "拆解阶段所有任务应为待定（打分不由脚本做）"
    assert all(r["src"] == "待判定" for r in rows), "拆解阶段 src 应为「待判定」"

    # 教育层次适配：每条任务须带 level
    assert all(r["level"] for r in rows), "每条任务应带 level（教育层次）"

    # n_parts：每条任务须带并列段数，供复核清单扫读复合条目
    assert all(isinstance(r.get("n_parts"), int) and r["n_parts"] >= 1 for r in rows), \
        "每条任务应带 n_parts（并列段数）"
    assert max(r["n_parts"] for r in rows) >= 3, "样例里应有并列 ≥3 段的复合条目"

    # R1：名词枚举不应被拆开
    noun_enum = [r for r in rows if "整合服装款式" in r["task"]]
    assert noun_enum and "色彩" in noun_enum[0]["task"], \
        "「款式、色彩、材料」是名词枚举，不应拆开，实为 %s" % [r["task"] for r in noun_enum]

    # R1a：不得出现「…的能力」这类只有尾段的残片
    frag = [r["task"] for r in rows
            if r["task"] != r["item"] and r["task"].endswith("能力")
            and not r["task"].startswith(build_tasks.ABILITY_VERBS)]
    assert not frag, "不应切出以「…能力」结尾的残片，实为 %s" % frag

    # R1b：拆分后仍跨多类型者须带 split_hint。
    # 样例已按新规则清理干净（0 条），故用合成条目验证机制本身仍有效。
    synth = build_tasks.build(
        {"合成专业": {"code": "000000", "level": "中等职业教育", "facing": "—",
                    "abilities": ["具有物联网产品装配、焊接、检测与调试的能力；"
                                  "具有数据采集与标注、应用程序辅助开发的能力"],
                    "certs": "—"}},
        {"合成专业": "合"})
    assert len(synth) == 2, "合成条目应按分号切为 2 条，实为 %d" % len(synth)
    assert all(r["split_hint"] for r in synth), \
        "跨类型的合成条目应带 split_hint，实为 %s" % [r["split_hint"] for r in synth]

    hints = [r for r in rows if r.get("split_hint")]
    assert all(len(r["types"]) >= 2 for r in hints), "split_hint 只应出现在跨类型条目上"

    # 疑似复合条目（并列 ≥3 段）在样例里应能被识别出来，供复核清单扫读
    assert sum(1 for r in rows if r["n_parts"] >= 3) >= 3, \
        "样例应识别出若干并列 ≥3 段的疑似复合条目"

    # R4：任务类型标注（允许「未分类」，但不应全部未分类）
    assert sum(1 for r in rows if r["types"] != ["未分类"]) >= len(rows) * 0.6, \
        "任务类型覆盖率过低，检查关键词表"

    # classify 的基本行为
    assert build_tasks.classify("具备汽车维护作业的能力") == ["常规手工"]
    assert build_tasks.classify("具有整合服装款式、色彩、材料等多重要素的能力") == ["未分类"]

    print("OK: 任务 %d 条 ｜ 通用素养 %d 条 ｜ split_hint %d 条 ｜ 疑似复合 %d 条"
          % (len(rows), len(gen), len(hints), sum(1 for r in rows if r["n_parts"] >= 3)))
    for r in hints:
        print("   ⚠ %-4s %-30s %s" % (r["tid"], "/".join(r["types"]), r["task"][:40]))


def main():
    test_split_rules()
    test_build()


if __name__ == "__main__":
    main()
