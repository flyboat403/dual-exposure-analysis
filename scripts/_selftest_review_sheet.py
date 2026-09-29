# -*- coding: utf-8 -*-
"""自检：复核清单的分区、编号冻结、真冲突判定、xlsx 下拉与读回。

运行：python scripts/_selftest_review_sheet.py
"""
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import build_review_sheet as rs  # noqa: E402


def test_build_logic(rows):
    res = rs.build(rows)

    # 分区必须覆盖全部条目
    assert len(res["pending"]) + len(res["done"]) == len(rows), "分区不覆盖全部条目"
    assert res["total"] == len(rows)

    # 编号必须保留原编号、升序、不重排
    def key(t):
        return (t[:1], int(t[1:]))

    pids = [r["tid"] for r in res["pending"]]
    assert pids == sorted(pids, key=key), "待判定区编号应升序，实为 %s" % pids

    # 真冲突应被检出
    fake = [{"tid": "测1", "major": "X", "task": "a", "types": ["常规手工"], "quad": "Ⅲ 仅 LLM 高"},
            {"tid": "测2", "major": "X", "task": "b", "types": ["交流"], "quad": "Ⅱ 双高"}]
    c = rs.build(fake)["conflicts"]
    assert any(x["tid"] == "测1" for x in c), "「常规手工却判Ⅲ」应被检出"
    assert any(x["tid"] == "测2" for x in c), "「单一交流却判自动化侧高」应被检出"

    # 组合类型不应被误报（组合里常规手工是主导，不是冲突）
    combo = [{"tid": "测3", "major": "X", "task": "c",
              "types": ["常规手工", "交流"], "quad": "Ⅱ 双高"}]
    assert not rs.build(combo)["conflicts"], "组合类型不应被误报为冲突"

    # 待定与未分类不参与冲突判定
    quiet = [{"tid": "测4", "major": "X", "task": "d", "types": ["未分类"], "quad": "Ⅲ 仅 LLM 高"},
             {"tid": "测5", "major": "X", "task": "e", "types": ["常规手工"], "quad": "待定"}]
    assert not rs.build(quiet)["conflicts"], "未分类与待定不应触发冲突"

    # 输出文件可写、可读、含关键节
    d = tempfile.mkdtemp()
    md, csv = os.path.join(d, "s.md"), os.path.join(d, "s.csv")
    rs.write_md(res, md)
    rs.write_csv(res, csv)
    text = io.open(md, encoding="utf-8").read()
    for need in ("待判定", "类型与象限冲突", "象限分布", "按专业"):
        assert need in text, "Markdown 应含「%s」节" % need
    assert "xlsx" in text, "Markdown 应提示填写用 xlsx"
    head = io.open(csv, encoding="utf-8-sig").readline()
    assert "LLM 档" in head and "自动化档" in head and "类型修正1" in head, \
        "CSV 表头应与 xlsx 口径一致（两档 + 类型修正），实为 %s" % head.strip()
    assert "教研组判定" not in head, "旧的单列「教研组判定」口径应已废弃"
    assert os.path.getsize(csv) > 100


def test_quad_of_matches_render():
    """本模块的 quad_of 必须与 render.quad_of 完全一致（否则读回后轴序校验会失败）。"""
    try:
        import render
    except Exception as e:                                    # 缺 matplotlib 时跳过
        print("   （跳过 quad_of 交叉比对：%s）" % e)
        return 0
    n = 0
    for l in (0.20, 0.55, 0.80):
        for r in (0.20, 0.55, 0.80):
            a, b = rs.quad_of(l, r), render.quad_of(l, r)
            assert a == b, "(%s,%s) 象限不一致：%s vs %s" % (l, r, a, b)
            n += 1
    return n


def fixture():
    """含待判定与冲突的小样本。"""
    return [
        {"major": "甲专业", "code": "600001", "level": "中等职业教育", "tid": "甲1",
         "item": "核对业务票据", "task": "核对业务票据", "types": ["常规认知"],
         "split_hint": False, "llm": None, "robot": None, "quad": "待定",
         "src": "待判定", "conf": "待判定"},
        {"major": "甲专业", "code": "600001", "level": "中等职业教育", "tid": "甲2",
         "item": "手工装夹工件的能力", "task": "手工装夹工件", "types": ["常规手工"],
         "split_hint": False, "llm": None, "robot": None, "quad": "待定",
         "src": "待判定", "conf": "待判定"},
        {"major": "甲专业", "code": "600001", "level": "中等职业教育", "tid": "甲3",
         "item": "接待客户的能力", "task": "接待客户", "types": ["交流"],
         "split_hint": False, "llm": 0.80, "robot": 0.80, "quad": "Ⅱ 双高",
         "src": "规则法", "conf": "自动"},
        {"major": "甲专业", "code": "600001", "level": "中等职业教育", "tid": "甲4",
         "item": "朗读课文", "task": "朗读课文", "types": ["常规手工"],
         "split_hint": False, "llm": 0.80, "robot": 0.20, "quad": "Ⅲ 仅 LLM 高",
         "src": "规则法", "conf": "自动"},
    ]


