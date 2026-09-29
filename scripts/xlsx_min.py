# -*- coding: utf-8 -*-
"""最小 xlsx 写入器 —— **仅用标准库**，不依赖 openpyxl / xlsxwriter。

为什么自己写：本技能的原则是"数据与脚本随技能分发，不联网、不装包"。复核清单
要交给教研组填写，`.csv` 无法携带"数据有效性"（下拉列表），只有 `.xlsx` 可以。
若为此引入 openpyxl 这一硬依赖，其他学校拿到技能就得先装包。核心用例只需
"多个工作表 + 文本/数字/公式 + 列宽 + 冻结窗格 + 加粗表头 + 下拉列表"，
这部分 XML 是稳定的，自己生成即可。

支持的样式（`Sheet.row(..., style="header")` 或逐格 `styles=[...]`）：
    default / header / bold / wrap / num2 / note / title / center

用法：
    wb = Workbook()
    ws = wb.sheet("一、待判定", freeze="A2", widths={"A": 10, "D": 40})
    ws.row(["编号", "任务"], style="header")
    ws.row(["汽1", "使用量具"], styles=["center", "wrap"])
    ws.validate("C2:C40", ["Ⅰ 仅机器人高", "Ⅱ 双高"], title="象限判定")
    ws.formula("K2", '=IF(A2="","",A2*2)')
    wb.save("out.xlsx")

XML 结构对齐 Excel 生成的文件（部件清单、元素次序、样式索引），避免打开时提示"需要修复"。
"""
import os
import re
import zipfile
from xml.sax.saxutils import escape, quoteattr

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"

# 非法控制字符会让 Excel 拒绝打开
_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def col_letter(idx):
    """0 → A，25 → Z，26 → AA。"""
    s = ""
    idx += 1
    while idx:
        idx, r = divmod(idx - 1, 26)
        s = chr(65 + r) + s
    return s


def _t(v):
    """单元格文本 → XML 安全的字符串。"""
    if v is None:
        return ""
    return _ILLEGAL.sub("", str(v))


# ── 样式表：索引与下面 STYLE_XFS / fonts / fills / borders 一一对应 ──
STYLES = {
    "default": 0,
    "header": 1,   # 加粗 + 蓝底 + 居中 + 细框
    "bold": 2,     # 加粗
    "wrap": 3,     # 自动换行 + 顶端对齐 + 细框
    "num2": 4,     # 两位小数 + 居中 + 细框
    "note": 5,     # 灰色斜体小字
    "title": 6,    # 大号加粗
    "center": 7,   # 居中 + 细框
}


