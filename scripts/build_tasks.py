# -*- coding: utf-8 -*-
"""标准文本 → 任务表。

本脚本只做四件事：剔除通用素养、把能力条目拆成任务、标注任务类型、初始化待判定状态。
**它不打分**——打分是 LLM 侧的判定动作（由 agent 在对话中逐条给出），
若脚本自己打分，两侧就都由程序给出，方法独立性不成立，四象限矩阵会退化。

拆解规则（R1 / R1a / R1b + R2—R5）：
    R1   顿号／逗号是**候选**边界（不是必然边界）；分号一定是边界
    R1a  候选边界只有同时满足下面三条才真正切开，否则并入前段：
         ① 后段是完整表述——不以「并／以及／和／及／或／同时」起首，
            也不以「…能力」结尾（这类是前段的补足，不是新任务）
         ② 后段长度 ≥ MIN_FRAGMENT（过短则失去上下文，见 R2）
         ③ 后段的任务类型与当前缓冲段**不同**
         第③条是关键：中文顿号既分隔并列动宾结构（该拆），也分隔同一任务的
         复合宾语（不该拆）。「拆装、检测与更换」是一个任务的三个动作，
         「造型设计与款式绘制表达、结构设计与纸样制作」才是两个方向不同的任务。
    R1b  拆分后仍跨多个任务类型者标 split_hint，交 agent／教研组再拆一层
    R2   打分在原始能力条目层进行，拆分碎片仅作任务清单
    R3   通用素养不构成任务，单列不计分
    R4   每条任务标注任务类型（常规手工／非常规手工／常规认知／分析／交流）
    R5   无法判定者标为待定，不默认判为安全

用法：
    python scripts/build_tasks.py --standards <standards.json> --majors <majors.json> --out <tasks.json>
"""
import argparse
import io
import json
import os
import re

RULES = {
    "R1": "顿号／逗号是候选边界；分号一定是边界",
    "R1a": "候选边界须同时满足：后段是完整表述 + 长度足够 + 类型与缓冲段不同，否则并入前段",
    "R1b": "拆分后仍跨多类型者标 split_hint，交 agent／教研组再拆",
    "R2": "打分在原始能力条目层进行，拆分碎片仅作任务清单（碎片过短会失去上下文）",
    "R3": "通用素养不构成任务，单列不计分",
    "R4": "每条任务标注任务类型（常规手工／非常规手工／常规认知／分析／交流）",
    "R5": "无法判定者标为待定，不默认判为安全",
}

# 通用素养词表（R3）。命中即整条剔除——这类条目描述的是人的品质，不是可被技术替代的任务。
GENERIC = [
    "终身学习", "可持续发展", "职业素养", "文化修养", "方针政策", "法律法规",
    "行业标准", "安全操作与自我防护", "质量意识", "环保意识", "安全意识",
    "协作意识", "创新思维", "奉献精神", "绿色生产", "环境保护", "安全防护",
    "职业道德", "依法从事", "仪容仪表和言谈举止", "数字化发展需求的基本数字技能",
]

# 任务类型关键词表（R4）。扩充时请同步更新 references/method.md 的说明。
TYPES = [
    ("常规手工", [
        "熟练使用", "操作", "拆装", "制作", "缝纫", "装配", "焊接", "加工", "烹饪",
        "初加工", "种植", "管护", "育苗", "饲养", "驯导", "更换", "维修", "洗",
        "剪", "吹", "染", "烫", "盘", "化妆", "修剪", "发型", "面点", "热菜",
        "冷菜", "雕刻", "维护作业",
    ]),
    ("非常规手工", [
        "安装与调试", "安装调试", "运行维护", "运行与维护", "故障", "调试", "检修",
        "保养", "系统集成", "施工", "布线", "试制", "组网", "监控", "造型", "建模",
        "拍摄", "摄像",
    ]),
    ("常规认知", [
        "核算", "成本", "校对", "录入", "报表", "文档", "识读", "识图", "记录",
        "质量检测", "办理", "登记", "工作流程", "服务程序", "计价", "计调", "售票",
        "排版", "配色", "采集", "标注",
    ]),
    ("分析", [
        "设计", "策划", "分析", "方案", "创意", "创作", "规划", "判断", "鉴别",
        "诊断", "识别", "美化", "构成", "编程", "开发", "原型", "绘制", "调色",
    ]),
    ("交流", [
        "沟通", "接待", "服务", "讲解", "销售", "咨询", "导游", "安抚", "协调",
        "突发事件", "表达", "互动", "客户", "游客", "旅客", "营销", "导购", "陈列",
        "乘务", "安检", "贵宾",
    ]),
]

MIN_FRAGMENT = 6  # 短于此长度的碎片与前一片合并，避免失去上下文（R2）

# 以这些连词起首的片段是前段的延续，不是新任务（R1a ①）
CONJ_HEAD = ("并", "以及", "和", "及", "或", "同时", "也", "与")
# 以「…能力」结尾的片段是前段的补足语（R1a ①）。注意必须排除自带主语的整条能力
# （以「具备／具有／掌握／能够」起首者），否则整条能力会被误并。
ABILITY_VERBS = ("具备", "具有", "掌握", "能够", "能", "会", "熟悉", "了解")


def classify(text):
    """按关键词表给出任务类型；都不命中则返回 ['未分类']。"""
    hits = [k for k, kws in TYPES if any(w in text for w in kws)]
    return hits or ["未分类"]


