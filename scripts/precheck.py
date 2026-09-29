# -*- coding: utf-8 -*-
"""环境与数据预检。

核心项缺失 → ok=False（后续步骤会失败，必须先补）；可选项缺失只提示，不阻塞。

用法：
    python scripts/precheck.py
    python scripts/precheck.py --json
"""
import argparse
import importlib.util
import json
import os
import sys

CORE = [
    "onet_ari.json",
    "moe_major_index.json",
    "moe_introduction_Vocational_Education_Majors.json",
    "sample/majors.json",
    "sample/standards.json",
    "sample/mapping.json",
    "sample/tasks.json",
    "templates/report.html.j2",
]

# 可选增强：本机若已装 occupation-analysis，可用其中国职业大典作映射交叉校验
OPTIONAL = [
    (
        "occupation_dictionary",
        os.path.join(
            os.path.expanduser("~"), ".agents", "skills", "occupation-analysis",
            "assets", "occupation_dictionary_split",
        ),
        "中国职业大典分册（用于映射增强与交叉校验；缺失不影响运行）",
    ),
    (
        "occupation_analysis_skill",
        os.path.join(
            os.path.expanduser("~"), ".workbuddy-ai", "skills", "occupation-analysis",
            "assets", "occupation_dictionary_split",
        ),
        "中国职业大典分册（WorkBuddy 技能目录副本）",
    ),
    (
        "occupation_analysis_moe_md",
        os.path.join(
            os.path.expanduser("~"), ".workbuddy-ai", "skills", "occupation-analysis",
            "assets", "moe_pdfs_md",
        ),
        "已转好的《专业简介》MD 全文（275 个类 / 1349 个专业，每个专业一个完整结构），"
        "可省去下载解析 PDF。本机没有时从 "
        "https://github.com/flyboat403/occupation-analysis/tree/main/assets/moe_pdfs_md 获取",
    ),
]


def run(assets_dir):
    files = []
    for rel in CORE:
        p = os.path.join(assets_dir, rel.replace("/", os.sep))
        exists = os.path.isfile(p)
        files.append({
            "path": rel,
            "ok": exists and os.path.getsize(p) > 0,
            "size": os.path.getsize(p) if exists else 0,
        })

    mpl = importlib.util.find_spec("matplotlib")
    # 写 xlsx 用自带的 xlsx_min（纯标准库）；只有「读回教研组填写的 xlsx」需要 openpyxl
    opx = importlib.util.find_spec("openpyxl")

    optional = []
    for name, path, note in OPTIONAL:
        optional.append({
            "name": name,
            "found": os.path.isdir(path),
            "path": path,
            "note": note,
        })

    return {
        "ok": all(f["ok"] for f in files) and mpl is not None,
        "python": "%d.%d.%d" % sys.version_info[:3],
        "python_ok": sys.version_info >= (3, 8),
        "matplotlib": "found" if mpl else None,
        "openpyxl": "found" if opx else None,
        "files": files,
        "optional": optional,
    }


def main():
    ap = argparse.ArgumentParser(description="双暴露度分析技能 · 环境与数据预检")
    ap.add_argument(
        "--assets",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets"),
        help="assets 目录（默认取技能自带）",
    )
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    a = ap.parse_args()

    r = run(a.assets)

    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print("Python %s %s" % (r["python"], "" if r["python_ok"] else "（需要 3.8+）"))
        print("[%s] matplotlib%s" % ("OK" if r["matplotlib"] else "X",
                                     "" if r["matplotlib"] else "  ← 出图必需，请 pip install matplotlib"))
        print("[%s] openpyxl%s"
              % ("OK" if r["openpyxl"] else "·",
                 "" if r["openpyxl"] else "  ← 仅「读回教研组填写的 xlsx」需要；"
                                              "生成 xlsx 不需要（pip install openpyxl）"))
        for f in r["files"]:
            print("[%s] %-34s %s" % ("OK" if f["ok"] else "X", f["path"],
                                     "%d B" % f["size"] if f["size"] else "缺失"))
        for o in r["optional"]:
            print("[%s] %-28s %s" % ("OK" if o["found"] else "·", o["name"], o["note"]))

    sys.exit(0 if r["ok"] else 1)


if __name__ == "__main__":
    main()
