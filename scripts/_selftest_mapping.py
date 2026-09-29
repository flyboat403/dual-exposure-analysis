# -*- coding: utf-8 -*-
"""自检：映射输入包、校验、加权聚合。

运行：python scripts/_selftest_mapping.py
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import onet_index  # noqa: E402
import build_mapping_prompt as bmp  # noqa: E402


def main():
    S = os.path.join(ROOT, "assets", "sample")
    idx = onet_index.load(os.path.join(ROOT, "assets", "onet_ari.json"))
    st = json.load(io.open(os.path.join(S, "standards.json"), encoding="utf-8"))
    mp = json.load(io.open(os.path.join(S, "mapping.json"), encoding="utf-8"))

    # 输入包必须含三段语义材料，且明确写出禁止项与输出格式要求
    pack = bmp.build_prompt_pack(st, idx)
    for need in ("职业面向", "主要专业能力要求", "职业类证书"):
        assert need in pack, "输入包应含「%s」" % need
    assert "禁止" in pack, "输入包必须写明禁止项"
    assert "字符串匹配" in pack, "输入包必须明确禁止名称字符串匹配"
    assert "Motor Vehicle Mechanic" in pack, "输入包应给出反例，说明为何不能做名称匹配"
    assert "mapping_confidence" in pack, "输入包必须要求输出 confidence"
    assert "未经使用者确认" in pack, "输入包必须写明强制确认环节"

    # 样例映射应 0 问题
    probs = bmp.validate(mp, idx)
    assert not probs, "样例映射应有 0 个问题，实为：%s" % probs

    # 校验必须能抓出四类错误
    bad = {"X": {"targets": [
        {"china_code": "x", "china_name": "x", "onet_code": "99-9999.99",
         "onet_name": "x", "mapping_confidence": "high", "weight": 0.5, "note": "a"}]}}
    p = bmp.validate(bad, idx)
    assert any("权重和" in x for x in p), "应检出权重和≠1"
    assert any("不存在" in x for x in p), "应检出 SOC 不存在"

    bad2 = {"X": {"targets": [
        {"china_code": "x", "china_name": "x", "onet_code": "49-3023.00",
         "onet_name": "x", "mapping_confidence": "very high", "weight": 1.0, "note": "a"}]}}
    assert any("confidence" in x for x in bmp.validate(bad2, idx)), "应检出非法 confidence"

    bad3 = {"X": {"targets": [
        {"china_code": "x", "china_name": "x", "onet_code": "49-3023.00",
         "onet_name": "x", "mapping_confidence": "high", "weight": 1.0}]}}
    assert any("缺 note" in x for x in bmp.validate(bad3, idx)), "应检出缺 note"

    # 下划线开头的键视为注释，不参与校验
    assert not bmp.validate({"_note": "注释", "X": mp["汽车运用与维修"]}, idx), \
        "下划线键应被跳过"

    # 加权聚合必须与已核验值一致
    exp = {"汽车运用与维修": (3.5, 44.4, 70.4), "服装设计与工艺": (-1.7, 28.9, 44.3),
           "航空服务": (0.7, 33.4, 52.2)}
    for major, (ari, pml, manual) in exp.items():
        g = bmp.aggregate(idx, mp[major]["targets"])
        assert abs(g["ari"] - ari) < 0.05, "%s ARI 应为 %.1f，实为 %.2f" % (major, ari, g["ari"])
        assert abs(g["pml"] - pml) < 0.05, "%s PML 应为 %.1f，实为 %.2f" % (major, pml, g["pml"])
        assert abs(g["manual"] - manual) < 0.05, \
            "%s 常规手工分量应为 %.1f，实为 %.2f" % (major, manual, g["manual"])

    # 输入包必须能带上"无对应大典职业"的诚实标注
    assert "汽车维修接待（岗位，非大典职业）" in json.dumps(mp, ensure_ascii=False), \
        "样例应包含「无对应大典职业」的情形"

    print("OK: 输入包 %d 字；校验与聚合通过；三个专业的聚合值与已核验值一致" % len(pack))
    for major in exp:
        g = bmp.aggregate(idx, mp[major]["targets"])
        print("   %-12s ARI %6.1f  PML %5.1f  常规手工 %5.1f  常规认知 %5.1f"
              % (major, g["ari"], g["pml"], g["manual"], g["routine_cog"]))


if __name__ == "__main__":
    main()