def test_xlsx_roundtrip():
    rows = fixture()
    res = rs.build(rows)
    assert len(res["pending"]) == 2 and len(res["conflicts"]) == 2, \
        "样本应有 2 条待判定 + 2 条冲突，实为 %d/%d" % (len(res["pending"]), len(res["conflicts"]))

    d = tempfile.mkdtemp()
    xp = os.path.join(d, "sheet.xlsx")
    rs.write_xlsx(res, xp)
    assert os.path.getsize(xp) > 3000, "xlsx 体积过小"

    # md 的待判定表必须与 xlsx 同口径（旧的单列「教研组判定」已废弃）
    mdp = os.path.join(d, "sheet.md")
    rs.write_md(res, mdp)
    md = io.open(mdp, encoding="utf-8").read()
    assert "| LLM 档 | 自动化档 | 类型修正 | 理由 |" in md, \
        "md 待判定表应与 xlsx 同口径（两档 + 类型修正）"
    assert "教研组判定" not in md, "md 不应再出现旧的单列「教研组判定」"

    # ── 结构核对：多工作表 + 下拉 + 预填（不依赖 openpyxl）
    import zipfile
    z = zipfile.ZipFile(xp)
    names = z.namelist()
    for need in ("[Content_Types].xml", "_rels/.rels", "xl/workbook.xml",
                 "xl/_rels/workbook.xml.rels", "xl/styles.xml"):
        assert need in names, "xlsx 缺少部件 %s" % need
    assert len([n for n in names if n.startswith("xl/worksheets/")]) == 5, "应有 5 张工作表"
    s3 = z.read("xl/worksheets/sheet3.xml").decode("utf-8")
    assert s3.count("<f>") == 2, "冲突表应有 2 个象限公式，实为 %d" % s3.count("<f>")
    assert "&gt;=" in s3, "公式里的 >= 应转义为 &gt;="
    assert "<f>=" not in s3, "公式内不得带前导等号"
    for i in (2, 3):     # 待判定表与冲突表都要有下拉
        x = z.read("xl/worksheets/sheet%d.xml" % i).decode("utf-8")
        assert 'type="list"' in x, "工作表 %d 应有下拉（数据有效性）" % i
        assert "0.20,0.55,0.80" in x, "工作表 %d 的档位下拉缺失" % i
        assert "常规手工,非常规手工,常规认知,分析,交流" in x, "工作表 %d 的类型下拉缺失" % i
        assert 'errorStyle="stop"' in x, "工作表 %d 的下拉应拒绝表外取值" % i

    # ── 读回：模拟教研组填写
    try:
        from openpyxl import load_workbook
    except ImportError:
        print("   （跳过读回测试：无 openpyxl）")
        return None
    wb = load_workbook(xp)
    s1, s2 = wb["一、待判定"], wb["二、类型与象限冲突"]
    h1 = {c.value: c.column for c in s1[1]}
    h2 = {c.value: c.column for c in s2[1]}
    assert s1.freeze_panes == "A2" and s2.freeze_panes == "A2", "两张待填表都应冻结表头"
    assert len(s1.data_validations.dataValidation) >= 4, "待判定表应有 4 组下拉"
    assert len(s2.data_validations.dataValidation) >= 4, "冲突表应有 4 组下拉"

    # 甲1：填 LLM 0.80 / 自动化 0.20 → 应得 Ⅲ 仅 LLM 高
    s1.cell(2, h1["LLM 档"]).value = "0.80"
    s1.cell(2, h1["自动化档"]).value = "0.20"
    s1.cell(2, h1["理由"]).value = "单据核对已由系统承担"
    # 甲2：填 LLM 0.20 / 自动化 0.80 → 应得 Ⅰ 仅机器人高
    s1.cell(3, h1["LLM 档"]).value = "0.20"
    s1.cell(3, h1["自动化档"]).value = "0.80"
    # 甲3（冲突）：去掉类型修正预填，改为「常规认知」；两档保持预填原样
    for r in range(2, s2.max_row + 1):
        if s2.cell(r, h2["编号"]).value == "甲3":
            s2.cell(r, h2["类型修正1"]).value = "常规认知"
            s2.cell(r, h2["类型修正2"]).value = None
    # 甲4（冲突）：完全不动
    # 额外加一行不存在的编号，应被忽略
    r = s2.max_row + 1
    s2.cell(r, h2["编号"]).value = "甲99"
    s2.cell(r, h2["LLM 档"]).value = "0.80"
    wb.save(xp)

    edits = rs.read_xlsx(xp)
    assert set(edits) == {"甲1", "甲2", "甲3", "甲4", "甲99"}, \
        "读回编号应含甲1/甲2/甲3/甲4/甲99，实为 %s" % sorted(edits)
    assert edits["甲1"]["llm"] == 0.80 and edits["甲1"]["robot"] == 0.20
    assert edits["甲1"]["reason"] == "单据核对已由系统承担"
    assert edits["甲3"]["types"] == ["常规认知"], "类型修正应被读到"
    # 冲突行按现判定预填 → 原样读回，判定不变
    assert edits["甲4"]["llm"] == 0.80 and edits["甲4"]["robot"] == 0.20

    log, unknown, warn = rs.apply_edits(rows, edits)
    by = {r["tid"]: r for r in rows}
    assert by["甲1"]["quad"] == "Ⅲ 仅 LLM 高", by["甲1"]["quad"]
    assert by["甲2"]["quad"] == "Ⅰ 仅机器人高", by["甲2"]["quad"]
    assert by["甲3"]["types"] == ["常规认知"] and by["甲3"]["quad"] == "Ⅱ 双高"
    assert by["甲1"]["conf"] == "教研组" and by["甲1"]["src"] == "教研组"
    assert "教研组：单据核对已由系统承担" in by["甲1"]["note"]
    assert unknown == ["甲99"], "未知编号应被报出（编号冻结），实为 %s" % unknown
    assert not warn, warn
    # 任何有双档的条目，象限必须等于 quad_of——否则 render 的轴序校验会报错
    for r in rows:
        if r["llm"] is not None and r["robot"] is not None:
            assert r["quad"] == rs.quad_of(r["llm"], r["robot"]), r["tid"]
    return len(log)


