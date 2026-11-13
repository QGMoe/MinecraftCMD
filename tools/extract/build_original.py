"""从三种底本生成原文层：content/original/<单元ID>.json 与 content/units.json、content/sources.json。

底本优先级（作者确认）
- 第零卷的感言与注意事项、第一卷卷头、序言、第一至二十四章及两篇"MC新手要学习的基础"：MineBBS 迁移版（BBCode）
- MineBBS 发布前言：MineBBS 迁移版独有
- 其余单元（第零卷进程表、第二十五至一百五十六章、番外与节日章、附录、封面、各卷卷头）：主稿 docx
- 第一百五十七至一百五十九章：起点原文（作者粘贴，逐字提取）
- 第十七卷卷名：作者提供的起点截图（只有标题，没有正文）

三种格式各自无损保存：
- docx：段落流（docx_extract.py 的输出），保留样式、run 格式、链接、书签、图片、文本框
- bbcode：按白名单切分的词元序列，每个词元保留原始字符（raw），拼接后与底本逐字相同
- text：原样文本

用法：python3 -I build_original.py <底本目录> <仓库根目录>
底本目录结构：
  <底本目录>/Minecraft指令手册.docx
  <底本目录>/MineBBS/*.txt
  <底本目录>/起点独有/157第一百五十七章.txt 等
"""
import hashlib
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import docx_extract  # noqa: E402

CN_NUM = '零一二三四五六七八九'


def cn2int(s):
    """中文数字（至三位）→ 整数。"""
    s = s.replace('〇', '零')
    if s == '十':
        return 10
    total, cur = 0, 0
    for ch in s:
        if ch in CN_NUM:
            cur = CN_NUM.index(ch)
        elif ch == '十':
            total += (cur or 1) * 10
            cur = 0
        elif ch == '百':
            total += cur * 100
            cur = 0
        else:
            raise ValueError(s)
    return total + cur


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_text(t):
    return sha256_bytes(t.encode('utf-8'))


# ---------- docx：切分单元 ----------

EXTRA_IDS = {  # 非编号小节：挂在前一章之后
    'MC新手要学习的基础—1—红石信号': 'ch007-x1',
    'MC新手要学习的基础—2—Minecraft版本的区分': 'ch007-x2',
    '新年好！': 'ch044-x1',
    '本书第一次大修新增章 ① 矿词与标签': 'ch064-x1',
    '第九十六章番外 如何获得一个拥有手臂的盔甲架': 'ch096-x1',
    '第九十六章番外的番外 看，这个盔甲架高兴极了': 'ch096-x2',
    '基岩版玩家的32767级锋利的苹果': 'ch104-x1',
    '祝贺Minecraft11周年生日快乐！': 'ch107-x1',
    '虎年快乐！': 'ch154-x1',
    '本书第一次大修完成感言': 'f-afterword',
    '阅读本书需注意事项': 'f-notes',
    '本书第一次大修进程表': 'f-progress',
    '序言': 'preface',
}
APPENDIX_IDS = {'附录': 'app', '测试试题': 'app-quiz', '索引章节': 'app-index', '参考/引用文献列表': 'app-refs'}


def unit_for_heading(style, text, state):
    t = text.strip()
    if style == 'heading 1':
        if t == 'Minecraft指令手册' or t.endswith('Minecraft指令手册'):
            return 'cover', 'cover', None
        state['appendix'] = True
        return APPENDIX_IDS[t], 'appendix', None
    if style == 'heading 2':
        if state.get('appendix'):
            return APPENDIX_IDS[t], 'appendix', None
        m = re.match(r'第([零一二三四五六七八九十]+)卷', t)
        n = cn2int(m.group(1))
        return 'vol%02d' % n, 'volume', n
    if style == 'heading 3':
        if t in EXTRA_IDS:
            uid = EXTRA_IDS[t]
            kind = 'front' if uid.startswith('f-') else ('preface' if uid == 'preface' else 'extra')
            return uid, kind, None
        m = re.match(r'第([零一二三四五六七八九十百]+)章', t)
        if not m:
            raise SystemExit('无法识别的三级标题：%r' % t)
        n = cn2int(m.group(1))
        return 'ch%03d' % n, 'chapter', n
    return None


def split_docx(paragraphs):
    units, cur, state = [], None, {}
    for p in paragraphs:
        style = p.get('ppr', {}).get('style', '')
        u = unit_for_heading(style, p.get('text', ''), state) if style.startswith('heading') else None
        if p['i'] == 0 and u is None:
            raise SystemExit('第一段不是标题')
        if u:
            uid, kind, num = u
            cur = {'id': uid, 'kind': kind, 'number': num, 'title': p['text'].strip(), 'paragraphs': []}
            units.append(cur)
        cur['paragraphs'].append(p)
    ids = [u['id'] for u in units]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise SystemExit('单元 ID 重复：%s' % sorted(dup))
    return units


