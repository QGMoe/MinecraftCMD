"""原文层校验。

两种模式
1. 自洽检查（不需要底本，任何环境都能跑，适合 CI）：
   - units.json 与 content/original/*.json 一一对应，字段一致
   - 每个单元的 text_sha256 由内容重新计算后一致；docx 段落的 sha256 一致；BBCode 词元拼回 raw 后 raw_sha256 一致
   - sources.json 记录的媒体文件存在且 sha256 一致
2. 底本比对（需要底本目录）：
   - 底本文件的 sha256 与 sources.json 记录一致
   - 用 build_original.py 在临时目录重新生成，与仓库中的 content/ 逐字节比较

用法：
  python3 -I verify.py <仓库根目录>                 # 自洽检查
  python3 -I verify.py <仓库根目录> --sources <底本目录>  # 再加底本比对
"""
import filecmp
import hashlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def sha(t):
    return hashlib.sha256(t.encode('utf-8')).hexdigest()


def unit_text(u):
    fmt = u['format']
    if fmt == 'docx-paragraphs':
        return ' '.join(p.get('text', '') for p in u['content'])
    if fmt == 'bbcode-tokens':
        return ''.join(t['text'] for t in u['content'] if 'text' in t)
    if fmt == 'text':
        return u['content']
    raise ValueError(fmt)


def docx_para_text(p):
    out = []
    for it in p.get('c', []):
        if 't' in it:
            out.append(it['t'])
        elif 'br' in it:
            out.append('\n')
    return ''.join(out)


def self_check(repo):
    errs = []
    content = os.path.join(repo, 'content')
    units = json.load(open(os.path.join(content, 'units.json'), encoding='utf-8'))
    files = {f[:-5] for f in os.listdir(os.path.join(content, 'original')) if f.endswith('.json')}
    ids = [u['id'] for u in units]
    if len(ids) != len(set(ids)):
        errs.append('units.json 中有重复 ID')
    if set(ids) != files:
        errs.append('units.json 与文件不一致：多 %s，少 %s' % (sorted(files - set(ids)), sorted(set(ids) - files)))
    for meta in units:
        path = os.path.join(content, 'original', meta['id'] + '.json')
        if not os.path.exists(path):
            continue
        u = json.load(open(path, encoding='utf-8'))
        for k in ('id', 'kind', 'number', 'title', 'source', 'format', 'text_sha256', 'chars'):
            if u.get(k) != meta.get(k):
                errs.append('%s：字段 %s 与 units.json 不一致' % (meta['id'], k))
        t = unit_text(u)
        if sha(t) != u['text_sha256']:
            errs.append('%s：text_sha256 不一致' % u['id'])
        if u['format'] == 'docx-paragraphs':
            for p in u['content']:
                pt = docx_para_text(p)
                if pt != p.get('text') or sha(pt) != p.get('sha256'):
                    errs.append('%s：段落 %s 的文本或 sha256 不一致' % (u['id'], p.get('i')))
        if u['format'] == 'bbcode-tokens':
            raw = ''.join(x.get('raw', x.get('text', '')) for x in u['content'])
            if sha(raw) != u['raw_sha256']:
                errs.append('%s：BBCode 拼回后 raw_sha256 不一致' % u['id'])
    src = json.load(open(os.path.join(content, 'sources.json'), encoding='utf-8'))
    for m, info in src['media'].items():
        p = os.path.join(repo, info['file'])
        if not os.path.exists(p):
            errs.append('缺少媒体文件 %s' % info['file'])
        elif hashlib.sha256(open(p, 'rb').read()).hexdigest() != info['sha256']:
            errs.append('媒体文件 sha256 不一致 %s' % info['file'])
    return errs, len(units)


def source_check(repo, src_dir):
    errs = []
    src = json.load(open(os.path.join(repo, 'content', 'sources.json'), encoding='utf-8'))
    logical_to_path = {'主稿/Minecraft指令手册.docx': os.path.join(src_dir, 'Minecraft指令手册.docx')}
    for logical in src['sources']:
        p = logical_to_path.get(logical, os.path.join(src_dir, *logical.split('/')))
        if not os.path.exists(p):
            errs.append('底本缺失：%s' % logical)
            continue
        if hashlib.sha256(open(p, 'rb').read()).hexdigest() != src['sources'][logical]['sha256']:
            errs.append('底本 sha256 与记录不一致：%s' % logical)
    if errs:
        return errs
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, 'content'))
        r = subprocess.run([sys.executable, '-I', os.path.join(HERE, 'build_original.py'), src_dir, tmp],
                           capture_output=True, text=True)
        if r.returncode:
            return ['重新生成失败：' + r.stderr[-500:]]
        a, b = os.path.join(repo, 'content'), os.path.join(tmp, 'content')
        for root, _, fs in os.walk(b):
            for f in fs:
                rel = os.path.relpath(os.path.join(root, f), b)
                if not os.path.exists(os.path.join(a, rel)):
                    errs.append('仓库缺少：content/' + rel)
                elif not filecmp.cmp(os.path.join(a, rel), os.path.join(b, rel), shallow=False):
                    errs.append('与重新生成的结果不同：content/' + rel)
        for root, _, fs in os.walk(a):
            for f in fs:
                rel = os.path.relpath(os.path.join(root, f), a)
                if rel.split(os.sep)[0] in ('original', 'assets') or rel in ('units.json', 'sources.json'):
                    if not os.path.exists(os.path.join(b, rel)):
                        errs.append('仓库多出（重新生成时没有）：content/' + rel)
    return errs


def main():
    repo = sys.argv[1]
    errs, n = self_check(repo)
    print('自洽检查：%d 个单元，%s' % (n, '通过' if not errs else '%d 个问题' % len(errs)))
    if '--sources' in sys.argv:
        e2 = source_check(repo, sys.argv[sys.argv.index('--sources') + 1])
        print('底本比对：%s' % ('通过' if not e2 else '%d 个问题' % len(e2)))
        errs += e2
    for e in errs[:50]:
        print('  -', e)
    sys.exit(1 if errs else 0)


if __name__ == '__main__':
    main()
