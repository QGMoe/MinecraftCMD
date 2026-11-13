"""从主稿 docx 无损提取段落流（原文层的 docx 部分）。

设计要点
- 直接遍历 document.xml，不依赖 python-docx 的段落 API（它会漏掉超链接里的文字）。
- 文本框在 mc:AlternateContent 里有 Choice 和 Fallback 两份，只取 Choice。
- 域代码：指令文字（instrText）不算正文，只记录在 field 里；结果文字照常算正文。
- 相邻且格式完全相同的 run 合并，只丢掉 run 的切分边界（没有语义），不丢字符。
- 输出的每个段落都带 text（纯文本）与 sha256，便于校验。

用法：python3 -I docx_extract.py <主稿.docx> <输出.json>
"""
import hashlib
import json
import posixpath
import sys
import zipfile

from lxml import etree

NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture',
    'mc': 'http://schemas.openxmlformats.org/markup-compatibility/2006',
    'wps': 'http://schemas.microsoft.com/office/word/2010/wordprocessingShape',
    'v': 'urn:schemas-microsoft-com:vml',
}
W = '{%s}' % NS['w']
R = '{%s}' % NS['r']
MC = '{%s}' % NS['mc']

# 不影响正文的元素：直接跳过
SKIP = {W + 'proofErr', W + 'lastRenderedPageBreak', W + 'bookmarkEnd', W + 'pPr', W + 'rPr',
        W + 'noProof', W + 'permStart', W + 'permEnd'}


def attr(el, name):
    return el.get(W + name) if el is not None else None


class Ctx:
    def __init__(self, z):
        self.z = z
        self.rels = self._rels('word/_rels/document.xml.rels')
        self.styles = self._styles()
        self.fld_stack = []  # 嵌套域：每项 {'instr': str, 'phase': 'instr'|'result'}

    def _rels(self, path):
        root = etree.fromstring(self.z.read(path))
        out = {}
        for rel in root:
            out[rel.get('Id')] = {'target': rel.get('Target'), 'mode': rel.get('TargetMode'),
                                  'type': rel.get('Type').rsplit('/', 1)[-1]}
        return out

    def _styles(self):
        root = etree.fromstring(self.z.read('word/styles.xml'))
        out = {}
        for st in root.iter(W + 'style'):
            name = st.find(W + 'name')
            out[st.get(W + 'styleId')] = name.get(W + 'val') if name is not None else st.get(W + 'styleId')
        return out


def run_props(rpr, ctx):
    p = {}
    if rpr is None:
        return p
    for child in rpr:
        tag = etree.QName(child).localname
        val = child.get(W + 'val')
        if tag == 'rStyle':
            p['style'] = ctx.styles.get(val, val)
        elif tag == 'rFonts':
            f = {k: child.get(W + k) for k in ('ascii', 'eastAsia', 'hAnsi', 'cs', 'hint') if child.get(W + k)}
            if f:
                p['font'] = f
        elif tag in ('b', 'i', 'strike', 'dstrike', 'caps', 'smallCaps', 'vanish', 'bCs', 'iCs'):
            p[tag] = val not in ('0', 'false')
        elif tag in ('u', 'color', 'highlight', 'sz', 'szCs', 'vertAlign', 'lang', 'spacing', 'w', 'kern', 'position'):
            p[tag] = val if val is not None else {k.split('}')[1]: v for k, v in child.attrib.items()}
        elif tag == 'shd':
            p['shd'] = {k.split('}')[1]: v for k, v in child.attrib.items()}
        elif tag in ('noProof', 'webHidden', 'specVanish', 'rtl', 'cs', 'eastAsianLayout'):
            p.setdefault('misc', []).append(tag)
        else:
            p.setdefault('other', []).append(tag)
    return p


def para_props(ppr, ctx):
    p = {}
    if ppr is None:
        return p
    for child in ppr:
        tag = etree.QName(child).localname
        if tag == 'pStyle':
            p['style'] = ctx.styles.get(child.get(W + 'val'), child.get(W + 'val'))
        elif tag in ('jc', 'outlineLvl'):
            p[tag] = child.get(W + 'val')
        elif tag in ('ind', 'spacing'):
            p[tag] = {k.split('}')[1]: v for k, v in child.attrib.items()}
        elif tag == 'numPr':
            p['num'] = {etree.QName(c).localname: c.get(W + 'val') for c in child}
        elif tag == 'rPr':
            mark = run_props(child, ctx)
            if mark:
                p['markRun'] = mark
        elif tag == 'sectPr':
            p['sectPr'] = True
        else:
            p.setdefault('other', []).append(tag)
    return p


def media_path(rid, ctx):
    rel = ctx.rels.get(rid)
    if not rel:
        return None
    return posixpath.normpath(posixpath.join('word', rel['target']))


def drawing_items(el, ctx):
    """w:drawing（或 mc:Choice 内的 drawing）→ 图片或文本框条目。"""
    items = []
    for cont in el:
        kind = etree.QName(cont).localname  # inline | anchor
        ext = cont.find('wp:extent', NS)
        doc = cont.find('wp:docPr', NS)
        base = {'placement': kind,
                'extent': {'cx': ext.get('cx'), 'cy': ext.get('cy')} if ext is not None else None,
                'name': doc.get('name') if doc is not None else None,
                'descr': doc.get('descr') if doc is not None else None}
        blip = cont.find('.//a:blip', NS)
        if blip is not None:
            rid = blip.get(R + 'embed')
            items.append(dict(base, kind='image', media=media_path(rid, ctx)))
        txbx = cont.find('.//wps:txbx/w:txbxContent', NS)
        if txbx is not None:
            items.append(dict(base, kind='textbox', paragraphs=[paragraph(p, ctx) for p in txbx.findall('w:p', NS)]))
        if blip is None and txbx is None:
            items.append(dict(base, kind='shape'))
    return items