def _is_tail(seg):
    """R1a ①：该片段是不是前段的补足语（而非独立任务）。

    两类：① 以连词起首；② 以「…能力」结尾且本身不带主语动词。
    """
    if seg.startswith(CONJ_HEAD):
        return True
    if seg.endswith("能力") and not seg.startswith(ABILITY_VERBS):
        return True
    return False


def split_item(item):
    """R1 / R1a：按「候选边界 + 三条判据」切分能力条目。

    中文顿号既用于并列的动宾结构（应拆），也用于名词枚举或同一任务的复合宾语
    （不该拆）。三条判据见文件头 R1a——其中最关键的是第③条「类型不同」：
    仅凭「两侧都含任务关键词」判断会把「拆装、检测与更换」切出
    「检测与更换的能力」这样的残片，它不是一个可独立判定的任务。

    分号一定是句级边界，无条件切。

    切分后再按 R1b 检查：若某片仍同时命中多个任务类型，说明它内部还混着方向
    不同的任务，该片会被标上 split_hint，交由 agent 或教研组再拆一层。
    """
    segs = [s for s in re.split(r"[；;]", item) if s.strip()]
    if len(segs) > 1:
        out = []
        for s in segs:
            out.extend(split_item(s))
        return out

    parts = [p.strip() for p in re.split(r"[、，,]", item) if p.strip()]
    if len(parts) <= 1:
        return [item]

    out, buf, buf_types = [], "", set()
    for p in parts:
        pt = set(classify(p))
        if not buf:
            buf, buf_types = p, pt
            continue
        # R1a 三条判据；任一不满足 → 不切，并入缓冲段
        keep = (_is_tail(p)                       # ① 补足语／连词起首
                or len(p) < MIN_FRAGMENT          # ② 过短
                or pt == buf_types                # ③ 类型相同
                or "未分类" in pt
                or "未分类" in buf_types)
        if keep:
            buf = buf + "、" + p
            buf_types |= pt
        else:
            out.append(buf)
            buf, buf_types = p, pt
    if buf:
        out.append(buf)
    return out if len(out) > 1 else [item]


def is_generic(item):
    return any(g in item for g in GENERIC)


def n_parts(item):
    """原条目按顿号／逗号／分号切出的片段数。

    ≥3 时提示这可能是**复合条目**（如「旅游景区、旅游电子商务、旅行社、定制旅行、
    导游、酒店服务」实际含 5 个岗位群的任务），供人工扫读——脚本不敢据此自动切，
    因为「款式、色彩、材料」同样是 3 段却是一条任务。
    """
    return len([p for p in re.split(r"[、，,；;]", item) if p.strip()])


def build(standards, abbr):
    """standards: {专业名: {code, level, facing, abilities, certs}}；abbr: {专业名: 缩写}"""
    rows = []
    counter = {}
    for major, m in standards.items():
        if major not in abbr:
            raise KeyError("专业「%s」缺缩写，请在 majors.json 中补上" % major)
        for item in m["abilities"]:
            item = item.strip().rstrip("；;")
            if is_generic(item):
                continue
            frags = split_item(item)
            for frag in frags:
                counter[major] = counter.get(major, 0) + 1
                types = classify(frag)
                rows.append({
                    "major": major,
                    "code": m["code"],
                    "level": m["level"],
                    "tid": "%s%d" % (abbr[major], counter[major]),
                    "item": item,
                    "task": frag,
                    "types": types,
                    # R1b：拆分后仍跨多类型 → 提示需再拆一层
                    "split_hint": len(types) >= 2 and frag != item,
                    # 并列片段数：≥3 提示可能是复合条目，供人工扫读（不自动切）
                    "n_parts": n_parts(item),
                    "llm": None,
                    "robot": None,
                    "quad": "待定",
                    "src": "待判定",
                    "conf": "待判定",
                })
    return rows


def generic_rows(standards):
    """R3 单列：被剔除的通用素养条目，供教研组核对剔除是否合理。"""
    return [{"major": k, "item": i}
            for k, m in standards.items() for i in m["abilities"] if is_generic(i)]


def main():
    ap = argparse.ArgumentParser(description="标准文本 → 任务表（拆解与分类，不打分）")
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--standards", default=os.path.join(here, "assets", "sample", "standards.json"))
    ap.add_argument("--majors", default=os.path.join(here, "assets", "sample", "majors.json"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    standards = json.load(io.open(a.standards, encoding="utf-8"))
    majors = json.load(io.open(a.majors, encoding="utf-8"))
    abbr = {k: v["abbr"] for k, v in majors.items()}

    rows = build(standards, abbr)
    gen = generic_rows(standards)

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with io.open(a.out, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)

    print("任务 %d 条 ｜ 剔除通用素养 %d 条 ｜ 需再拆（split_hint）%d 条 ｜ "
          "疑似复合（并列≥3 段）%d 条"
          % (len(rows), len(gen), sum(1 for r in rows if r["split_hint"]),
             sum(1 for r in rows if r["n_parts"] >= 3)))
    for r in rows:
        flag = "  ⚠需再拆" if r["split_hint"] else (
            "  ◆疑似复合(%d段)" % r["n_parts"] if r["n_parts"] >= 3 else "")
        print("  %-4s %-12s %-14s %s%s"
              % (r["tid"], r["major"][:10], "/".join(r["types"]), r["task"][:44], flag))
    print("\nwrote %s" % a.out)


if __name__ == "__main__":
    main()