class Sheet(object):
    def __init__(self, name, freeze=None, widths=None, header_rows=1):
        self.name = name
        self.freeze = freeze
        self.widths = dict(widths or {})
        self.header_rows = header_rows
        self.rows = []           # [[cell, ...]]，cell = (value, style_idx) | (("f", 公式), style)
        self.validations = []

    # ── 写内容 ──
    def row(self, values, style=None, styles=None):
        """style 施加于整行；styles 逐格覆盖。值为 None 写空格。"""
        s = STYLES.get(style, 0) if style else 0
        out = []
        for i, v in enumerate(values):
            si = s
            if styles and i < len(styles) and styles[i]:
                si = STYLES.get(styles[i], 0)
            out.append((v, si))
        self.rows.append(out)
        return self

    def blank(self, n=1):
        for _ in range(n):
            self.rows.append([])
        return self

    def formula(self, ref, text, style="wrap"):
        """在指定格写公式（ref 形如 'K2'）。行号小于当前行数时定位到已有行。"""
        m = re.match(r"^([A-Z]+)(\d+)$", ref)
        if not m:
            raise ValueError("非法单元格引用：%s" % ref)
        col, rn = m.group(1), int(m.group(2))
        ci = 0
        for ch in col:
            ci = ci * 26 + (ord(ch) - 64)
        ci -= 1
        while len(self.rows) < rn:
            self.rows.append([])
        target = self.rows[rn - 1]
        while len(target) <= ci:
            target.append((None, 0))
        target[ci] = (("f", text), STYLES.get(style, 0))
        return self

    def width(self, col, w):
        self.widths[col] = w
        return self

    # ── 数据有效性（下拉）──
    def validate(self, ref, options, title="", msg="", error_title="", error_msg="",
                 style="stop"):
        """ref 形如 'H3:H40'；options 为下拉选项列表（不得含逗号）。"""
        assert options, "选项不能为空"
        for o in options:
            if "," in str(o):
                raise ValueError("下拉选项不得含英文逗号：%r" % o)
        self.validations.append({
            "ref": ref, "options": [str(o) for o in options],
            "title": title, "msg": msg, "error_title": error_title,
            "error_msg": error_msg, "style": style,
        })
        return self

    # ── 序列化 ──
    def _cols_xml(self):
        if not self.widths:
            return ""
        out = []
        for col in sorted(self.widths, key=lambda c: (len(c), c)):
            ci = 0
            for ch in col:
                ci = ci * 26 + (ord(ch) - 64)
            out.append('<col min="%d" max="%d" width="%s" customWidth="1"/>'
                       % (ci, ci, self.widths[col]))
        return "<cols>%s</cols>" % "".join(out)

    def _cell_xml(self, ci, ri, cell):
        v, si = cell
        ref = "%s%d" % (col_letter(ci), ri)
        sa = ' s="%d"' % si if si else ""
        if isinstance(v, tuple) and v and v[0] == "f":
            f = _t(v[1])
            if f.startswith("="):        # <f> 内不写前导等号（那是 Excel 的输入约定）
                f = f[1:]
            return '<c r="%s"%s><f>%s</f></c>' % (ref, sa, escape(f))
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return '<c r="%s"%s><v>%s</v></c>' % (ref, sa, v)
        return '<c r="%s"%s t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' \
               % (ref, sa, escape(_t(v)))

    def _sheet_data(self):
        out = []
        for ri, row in enumerate(self.rows, 1):
            cells = "".join(self._cell_xml(ci, ri, c) for ci, c in enumerate(row))
            out.append('<row r="%d">%s</row>' % (ri, cells))
        return "<sheetData>%s</sheetData>" % "".join(out)

    def _views(self):
        if not self.freeze:
            return '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
        m = re.match(r"^([A-Z]+)(\d+)$", self.freeze)
        col, rn = m.group(1), int(m.group(2))
        ci = 0
        for ch in col:
            ci = ci * 26 + (ord(ch) - 64)
        panes = []
        if rn > 1:
            panes.append('ySplit="%d"' % (rn - 1))
        if ci > 1:
            panes.append('xSplit="%d"' % (ci - 1))
        panes.append('topLeftCell="%s"' % self.freeze)
        pane = "bottomRight" if rn > 1 and ci > 1 else ("bottomLeft" if rn > 1 else "topRight")
        panes.append('activePane="%s"' % pane)
        panes.append('state="frozen"')
        return ('<sheetViews><sheetView workbookViewId="0"><pane %s/>'
                '<selection pane="%s" activeCell="%s" sqref="%s"/></sheetView></sheetViews>'
                % (" ".join(panes), pane, self.freeze, self.freeze))

    def _dimension(self):
        ncells = max([len(r) for r in self.rows] or [1])
        return '<dimension ref="A1:%s%d"/>' % (col_letter(max(ncells - 1, 0)),
                                               max(len(self.rows), 1))

    def _validations(self):
        if not self.validations:
            return ""
        items = []
        for v in self.validations:
            attrs = ['sqref=%s' % quoteattr(v["ref"]),
                     'type="list"', 'allowBlank="1"',
                     'showDropDown="0"',          # 0 = 显示下拉箭头（该属性名与含义相反）
                     'showInputMessage="1"', 'showErrorMessage="1"',
                     'errorStyle="stop"']
            if v["error_title"]:
                attrs.append('errorTitle=%s' % quoteattr(v["error_title"]))
            if v["error_msg"]:
                attrs.append('error=%s' % quoteattr(v["error_msg"]))
            if v["title"]:
                attrs.append('promptTitle=%s' % quoteattr(v["title"]))
            if v["msg"]:
                attrs.append('prompt=%s' % quoteattr(v["msg"]))
            opts = ",".join(v["options"])
            items.append("<dataValidation %s><formula1>%s</formula1></dataValidation>"
                         % (" ".join(attrs), escape('"%s"' % opts)))
        return '<dataValidations count="%d">%s</dataValidations>' % (len(items), "".join(items))

    def to_xml(self):
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<worksheet xmlns="%s">%s%s<sheetFormatPr defaultRowHeight="15"/>'
                '%s%s%s%s</worksheet>'
                % (NS_MAIN, self._dimension(), self._views(), self._cols_xml(),
                   self._sheet_data(), self._validations(), ""))