# ---------- BBCode：白名单词元 ----------

BB_TAGS = ('CENTER|LEFT|RIGHT|FONT|B|I|U|S|TD|TR|TH|TABLE|\\*|COLOR|BGCOLOR|HEADING|LIST|SIZE|INDENT|HR|URL|'
           'ISPOILER|SPOILER|QUOTE|CODE|ATTACH|IMG')
BB_RE = re.compile(r'\[(/?)(%s)(=[^\]\r\n]*)?((?: [A-Za-z\-]+="[^"\r\n]*")*)\]' % BB_TAGS, re.I)


def bb_tokens(text):
    toks, pos = [], 0
    in_code = False
    for m in BB_RE.finditer(text):
        name = m.group(2).upper()
        closing = bool(m.group(1))
        if in_code and not (closing and name == 'CODE'):
            continue  # [CODE] 内部不解析
        if m.start() > pos:
            toks.append({'text': text[pos:m.start()]})
        tok = {'tag': name, 'raw': m.group(0)}
        if closing:
            tok['close'] = True
        if m.group(3):
            tok['arg'] = m.group(3)[1:]
        if m.group(4):
            tok['attrs'] = m.group(4).strip()
        toks.append(tok)
        pos = m.end()
        if name == 'CODE':
            in_code = not closing
    if pos < len(text):
        toks.append({'text': text[pos:]})
    joined = ''.join(t.get('raw', t.get('text', '')) for t in toks)
    assert joined == text, '词元拼接后与原文不一致'
    return toks


def bb_plain(toks):
    return ''.join(t['text'] for t in toks if 'text' in t)


MINEBBS_FILES = [
    ('1第一章.txt', 'ch001'), ('2第二章.txt', 'ch002'), ('3第三章.txt', 'ch003'), ('4第四章.txt', 'ch004'),
    ('5第五章.txt', 'ch005'), ('6第六章.txt', 'ch006'), ('7第七章.txt', 'ch007'),
    ('8基础1.txt', 'ch007-x1'), ('9基础2.txt', 'ch007-x2'),
] + [('%d第%s章.txt' % (200 + k, n), 'ch%03d' % (7 + k)) for k, n in enumerate(
    ['八', '九', '十', '十一', '十二', '十三', '十四', '十五', '十六', '十七', '十八', '十九', '二十', '二十一',
     '二十二', '二十三', '二十四'], start=1)]

# 0声明部分.txt 按一级标题切分
MINEBBS_FRONT = [
    ('《Minecraft 指令手册》MineBBS 发布前言', 'f-minebbs-preface'),
    ('本书第一次大修完成感言', 'f-afterword'),
    ('阅读本书需注意事项', 'f-notes'),
    ('第一卷 新手入门', 'vol01'),
    ('序言', 'preface'),
]


def split_minebbs_front(text):
    heads = [(m.start(), re.sub(r'\[/?[A-Z]+(=[^\]]*)?\]', '', m.group(1)).strip())
             for m in re.finditer(r'\[HEADING=1\](.*?)\[/HEADING\]', text)]
    names = [h for _, h in heads]
    expect = [n for n, _ in MINEBBS_FRONT]
    if names != expect:
        raise SystemExit('0声明部分.txt 的一级标题与预期不符：%r' % names)
    out = []
    for k, (start, name) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(text)
        out.append((MINEBBS_FRONT[k][1], name, text[start:end]))
    if heads[0][0] != 0:
        # 第一个标题之前的内容也必须保留
        out[0] = (out[0][0], out[0][1], text[:heads[1][0]])
    return out


# ---------- 主流程 ----------