def test_out_of_range_rejected():
    """档位取值表外必须报错，而不是默默写进任务表。"""
    rows = fixture()
    res = rs.build(rows)
    d = tempfile.mkdtemp()
    xp = os.path.join(d, "bad.xlsx")
    rs.write_xlsx(res, xp)
    try:
        from openpyxl import load_workbook
    except ImportError:
        return False
    wb = load_workbook(xp)
    s1 = wb["一、待判定"]
    h1 = {c.value: c.column for c in s1[1]}
    s1.cell(2, h1["LLM 档"]).value = "0.70"     # 不在 0.20/0.55/0.80 内
    wb.save(xp)
    try:
        rs.read_xlsx(xp)
    except SystemExit as e:
        assert "档位" in str(e), str(e)
        return True
    raise AssertionError("表外取值应被拒绝")


def test_apply_unknown_columns():
    """列被挪动也应能读回（按表头名称定位，不依赖列序）。"""
    try:
        from openpyxl import load_workbook
    except ImportError:
        return False
    rows = fixture()
    res = rs.build(rows)
    d = tempfile.mkdtemp()
    xp = os.path.join(d, "moved.xlsx")
    rs.write_xlsx(res, xp)
    wb = load_workbook(xp)
    s1 = wb["一、待判定"]
    h1 = {c.value: c.column for c in s1[1]}
    # 先填一处，再把列整体右移
    for r in range(2, s1.max_row + 1):
        if s1.cell(r, h1["编号"]).value == "甲1":
            s1.cell(r, h1["类型修正1"]).value = "分析"
    s1.insert_cols(1)
    wb.save(xp)
    edits = rs.read_xlsx(xp)
    # 甲1 来自「待判定」表（刚填的类型修正）；甲3／甲4 来自「冲突」表的预填两档
    assert set(edits) == {"甲1", "甲3", "甲4"}, \
        "插列后读到的编号异常：%s" % sorted(edits)
    assert edits["甲1"]["types"] == ["分析"], "插列后类型修正应仍落在「类型修正1」列"
    assert edits["甲1"]["llm"] is None and edits["甲1"]["robot"] is None, \
        "插列后「LLM 档」不应串到别的列"
    return True


def main():
    rows = json.load(io.open(os.path.join(ROOT, "assets", "sample", "tasks.json"),
                             encoding="utf-8"))
    test_build_logic(rows)
    n = test_quad_of_matches_render()
    nlog = test_xlsx_roundtrip()
    test_out_of_range_rejected()
    test_apply_unknown_columns()

    res = rs.build(rows)
    print("OK: 待判定 %d ｜ 已判定 %d ｜ 冲突 %d ｜ 合计 %d"
          % (len(res["pending"]), len(res["done"]), len(res["conflicts"]), res["total"]))
    print("   象限：" + "  ".join("%s %d" % (q, res["counts"][q])
                                  for q in rs.QORDER if res["counts"][q]))
    if n:
        print("   quad_of 与 render 逐格一致：%d 格" % n)
    if nlog is not None:
        print("   xlsx 读回闭环：填入 5 条 → 实际变更 %d 条" % nlog)


if __name__ == "__main__":
    main()