STYLES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="%s">'
    '<numFmts count="0"/>'
    # fonts: 0 默认 / 1 加粗 / 2 大号加粗 / 3 灰色斜体
    '<fonts count="4">'
    '<font><name val="\u7b49\u7ebf"/><family val="2"/><charset val="134"/><sz val="11"/></font>'
    '<font><b/><name val="\u7b49\u7ebf"/><family val="2"/><charset val="134"/><sz val="11"/></font>'
    '<font><b/><name val="\u7b49\u7ebf"/><family val="2"/><charset val="134"/><sz val="14"/></font>'
    '<font><i/><color rgb="FF808080"/><name val="\u7b49\u7ebf"/><family val="2"/>'
    '<charset val="134"/><sz val="10"/></font>'
    '</fonts>'
    # fills: 0 无 / 1 gray125（必备占位） / 2 表头蓝 / 3 浅灰
    '<fills count="4">'
    '<fill><patternFill/></fill>'
    '<fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFDCE6F0"/>'
    '<bgColor indexed="64"/></patternFill></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFF2F2F2"/>'
    '<bgColor indexed="64"/></patternFill></fill>'
    '</fills>'
    '<borders count="2">'
    '<border><left/><right/><top/><bottom/><diagonal/></border>'
    '<border><left style="thin"><color rgb="FFBFBFBF"/></left>'
    '<right style="thin"><color rgb="FFBFBFBF"/></right>'
    '<top style="thin"><color rgb="FFBFBFBF"/></top>'
    '<bottom style="thin"><color rgb="FFBFBFBF"/></bottom><diagonal/></border>'
    '</borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="8">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'                       # 0 default
    '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1"'
    ' applyFill="1" applyBorder="1" applyAlignment="1">'
    '<alignment horizontal="center" vertical="center" wrapText="1"/></xf>'                 # 1 header
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'          # 2 bold
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"'
    ' applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'                     # 3 wrap
    '<xf numFmtId="2" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1"'
    ' applyBorder="1" applyAlignment="1"><alignment horizontal="center"/></xf>'             # 4 num2
    '<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1"'
    ' applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'                     # 5 note
    '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>'          # 6 title
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"'
    ' applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>'           # 7 center
    '</cellXfs>'
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
    '<dxfs count="0"/>'
    '<tableStyles count="0" defaultTableStyle="TableStyleMedium9"'
    ' defaultPivotStyle="PivotStyleLight16"/>'
    '</styleSheet>' % NS_MAIN)


class Workbook(object):
    def __init__(self, creator="dual-exposure-analysis"):
        self.sheets = []
        self.creator = creator

    def sheet(self, name, **kw):
        s = Sheet(name, **kw)
        self.sheets.append(s)
        return s

    def _content_types(self):
        ws = "".join(
            '<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % (i + 1)
            for i in range(len(self.sheets)))
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-'
                'package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.'
                'openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                '%s'
                '<Override PartName="/xl/styles.xml" ContentType="application/vnd.'
                'openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                '<Override PartName="/docProps/core.xml" ContentType="application/vnd.'
                'openxmlformats-package.core-properties+xml"/>'
                '<Override PartName="/docProps/app.xml" ContentType="application/vnd.'
                'openxmlformats-officedocument.extended-properties+xml"/>'
                '</Types>' % ws)

    def _root_rels(self):
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="%s">'
                '<Relationship Id="rId1" Type="%s/officeDocument" Target="xl/workbook.xml"/>'
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/'
                '2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
                '<Relationship Id="rId3" Type="%s/extended-properties" Target="docProps/app.xml"/>'
                '</Relationships>' % (NS_PKG_REL, NS_REL, NS_REL))

    def _workbook_rels(self):
        items = "".join(
            '<Relationship Id="rId%d" Type="%s/worksheet" Target="worksheets/sheet%d.xml"/>'
            % (i + 1, NS_REL, i + 1) for i in range(len(self.sheets)))
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="%s">%s'
                '<Relationship Id="rId%d" Type="%s/styles" Target="styles.xml"/>'
                '</Relationships>' % (NS_PKG_REL, items, len(self.sheets) + 1, NS_REL))

    def _workbook(self):
        sheets = "".join(
            '<sheet name=%s sheetId="%d" r:id="rId%d"/>'
            % (quoteattr(s.name), i + 1, i + 1) for i, s in enumerate(self.sheets))
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="%s" xmlns:r="%s">'
                '<bookViews><workbookView activeTab="0"/></bookViews>'
                '<sheets>%s</sheets></workbook>' % (NS_MAIN, NS_REL, sheets))

    def save(self, path):
        d = os.path.dirname(os.path.abspath(path))
        if d:
            os.makedirs(d, exist_ok=True)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", self._content_types())
            z.writestr("_rels/.rels", self._root_rels())
            z.writestr("docProps/core.xml",
                       '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                       '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/'
                       '2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/'
                       '1.1/" xmlns:dcterms="http://purl.org/dc/terms/">'
                       '<dc:creator>%s</dc:creator><cp:lastModifiedBy>%s</cp:lastModifiedBy>'
                       '</cp:coreProperties>' % (escape(self.creator), escape(self.creator)))
            z.writestr("docProps/app.xml",
                       '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                       '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/'
                       '2006/extended-properties"><Application>%s</Application></Properties>'
                       % escape(self.creator))
            z.writestr("xl/workbook.xml", self._workbook())
            z.writestr("xl/_rels/workbook.xml.rels", self._workbook_rels())
            z.writestr("xl/styles.xml", STYLES_XML)
            for i, s in enumerate(self.sheets):
                z.writestr("xl/worksheets/sheet%d.xml" % (i + 1), s.to_xml())
        return path


if __name__ == "__main__":
    wb = Workbook()
    ws = wb.sheet("测试", freeze="A2", widths={"A": 10, "B": 30})
    ws.row(["编号", "任务"], style="header")
    ws.row(["汽1", "使用量具"], styles=["center", "wrap"])
    ws.validate("C2:C9", ["Ⅰ 仅机器人高", "Ⅱ 双高"])
    wb.save("E:/tmp/_xlsxmin_demo.xlsx")
    print("wrote E:/tmp/_xlsxmin_demo.xlsx")
