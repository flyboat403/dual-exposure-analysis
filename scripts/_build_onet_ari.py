# -*- coding: utf-8 -*-
"""一次性构建脚本：从 O*NET 原始数据生成 assets/onet_ari.json。

输入（O*NET 官方数据，仅构建时用；构建产物已随技能分发，运行期不需要它们）：
    onet_abil.json   —— 896 职业 × 52 项 Abilities（含 Importance）
    onet_wa.json     —— 896 职业 × Work Activities 派生值

  来源：O*NET Database（美国劳工部，CC BY 4.0）的 Abilities 与 Work Activities 表。
  取数方式：在 O*NET 官网按 SOC 逐职业导出，或从 O*NET 数据库的
  `Abilities.txt` / `Work Activities.txt` 按 `O*NET-SOC Code` 汇总。

输出：
    assets/onet_ari.json  —— {_meta, occupations: {SOC: {title, ari, pml, manual, routine_cog}}}

用法：
    python scripts/_build_onet_ari.py --abil <path> --wa <path>
"""
import argparse
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 源数据路径：**仅重建索引时需要**，技能分发环境中通常不存在（产物已随技能分发）。
# 要重建时，把 O*NET 导出文件放到 scripts/ 下命名为 onet_abil.json / onet_wa.json，
# 或用 --abil / --wa 指定路径，或设环境变量 ONET_ABIL / ONET_WA。
DEFAULT_ABIL = os.environ.get("ONET_ABIL", os.path.join(HERE, "onet_abil.json"))
DEFAULT_WA = os.environ.get("ONET_WA", os.path.join(HERE, "onet_wa.json"))


def build(abil_path, wa_path):
    abil = json.load(io.open(abil_path, encoding="utf-8"))
    wa = json.load(io.open(wa_path, encoding="utf-8"))

    occ = {}
    for soc, w in wa.items():
        a = abil.get(soc)
        if not a:
            continue
        occ[soc] = {
            "title": a["title"],
            "ari": w["ari"],
            "pml": a["pml_core"],
            "manual": w["manual"],
            "routine_cog": w["routine_cog"],
        }
    return {
        "_meta": {
            "source": "O*NET 职业数据库（U.S. Department of Labor, Employment and Training Administration）",
            "license": "CC BY 4.0",
            "derived_from": "O*NET Work Activities 与 Abilities 的 Importance 评分",
            "ari_definition": (
                "自动化可及性指数 = 常规侧 7 项工作活动均值 − 非常规侧 8 项均值。"
                "常规侧：Controlling Machines and Processes / Handling and Moving Objects / "
                "Operating Vehicles, Mechanized Devices, or Equipment / Performing General Physical "
                "Activities / Processing Information / Documenting, Recording, and Maintaining "
                "Information / Performing Administrative Activities。"
                "非常规侧：Thinking Creatively / Making Decisions and Solving Problems / "
                "Repairing and Maintaining Mechanical Equipment / Repairing and Maintaining "
                "Electronic Equipment / Inspecting Equipment, Structures, or Materials / "
                "Assisting and Caring for Others / Resolving Conflicts and Negotiating with Others / "
                "Guiding, Directing, and Motivating Subordinates"
            ),
            "pml_definition": (
                "感知—操作负担 = Abilities 中 Psychomotor(10) + Physical(9) 的 Importance 均值"
            ),
            "manual_definition": "常规手工分量（对应工业机器人等物理自动化）",
            "routine_cog_definition": "常规认知分量（对应规则化业务系统）",
            "count": len(occ),
        },
        "occupations": occ,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--abil", default=DEFAULT_ABIL)
    ap.add_argument("--wa", default=DEFAULT_WA)
    ap.add_argument("--out", default=os.path.join(ROOT, "assets", "onet_ari.json"))
    a = ap.parse_args()

    data = build(a.abil, a.wa)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with io.open(a.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print("wrote %s  %d 职业  %.1f KB"
          % (a.out, data["_meta"]["count"], os.path.getsize(a.out) / 1024))


if __name__ == "__main__":
    main()
