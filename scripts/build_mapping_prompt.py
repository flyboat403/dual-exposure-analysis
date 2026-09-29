# -*- coding: utf-8 -*-
"""专业 → O*NET 职业映射：组装语义推断输入包、校验映射、加权聚合。

**本脚本不做推断，也不做匹配。** 推断由 agent 完成——这是刻意的：
不同分类体系的职业名差异极大（"汽车维修工" ≠ "Motor Vehicle Mechanic"），
任何基于名称字符串的匹配都会系统性地错，只能靠语义理解。

脚本负责的三件事：
    1. build_prompt_pack —— 把"职业面向 + 主要专业能力要求 + 职业类证书"组装成
       给 agent 的推断输入，并写明禁止项与输出格式
    2. validate         —— 校验 agent 产出的映射（权重和、SOC 存在性、confidence、依据）
    3. aggregate        —— 把多个目标职业的 O*NET 指标按权重聚合成专业层数值

用法：
    python scripts/build_mapping_prompt.py --standards <standards.json> --out <pack.md>
    python scripts/build_mapping_prompt.py --validate <mapping.json>
"""
import argparse
import io
import json
import os

import onet_index

CONF_OK = ("high", "medium", "low")
KEYS = ("ari", "pml", "manual", "routine_cog")

PACK_HEAD = """# 任务：把每个专业的"职业面向"映射到 O*NET 职业（SOC）

## 硬性规则（违反即作废）

1. **禁止使用名称字符串匹配**。不得因为中文职业名里出现某个英文词，就去匹配 O*NET 职业名。
   不同分类体系的命名差异极大——例："汽车维修工" ≠ "Motor Vehicle Mechanic"。
   只能依据下面给出的中文语义材料做推断。
2. **只依据三段材料**：职业面向、主要专业能力要求、职业类证书。
   其中"主要专业能力要求"信息量最大，是判断岗位群实际工作内容的主要依据。
3. 每个专业给出 **2—4 个** O*NET 职业，**权重之和必须为 1.0**。
   权重反映该岗位群在本专业培养中的实际比重，不是平均分配。
4. 每个目标职业必须给出：
   - `china_code` / `china_name`：对应的中国职业（取自《中华人民共和国职业分类大典》）
   - `onet_code`：O*NET SOC 代码，格式 `xx-xxxx.xx`
   - `onet_name`：O*NET 职业英文名（照抄索引里的 title，不要自己翻译）
   - `mapping_confidence`：`high` / `medium` / `low`
   - `note`：中文，一句话写明判断依据（哪条能力要求支持这个映射）
5. **拿不准就给 `low`，不要猜。** 宁少勿滥——错误的映射会让后面所有分析白做。
6. 不要使用不在 O*NET 索引中的 SOC 代码。可以用下面的命令核对：

   ```
   python scripts/onet_index.py --search <英文关键词>
   python scripts/onet_index.py --show <SOC>
   ```

## 输出格式（严格 JSON，不要加解释文字）

```json
{
  "<专业名>": {
    "code": "<专业代码>",
    "level": "<教育层次>",
    "facing": "<职业面向原文>",
    "targets": [
      {
        "china_code": "<大典职业代码>",
        "china_name": "<大典职业名称>",
        "onet_code": "xx-xxxx.xx",
        "onet_name": "<O*NET 职业英文名>",
        "mapping_confidence": "high",
        "weight": 0.6,
        "note": "<判断依据>"
      }
    ]
  }
}
```

## 为什么要这么严

映射是本方法唯一无法自动化的环节。职业院校的专业"职业面向"是一句规范性的培养目标
（例如"面向汽车机电维修、汽车维修接待等岗位（群）"），它并不直接等于任何一个 O*NET
职业；一个岗位群往往横跨 2—4 个 O*NET 职业，而各岗位群在培养中的比重也不相同。
所以这一步只能由了解该专业的人（或能读懂中文语义的模型）来判断，并留下依据供复核。
"""


def _dict_snippet(dict_dir, facing, limit=3):
    """可选增强：从中国职业大典分册里取相关条目作参考材料。

    注意这是**语义参考**，不是匹配依据——分册按大类组织，条目里是职业定义与
    主要工作任务的中文描述，帮助判断岗位群落在哪个职业上。
    """
    if not dict_dir or not os.path.isdir(dict_dir):
        return ""
    words = [w for w in facing.replace("、", " ").replace("，", " ").split() if len(w) >= 3]
    if not words:
        return ""
    hits = []
    for fn in sorted(os.listdir(dict_dir)):
        if not (fn.startswith("class_") and fn.endswith(".md")):
            continue
        txt = io.open(os.path.join(dict_dir, fn), encoding="utf-8", errors="ignore").read()
        for w in words:
            i = txt.find(w)
            if i >= 0:
                snippet = txt[max(0, i - 80):i + 220].replace("\n", " ")
                hits.append("- （%s）…%s…" % (fn[6:12], snippet))
                break
        if len(hits) >= limit:
            break
    if not hits:
        return ""
    return ("\n\n## 参考材料：中国职业大典相关条目\n"
            "（仅供语义参考。**不得**据此做名称匹配，也不要照抄其中的代码——"
            "大典代码与 O*NET 代码是两套体系。）\n" + "\n".join(hits))


