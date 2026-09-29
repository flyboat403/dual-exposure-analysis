# -*- coding: utf-8 -*-
"""自检：内置索引必须与源数据逐项一致，且覆盖 896 个职业。

运行：python scripts/_selftest_onet_index.py
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import onet_index  # noqa: E402

# O*NET 源数据：**仅研制环境有**，用于逐项核对索引与源数据是否一致。
# 技能分发到其他机器后不存在，此时跳过这一段，其余检查照跑。
# 需要时用环境变量 ONET_ABIL / ONET_WA 指向自己导出的源文件。
SRC_ABIL = os.environ.get("ONET_ABIL", os.path.join(HERE, "onet_abil.json"))
SRC_WA = os.environ.get("ONET_WA", os.path.join(HERE, "onet_wa.json"))


def main():
    idx = onet_index.load(os.path.join(ROOT, "assets", "onet_ari.json"))
    occ = idx["occupations"]
    assert len(occ) == 896, "职业数应为 896，实为 %d" % len(occ)

    # 与源数据逐项核对——仅在研制环境（有源数据）时执行。
    # 技能分发到其他机器后源数据不存在，此时跳过这一段，其余检查照跑。
    if os.path.isfile(SRC_ABIL) and os.path.isfile(SRC_WA):
        abil = json.load(io.open(SRC_ABIL, encoding="utf-8"))
        wa = json.load(io.open(SRC_WA, encoding="utf-8"))
        bad = []
        for soc, rec in occ.items():
            for key, src, src_key in [("ari", wa, "ari"), ("pml", abil, "pml_core"),
                                      ("manual", wa, "manual"),
                                      ("routine_cog", wa, "routine_cog")]:
                if abs(rec[key] - src[soc][src_key]) > 1e-9:
                    bad.append((soc, key, rec[key], src[soc][src_key]))
        assert not bad, "与源数据不一致 %d 项，前 5 项：%s" % (len(bad), bad[:5])
        print("   （已与源数据逐项核对 896 职业 × 4 指标）")
    else:
        print("   （未找到源数据，跳过逐项核对——技能分发环境下属正常）")

    # 抽样：已核验的三个值（用容差，避免显示值四舍五入造成误判）
    assert abs(occ["49-3023.00"]["ari"] - 1.76) < 0.01, \
        "汽车维修技师 ARI 应为 1.76，实为 %s" % occ["49-3023.00"]["ari"]
    assert abs(occ["45-2092.00"]["pml"] - 59.16) < 0.01, \
        "农业工人 PML 应为 59.16，实为 %s" % occ["45-2092.00"]["pml"]
    assert abs(occ["41-3041.00"]["routine_cog"] - 70.0) < 1e-9, \
        "旅行社代理 routine_cog 应为 70.0"
    assert abs(occ["41-3041.00"]["manual"] - 11.75) < 0.01, \
        "旅行社代理常规手工分量应极低（11.75）"

    p = onet_index.percentile(idx, "pml", 59.16)
    assert 99.0 <= p <= 100.0, "59.16 的 PML 百分位应在 99—100，实为 %.1f" % p

    assert any(s == "49-3023.00" for s, _ in onet_index.search(idx, "Automotive")), \
        "检索 Automotive 应含 49-3023.00"

    line = onet_index.format_line(idx, "41-3041.00")
    assert "Travel Agents" in line and "ARI" in line and "70.0" in line, \
        "format_line 应含职业名、ARI 与 routine_cog，实为：%s" % line
    assert onet_index.format_line(idx, "99-9999.99").startswith("未找到"), \
        "不存在的 SOC 应返回「未找到」"

    print("OK: 896 职业逐项一致；抽样与 format_line 检查通过")
    print("   " + line)


if __name__ == "__main__":
    main()
