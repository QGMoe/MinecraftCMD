"""用与 docx_extract.py 不同的方法独立核对：提取结果的字符是否与 docx 一致。

独立方法：按文档顺序遍历所有 w:t / w:tab / w:br 等文本元素，
跳过 mc:Fallback 内的内容与域指令文字，拼出全文；
再把提取结果（含文本框内段落，按出现位置展开）拼成全文，两者逐字比较。

用法：python3 -I docx_crosscheck.py <主稿.docx> <提取结果.json>
"""
import json
import sys
import zipfile

from lxml import etree

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
MC = '{http://schemas.openxmlformats.org/markup-compatibility/2006}'


def independent_text(docx):
    root = etree.fromstring(zipfile.ZipFile(docx).read('word/document.xml'))
    out = []
    instr_depth = []  # 每个打开的域：True 表示处于指令阶段
    for ev, el in etree.iterwalk(root, events=('start',)):
        anc = el.getparent()
        skip = False
        while anc is not None:
            if anc.tag == MC + 'Fallback':
                skip = True
                break
            anc = anc.getparent()
        if skip:
            continue
        if el.tag == W + 'fldChar':
            t = el.get(W + 'fldCharType')
            if t == 'begin':
                instr_depth.append(True)
            elif t == 'separate':
                instr_depth[-1] = False
            elif t == 'end':
                instr_depth.pop()
            continue
        if instr_depth and instr_depth[-1]:
            continue
        if el.tag == W + 't':
            out.append(el.text or '')
        elif el.tag == W + 'tab' and el.getparent().tag == W + 'r':
            out.append('\t')
        elif el.tag in (W + 'br', W + 'cr'):
            out.append('\n')
        elif el.tag == W + 'p':
            out.append(' ')  # 段落分隔
    return ''.join(out)


def extracted_text(data):
    out = []

    def para(p):
        out.append(' ')
        for it in p.get('c', []):
            if 't' in it:
                out.append(it['t'])
            elif 'br' in it:
                out.append('\n')
            elif it.get('kind') == 'textbox':
                for q in it['paragraphs']:
                    para(q)

    for p in data['paragraphs']:
        para(p)
    return ''.join(out)


def main():
    a = independent_text(sys.argv[1])
    b = extracted_text(json.load(open(sys.argv[2], encoding='utf-8')))
    if a == b:
        print('一致：%d 个字符（含段落分隔）' % len(a))
        return
    n = next(i for i in range(min(len(a), len(b))) if a[i] != b[i]) if any(x != y for x, y in zip(a, b)) else min(len(a), len(b))
    print('不一致：长度 %d vs %d，首个差异位置 %d' % (len(a), len(b), n))
    print('docx  :', repr(a[max(0, n - 40):n + 40]))
    print('提取  :', repr(b[max(0, n - 40):n + 40]))
    sys.exit(1)


if __name__ == '__main__':
    main()