def build_prompt_pack(standards, index=None, dict_dir=None):
    """组装给 agent 的语义推断输入包。"""
    parts = [PACK_HEAD]
    for major, m in standards.items():
        parts.append("\n---\n\n## 专业：%s\n" % major)
        parts.append("- **专业代码**：%s" % m.get("code", "（缺）"))
        parts.append("- **教育层次**：%s" % m.get("level", "（缺）"))
        parts.append("\n**职业面向**：%s\n" % m.get("facing", "（缺）"))
        parts.append("**主要专业能力要求**（共 %d 条）：\n" % len(m.get("abilities", [])))
        parts.append("\n".join("%d. %s" % (i, a) for i, a in enumerate(m.get("abilities", []), 1)))
        parts.append("\n\n**职业类证书**：%s" % m.get("certs", "（缺）"))
        parts.append(_dict_snippet(dict_dir, m.get("facing", "")))
    parts.append("\n---\n\n## 确认环节\n"
                 "产出映射后，把每个候选 SOC 用 `python scripts/onet_index.py --show <SOC>` "
                 "查一遍，把指标展示给使用者，让他们判断这些职业是否真的对得上本校该专业的岗位群。\n"
                 "**未经使用者确认，不得进入任务拆解与打分环节。**\n")
    return "\n".join(parts)


def validate(mapping, index):
    """校验映射，返回问题清单（空列表表示通过）。下划线开头的键视为注释，跳过。"""
    probs = []
    for major, m in mapping.items():
        if major.startswith("_"):
            continue
        if not isinstance(m, dict):
            probs.append("%s：值应为对象，实为 %s" % (major, type(m).__name__))
            continue
        tg = m.get("targets") or []
        if not tg:
            probs.append("%s：targets 为空" % major)
            continue
        if len(tg) > 6:
            probs.append("%s：目标职业 %d 个，偏多（建议 2—4 个）" % (major, len(tg)))
        s = sum(t.get("weight", 0) for t in tg)
        if abs(s - 1.0) > 1e-6:
            probs.append("%s：权重和为 %.3f，应为 1.0" % (major, s))
        for t in tg:
            soc = t.get("onet_code", "")
            if not onet_index.lookup(index, soc):
                probs.append("%s：SOC %s 不存在于内置索引" % (major, soc))
            if t.get("mapping_confidence") not in CONF_OK:
                probs.append("%s：SOC %s 的 mapping_confidence 非法（%r）"
                             % (major, soc, t.get("mapping_confidence")))
            for k in ("china_code", "china_name", "onet_name", "note"):
                if not t.get(k):
                    probs.append("%s：SOC %s 缺 %s" % (major, soc, k))
    return probs


def aggregate(index, targets):
    """把多个目标职业的 O*NET 指标按权重聚合成专业层数值。"""
    total = sum(t["weight"] for t in targets)
    return {k: round(sum(onet_index.lookup(index, t["onet_code"])[k] * t["weight"]
                         for t in targets) / total, 2)
            for k in KEYS}


def default_index_path():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "assets", "onet_ari.json")


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description="专业 → O*NET 映射：输入包 / 校验 / 聚合")
    ap.add_argument("--standards", default=os.path.join(here, "assets", "sample", "standards.json"))
    ap.add_argument("--index", default=default_index_path())
    ap.add_argument("--dict-dir", help="可选：中国职业大典分册目录（作语义参考）")
    ap.add_argument("--out", help="把输入包写到该文件")
    ap.add_argument("--validate", help="校验某个 mapping.json")
    ap.add_argument("--aggregate", help="对某个 mapping.json 做加权聚合")
    a = ap.parse_args()

    if a.validate or a.aggregate:
        mp = json.load(io.open(a.validate or a.aggregate, encoding="utf-8"))
        idx = onet_index.load(a.index)
        probs = validate(mp, idx)
        if probs:
            print("发现 %d 个问题：" % len(probs))
            for p in probs:
                print("  [X] " + p)
            raise SystemExit(1)
        nmajor = sum(1 for k in mp if not k.startswith("_"))
        print("OK：映射校验通过（%d 个专业）" % nmajor)
        if a.aggregate:
            print()
            print("%-14s %8s %8s %10s %10s" % ("专业", "ARI", "PML", "常规手工", "常规认知"))
            for major, m in mp.items():
                if major.startswith("_"):
                    continue
                g = aggregate(idx, m["targets"])
                print("%-14s %8.1f %8.1f %10.1f %10.1f"
                      % (major, g["ari"], g["pml"], g["manual"], g["routine_cog"]))
        return

    standards = json.load(io.open(a.standards, encoding="utf-8"))
    idx = onet_index.load(a.index)
    pack = build_prompt_pack(standards, idx, a.dict_dir)
    if a.out:
        io.open(a.out, "w", encoding="utf-8").write(pack)
        print("wrote %s  %d 字" % (a.out, len(pack)))
    else:
        print(pack)


if __name__ == "__main__":
    main()
