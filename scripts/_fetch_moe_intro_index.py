# -*- coding: utf-8 -*-
"""抓取教育部「职业教育专业简介（2022 年修订）」全部专业类 PDF 链接。

来源页面：http://www.moe.gov.cn/s78/A07/zcs_ztzl/2017_zt06/17zt06_bznr/bznr_zdzyxxzyml/

页面结构（两层）：
    目录页 → 3 个层次 × 19 个专业大类 = 57 个子页
    子页   → 该大类下每个「专业类」一个 PDF（标签形如「7102 计算机类」）

输出：与 moe_pdfs_final.json 同构的扁平记录列表，
    {major_code, major_name, education_level, pdf_url, category}
其中 major_code 为 **4 位专业类代码**（本索引按「类」给 PDF，不是按专业）。

用法：
    python scripts/_fetch_moe_intro_index.py --out assets/moe_introduction_Vocational_Education_Majors.json
"""
import argparse
import io
import json
import os
import re
import sys
import time
import urllib.request

BASE = ("http://www.moe.gov.cn/s78/A07/zcs_ztzl/2017_zt06/17zt06_bznr/"
        "bznr_zdzyxxzyml/")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

LEVELS = [
    ("zhongzhi", "中等职业教育"),
    ("gaozhizhuan", "高等职业教育专科"),
    ("gaozhiben", "高等职业教育本科"),
]


def get(url, tries=3, timeout=60):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:
            if i == tries - 1:
                raise
            print("   重试 %d/%d（%s）" % (i + 1, tries, e), file=sys.stderr)
            time.sleep(2 * (i + 1))


def links(html):
    return [(m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip())
            for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                                 html, re.S | re.I)]


def main():
    ap = argparse.ArgumentParser(description="抓取职业教育专业简介 PDF 索引")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sleep", type=float, default=0.6, help="每次请求间隔秒数")
    a = ap.parse_args()

    print("① 读取目录页 %s" % BASE)
    idx = get(BASE)

    # 目录页里，「大类」链接紧跟在对应层次的标题链接之后
    subpages = []          # [(level_name, slug, category_name)]
    cur_level, cur_slug = None, None
    for href, txt in links(idx):
        h = href.strip()
        if not h.startswith("./") or h.endswith(".pdf"):
            continue
        parts = [p for p in h.strip("./").split("/") if p]
        if len(parts) == 1 and parts[0] in [k for k, _ in LEVELS]:
            cur_slug = parts[0]
            cur_level = dict(LEVELS)[cur_slug]
        elif len(parts) == 2 and cur_slug and parts[0] == cur_slug and "大类" in txt:
            subpages.append((cur_level, h, txt))
    print("   解析出 %d 个子页" % len(subpages))
    assert len(subpages) == 57, "子页数应为 57（3 层次 × 19 大类），实为 %d" % len(subpages)

    print("② 逐个抓取子页，提取专业类 PDF")
    recs, seen = [], set()
    for i, (level, rel, category) in enumerate(subpages, 1):
        url = urllib.request.urljoin(BASE, rel)
        if not url.endswith("/"):
            url += "/"
        html = get(url)
        n = 0
        for href, txt in links(html):
            if not href.lower().endswith(".pdf"):
                continue
            m = re.match(r"^(\d{4})\s*(.+)$", txt)
            if not m:
                print("   [警告] 标签无法解析：%r" % txt, file=sys.stderr)
                continue
            code, name = m.group(1), m.group(2).strip()
            if code in seen:
                print("   [警告] 类代码重复：%s（%s / %s）" % (code, name, category),
                      file=sys.stderr)
                continue
            seen.add(code)
            recs.append({
                "major_code": code,
                "major_name": name,
                "education_level": level,
                "pdf_url": urllib.request.urljoin(url, href),
                "category": category,
            })
            n += 1
        print("   [%2d/%d] %-12s %-10s -> %d 个类" % (i, len(subpages), level, category, n))
        time.sleep(a.sleep)

    recs.sort(key=lambda r: (r["education_level"], r["major_code"]))
    d = os.path.dirname(os.path.abspath(a.out))
    if d:
        os.makedirs(d, exist_ok=True)
    with io.open(a.out, "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False, indent=1)

    import collections
    c = collections.Counter(r["education_level"] for r in recs)
    print("\n③ 写入 %s" % a.out)
    print("   共 %d 条（按专业类）" % len(recs))
    for _, lv in LEVELS:
        print("     %-14s %d" % (lv, c.get(lv, 0)))


if __name__ == "__main__":
    main()