def run_items(r, ctx, extra_props=None):
    props = run_props(r.find(W + 'rPr'), ctx)
    if extra_props:
        props = dict(props, **extra_props)
    out = []
    for child in r:
        tag = child.tag
        if tag in SKIP:
            continue
        name = etree.QName(child).localname
        in_instr = bool(ctx.fld_stack) and ctx.fld_stack[-1]['phase'] == 'instr'
        if name == 'fldChar':
            t = child.get(W + 'fldCharType')
            if t == 'begin':
                ctx.fld_stack.append({'instr': '', 'phase': 'instr'})
                out.append({'field': 'begin'})
            elif t == 'separate':
                ctx.fld_stack[-1]['phase'] = 'result'
                out.append({'field': 'separate', 'instr': ctx.fld_stack[-1]['instr']})
            elif t == 'end':
                f = ctx.fld_stack.pop()
                out.append({'field': 'end', 'instr': f['instr']})
            continue
        if name == 'instrText':
            ctx.fld_stack[-1]['instr'] += child.text or ''
            continue
        if in_instr:
            # 域指令阶段的其他内容不算正文
            out.append({'fieldInstrContent': name})
            continue
        if name == 't':
            out.append({'t': child.text or '', 'p': props})
        elif name == 'tab':
            out.append({'t': '\t', 'p': props})
        elif name == 'br':
            out.append({'br': child.get(W + 'type') or 'textWrapping', 'p': props})
        elif name == 'cr':
            out.append({'br': 'cr', 'p': props})
        elif name == 'noBreakHyphen':
            out.append({'t': '‑', 'p': props})
        elif name == 'softHyphen':
            out.append({'t': '­', 'p': props})
        elif name == 'sym':
            out.append({'sym': {'font': child.get(W + 'font'), 'char': child.get(W + 'char')}, 'p': props})
        elif name == 'drawing':
            out.extend(drawing_items(child, ctx))
        elif tag == MC + 'AlternateContent':
            choice = child.find('mc:Choice', NS)
            if choice is not None:
                for c in choice:
                    if etree.QName(c).localname == 'drawing':
                        out.extend(drawing_items(c, ctx))
                    else:
                        out.append({'unknown': 'mc:Choice/' + etree.QName(c).localname})
        elif name == 'pict':
            out.append({'unknown': 'w:pict'})
        else:
            out.append({'unknown': name})
    return out


def inline_items(parent, ctx, link=None):
    out = []
    for child in parent:
        tag = child.tag
        if tag in SKIP:
            continue
        name = etree.QName(child).localname
        if name == 'r':
            items = run_items(child, ctx)
            if link:
                for it in items:
                    it['link'] = link
            out.extend(items)
        elif name == 'hyperlink':
            rid = child.get(R + 'id')
            lk = {}
            if rid:
                lk['url'] = ctx.rels.get(rid, {}).get('target')
            if child.get(W + 'anchor'):
                lk['anchor'] = child.get(W + 'anchor')
            out.extend(inline_items(child, ctx, link=lk or {'empty': True}))
        elif name == 'bookmarkStart':
            out.append({'bookmark': child.get(W + 'name')})
        elif name in ('smartTag', 'ins', 'customXml', 'sdtContent', 'fldSimple'):
            out.append({'wrapper': name})
            out.extend(inline_items(child, ctx, link=link))
        elif name == 'sdt':
            out.extend(inline_items(child.find(W + 'sdtContent'), ctx, link=link))
        elif name == 'del':
            out.append({'deleted': True})
        else:
            out.append({'unknown': name})
    return out


def merge(items):
    """合并相邻、格式与链接都相同的文本条目。"""
    out = []
    for it in items:
        if out and 't' in it and 't' in out[-1] and it.get('p') == out[-1].get('p') and it.get('link') == out[-1].get('link'):
            out[-1]['t'] += it['t']
        else:
            out.append(dict(it))
    return out


def plain_text(items):
    s = []
    for it in items:
        if 't' in it:
            s.append(it['t'])
        elif 'br' in it:
            s.append('\n')
    return ''.join(s)


def paragraph(p, ctx):
    ppr = para_props(p.find(W + 'pPr'), ctx)
    items = merge(inline_items(p, ctx))
    text = plain_text(items)
    return {'ppr': ppr, 'c': items, 'text': text,
            'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}


def extract(docx_path):
    z = zipfile.ZipFile(docx_path)
    ctx = Ctx(z)
    body = etree.fromstring(z.read('word/document.xml')).find(W + 'body')
    paras = []
    for i, el in enumerate(body):
        name = etree.QName(el).localname
        if name == 'p':
            para = paragraph(el, ctx)
            para['i'] = len(paras)
            paras.append(para)
        elif name == 'sectPr':
            continue
        else:
            paras.append({'i': len(paras), 'unknownBlock': name})
    if ctx.fld_stack:
        raise SystemExit('域未闭合：%r' % ctx.fld_stack)
    return {'source': posixpath.basename(docx_path), 'paragraphs': paras}


def main():
    src, out = sys.argv[1], sys.argv[2]
    data = extract(src)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    unknown = [p['i'] for p in data['paragraphs'] if 'unknownBlock' in p or any('unknown' in c for c in p.get('c', []))]
    print('段落', len(data['paragraphs']), '含未识别元素的段落', unknown[:20], len(unknown))


if __name__ == '__main__':
    main()
