# -*- coding: utf-8 -*-
"""打包分发：把技能目录复制到 dist/ 并打成 zip。

剔除 __pycache__ 与 .pyc；保留自检脚本（分发后仍可用来自证环境完好）。

用法：python scripts/_pack.py
"""
import io
import os
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NAME = os.path.basename(ROOT)
DIST = os.path.join(os.path.dirname(ROOT), "dist")
SKIP_DIRS = {"__pycache__", ".git", "dist"}


def main():
    target = os.path.join(DIST, NAME)
    if os.path.exists(target):
        shutil.rmtree(target)
    os.makedirs(DIST, exist_ok=True)
    shutil.copytree(ROOT, target,
                    ignore=shutil.ignore_patterns(*SKIP_DIRS, "*.pyc"))

    zpath = os.path.join(DIST, NAME + ".zip")
    n = 0
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, DIST))
                n += 1

    size = sum(os.path.getsize(os.path.join(r, f))
               for r, d, fs in os.walk(target) for f in fs)
    print("目录 %s  %d 个文件  %.1f KB" % (target, n, size / 1024))
    print("压缩包 %s  %.1f KB" % (zpath, os.path.getsize(zpath) / 1024))
    # 预期体积约 930 KB：onet_ari.json（106 KB）+ moe_major_index.json（168 KB）
    # + moe_introduction_Vocational_Education_Majors.json（406 KB）+ 样例与代码。
    # 超过 1.3 MB 说明多半误打包了大数据文件（如 occupation-analysis 的 moe_pdfs_md，4 MB）。
    if size > 1300 * 1024:
        print("[提醒] 目录超过 1.3 MB（预期约 930 KB），检查是否误打包了大数据文件。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
