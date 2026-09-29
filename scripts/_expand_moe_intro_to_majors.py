# -*- coding: utf-8 -*-
"""把「专业类」级索引展开为「专业」级索引。

输入：assets/moe_introduction_Vocational_Education_Majors.json（275 个专业类）
做法：逐个下载该类的简介 PDF，从正文里提取 `专业代码 X` / `专业名称 Y` 配对，
      展开为一条一专业；同一类的所有专业共用同一个 pdf_url。

输出：仍是 5 个字段，但 major_code 由 4 位专业类代码变为 6 位专业代码。

用法：
    python scripts/_expand_moe_intro_to_majors.py \
        --index assets/moe_introduction_Vocational_Education_Majors.json \
        --cache E:/tmp/moe_intro_pdf --out <输出 json>
"""
import argparse
import io
import json
import os
import re
import sys
import time
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

# 「专业代码 610101」+「专业名称 种子生产技术」成对出现。
# 注意 \s+ 而非 \s*\n?\s*——有的转换稿在两者之间留了空行。
PAIR = re.compile(r"专业代码\s*([0-9]{6}[A-Z]?)\s*\n?\s*专业名称\s*([^\n]+)")

# 专业名只应含汉字、字母、数字、括号与连接符；其余（PDF 抽出的上标杂字等）清掉
CLEAN = re.compile(r"[^\u4e00-\u9fffA-Za-z0-9（）()·\-]")


def fetch(url, cache_dir, tries=3, timeout=120):
    os.makedirs(cache_dir, exist_ok=True)
    local = os.path.join(cache_dir, url.rsplit("/", 1)[-1])
    if os.path.isfile(local) and os.path.getsize(local) > 1000:
        return open(local, "rb").read()
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            with open(local, "wb") as f:
                f.write(data)
            return data
        except Exception as e:
            if i == tries - 1:
                raise
            print("      重试 %d/%d（%s）" % (i + 1, tries, e), file=sys.stderr)
            time.sleep(2 * (i + 1))


def extract_pairs(pdf_bytes):
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(pdf_bytes))
    txt = "\n".join((p.extract_text() or "") for p in r.pages)
    # 把连续空格/制表/全角空格压成单空格，但保留换行（配对可能跨行）
    txt = re.sub(r"[ \t\u3000]+", " ", txt)
    out = []
    for code, name in PAIR.findall(txt):
        name = CLEAN.sub("", re.sub(r"\s+", "", name)).strip()
        if name and (not out or out[-1][0] != code):
            out.append((code, name))
    return out


def main():
    ap = argparse.ArgumentParser(description="专业类索引 → 专业级索引")
    ap.add_argument("--index", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", default=os.path.join(os.path.expanduser("~"), ".cache",
                                                    "moe_intro_pdf"))
    ap.add_argument("--sleep", type=float, default=0.3)
    a = ap.parse_args()

    src = json.load(io.open(a.index, encoding="utf-8"))
    print("① 读入 %d 个专业类" % len(src))

    out, problems = [], []
    for i, rec in enumerate(src, 1):
        try:
            pdf = fetch(rec["pdf_url"], a.cache)
            pairs = extract_pairs(pdf)
        except Exception as e:
            problems.append((rec["major_code"], "下载/解析失败：%s" % e))
            print("   [%3d/%d] %s %s -> 失败：%s"
                  % (i, len(src), rec["major_code"], rec["major_name"], e))
            continue

        cls = rec["major_code"]
        if not pairs:
            problems.append((cls, "PDF 未提取到任何专业（可能是扫描件）"))
        bad = [c for c, _ in pairs if not c.startswith(cls)]
        if bad:
            problems.append((cls, "提取到的专业代码不以类代码开头：%s" % bad[:5]))

        for code, name in pairs:
            out.append({
                "major_code": code,
                "major_name": name,
                "education_level": rec["education_level"],
                "pdf_url": rec["pdf_url"],
                "category": rec["category"],
            })
        print("   [%3d/%d] %s %-12s -> %2d 个专业"
              % (i, len(src), cls, rec["major_name"], len(pairs)))
        time.sleep(a.sleep)

    # 去重（同代码保留首见）
    seen, uniq = set(), []
    for r in out:
        if r["major_code"] in seen:
            continue
        seen.add(r["major_code"])
        uniq.append(r)
    uniq.sort(key=lambda r: (r["education_level"], r["major_code"]))

    d = os.path.dirname(os.path.abspath(a.out))
    if d:
        os.makedirs(d, exist_ok=True)
    with io.open(a.out, "w", encoding="utf-8") as f:
        json.dump(uniq, f, ensure_ascii=False, indent=1)

    import collections
    c = collections.Counter(r["education_level"] for r in uniq)
    print("\n② 写入 %s" % a.out)
    print("   %d 条专业记录（展开前 %d 个类；去重丢弃 %d 条）"
          % (len(uniq), len(src), len(out) - len(uniq)))
    for lv in ["中等职业教育", "高等职业教育专科", "高等职业教育本科"]:
        print("     %-14s %d" % (lv, c.get(lv, 0)))
    if problems:
        print("\n③ 异常 %d 处：" % len(problems))
        for cls, why in problems:
            print("   %s：%s" % (cls, why))
    else:
        print("\n③ 无异常")


if __name__ == "__main__":
    main()