def main():
    src_dir, repo = sys.argv[1], sys.argv[2]
    out_dir = os.path.join(repo, 'content', 'original')
    asset_dir = os.path.join(repo, 'content', 'assets', 'docx')
    for d in (out_dir, asset_dir):
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d)

    sources = {}

    def register(logical, path):
        b = open(path, 'rb').read()
        sources[logical] = {'size': len(b), 'sha256': sha256_bytes(b)}
        return b

    # docx
    docx_path = os.path.join(src_dir, 'Minecraft指令手册.docx')
    register('主稿/Minecraft指令手册.docx', docx_path)
    stream = docx_extract.extract(docx_path)
    docx_units = split_docx(stream['paragraphs'])

    # MineBBS
    bb_units = {}
    front = os.path.join(src_dir, 'MineBBS', '0声明部分.txt')
    raw = register('MineBBS/0声明部分.txt', front).decode('utf-8')
    for uid, name, chunk in split_minebbs_front(raw):
        bb_units[uid] = {'file': 'MineBBS/0声明部分.txt', 'title': name, 'raw': chunk}
    for fname, uid in MINEBBS_FILES:
        logical = 'MineBBS/' + fname
        raw = register(logical, os.path.join(src_dir, 'MineBBS', fname)).decode('utf-8')
        bb_units[uid] = {'file': logical, 'title': None, 'raw': raw}

    # 起点独有
    qd_units = {}
    for fname, uid in [('157第一百五十七章.txt', 'ch157'), ('158第一百五十八章.txt', 'ch158'),
                       ('159第一百五十九章.txt', 'ch159')]:
        logical = '起点独有/' + fname
        raw = register(logical, os.path.join(src_dir, '起点独有', fname)).decode('utf-8')
        qd_units[uid] = {'file': logical, 'raw': raw}

    # 合并：按 docx 顺序排列，再插入 MineBBS 独有与起点独有单元
    order, used_media = [], set()

    def write(unit):
        with open(os.path.join(out_dir, unit['id'] + '.json'), 'w', encoding='utf-8') as f:
            json.dump(unit, f, ensure_ascii=False, indent=1)
        order.append({k: unit[k] for k in ('id', 'kind', 'number', 'title', 'source', 'format', 'text_sha256', 'chars')})

    def docx_unit(u):
        text = ' '.join(p.get('text', '') for p in u['paragraphs'])
        for p in u['paragraphs']:
            for c in p.get('c', []):
                if c.get('kind') == 'image':
                    used_media.add(c['media'])
                elif c.get('kind') == 'textbox':
                    for q in c['paragraphs']:
                        for cc in q.get('c', []):
                            if cc.get('kind') == 'image':
                                used_media.add(cc['media'])
        return {'id': u['id'], 'kind': u['kind'], 'number': u['number'], 'title': u['title'],
                'source': {'file': '主稿/Minecraft指令手册.docx',
                           'paragraphs': [u['paragraphs'][0]['i'], u['paragraphs'][-1]['i']]},
                'format': 'docx-paragraphs', 'content': u['paragraphs'],
                'text_sha256': sha256_text(text), 'chars': len(text.replace(' ', ''))}

    def bb_unit(uid, base):
        b = bb_units[uid]
        toks = bb_tokens(b['raw'])
        plain = bb_plain(toks)
        title = base['title'] if base else b['title']
        return {'id': uid, 'kind': base['kind'] if base else 'front', 'number': base['number'] if base else None,
                'title': title, 'source': {'file': b['file']}, 'format': 'bbcode-tokens', 'content': toks,
                'raw_sha256': sha256_text(b['raw']), 'text_sha256': sha256_text(plain), 'chars': len(plain)}

    for u in docx_units:
        if u['id'] == 'f-afterword':
            write(bb_unit('f-minebbs-preface', None))
        if u['id'] in bb_units:
            write(bb_unit(u['id'], u))
        else:
            write(docx_unit(u))
        if u['id'] == 'ch156':
            # 第十六卷末尾：起点独有的第一百五十七章；然后第十七卷
            for uid in ('ch157',):
                q = qd_units[uid]
                write({'id': uid, 'kind': 'chapter', 'number': 157, 'title': q['raw'].split('\n', 1)[0].strip(),
                       'source': {'file': q['file']}, 'format': 'text', 'content': q['raw'],
                       'text_sha256': sha256_text(q['raw']), 'chars': len(q['raw'])})
            write({'id': 'vol17', 'kind': 'volume', 'number': 17, 'title': '第十七卷 从NBT路径到/data指令',
                   'source': {'file': '作者提供的起点截图（只有卷名）'}, 'format': 'text', 'content': '',
                   'text_sha256': sha256_text(''), 'chars': 0})
            for uid, n in (('ch158', 158), ('ch159', 159)):
                q = qd_units[uid]
                write({'id': uid, 'kind': 'chapter', 'number': n, 'title': q['raw'].split('\n', 1)[0].strip(),
                       'source': {'file': q['file']}, 'format': 'text', 'content': q['raw'],
                       'text_sha256': sha256_text(q['raw']), 'chars': len(q['raw'])})

    # 检查：每个 MineBBS / 起点单元都已写出
    written = {o['id'] for o in order}
    missing = (set(bb_units) | set(qd_units)) - written
    if missing:
        raise SystemExit('有单元没有写出：%s' % sorted(missing))

    # 复制用到的 docx 媒体文件
    import zipfile
    z = zipfile.ZipFile(docx_path)
    media = {}
    for m in sorted(used_media):
        b = z.read(m)
        name = os.path.basename(m)
        with open(os.path.join(asset_dir, name), 'wb') as f:
            f.write(b)
        media[m] = {'file': 'content/assets/docx/' + name, 'sha256': sha256_bytes(b), 'size': len(b)}

    with open(os.path.join(repo, 'content', 'units.json'), 'w', encoding='utf-8') as f:
        json.dump(order, f, ensure_ascii=False, indent=1)
    with open(os.path.join(repo, 'content', 'sources.json'), 'w', encoding='utf-8') as f:
        json.dump({'sources': sources, 'media': media}, f, ensure_ascii=False, indent=1)
    print('单元', len(order), '媒体', len(media))


if __name__ == '__main__':
    main()
