// 原文层 → HTML（最小可浏览版：原文直出，只做忠实的格式映射，不做语义识别）。
// 所有正文字符都经过 HTML 转义；不经过 Markdown，避免 * _ ~ # 等被解释。
// 校验：scripts/check-render.mjs 会核对渲染结果去掉标签后与原文逐字一致。

const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

// ---------- docx 段落 ----------

const PARA_CLASS = {
  'MC内容': 'mc',
  '小标题': 'subheading',
  caption: 'caption',
  'List Paragraph': 'list-paragraph',
};

function cssColor(hex) {
  return /^[0-9A-Fa-f]{6}$/.test(hex) ? '#' + hex : null;
}

function docxInline(items, assetBase) {
  let out = '';
  for (const it of items) {
    if ('t' in it || 'br' in it) {
      let h = 't' in it ? esc(it.t) : '<br>';
      const p = it.p || {};
      if ('t' in it) {
        if (p.b) h = `<strong>${h}</strong>`;
        if (p.i) h = `<em>${h}</em>`;
        if (p.u && p.u !== 'none') h = `<u>${h}</u>`;
        if (p.strike || p.dstrike) h = `<s>${h}</s>`;
        const styles = [];
        const c = p.color && cssColor(p.color);
        if (c) styles.push(`color:${c}`);
        const attrs = [];
        if (styles.length) attrs.push(`style="${styles.join(';')}"`);
        if (p.style) attrs.push(`data-cs="${esc(p.style)}"`);
        if (p.font && (p.font.ascii || p.font.eastAsia)) attrs.push(`data-font="${esc(p.font.eastAsia || p.font.ascii)}"`);
        if (p.highlight) h = `<mark data-hl="${esc(p.highlight)}">${h}</mark>`;
        if (attrs.length) h = `<span ${attrs.join(' ')}>${h}</span>`;
      }
      if (it.link) {
        const href = it.link.url || (it.link.anchor ? '#' + encodeURIComponent(it.link.anchor) : null);
        if (href && /^(https?:|#)/.test(href)) h = `<a href="${esc(href)}">${h}</a>`;
      }
      out += h;
    } else if ('bookmark' in it) {
      if (it.bookmark && it.bookmark !== '_GoBack') out += `<a id="${esc(it.bookmark)}"></a>`;
    } else if (it.kind === 'image') {
      const name = it.media.split('/').pop();
      out += `<img class="docx-image ${it.placement}" src="${assetBase}/${esc(name)}" alt="${esc(it.descr || '插图')}" loading="lazy">`;
    } else if (it.kind === 'textbox') {
      out += `<span class="textbox">${it.paragraphs.map((q) => docxInline(q.c || [], assetBase)).join('<br>')}</span>`;
    }
    // field 标记、shape 等不产生正文
  }
  return out;
}

function renderDocx(unit, assetBase) {
  const paras = unit.content;
  const html = [];
  paras.forEach((p, k) => {
    const style = (p.ppr && p.ppr.style) || '';
    if (k === 0 && style.startsWith('heading')) {
      // 单元标题的文字由页面标题显示；标题段落里的图片（如封面、第九十二章）照常输出
      const imgs = (p.c || []).filter((it) => it.kind === 'image');
      if (imgs.length) html.push(`<p class="o align-center">${docxInline(imgs, assetBase)}</p>`);
      return;
    }
    const inner = docxInline(p.c || [], assetBase);
    if (!inner) {
      html.push('<p class="empty"></p>');
      return;
    }
    const cls = ['o'];
    if (PARA_CLASS[style]) cls.push(PARA_CLASS[style]);
    if (style.startsWith('heading')) cls.push('inner-heading');
    const jc = p.ppr && p.ppr.jc;
    if (jc === 'center' || jc === 'right') cls.push('align-' + jc);
    if (p.ppr && p.ppr.ind && p.ppr.ind.firstLine) cls.push('indent');
    html.push(`<p class="${cls.join(' ')}">${inner}</p>`);
  });
  return html.join('\n');
}

// ---------- BBCode 词元（XenForo / MineBBS） ----------

const BLOCK = new Set(['CENTER', 'LEFT', 'RIGHT', 'HEADING', 'LIST', '*', 'TABLE', 'TR', 'TD', 'TH', 'HR', 'QUOTE', 'SPOILER', 'CODE', 'INDENT']);

function safeColor(v) {
  return /^(rgb\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*\)|#[0-9a-fA-F]{3,6}|[a-zA-Z]+)$/.test(v) ? v : null;
}

function stripQuotes(v) {
  return v ? v.replace(/^['"]|['"]$/g, '') : v;
}

function renderBBCode(unit) {
  const toks = unit.content;
  let i = 0;
  // 跳过开头的单元标题：第一个 [HEADING]…[/HEADING]
  while (i < toks.length && 'text' in toks[i] && !toks[i].text.trim()) i++;
  if (toks[i] && toks[i].tag === 'HEADING' && !toks[i].close) {
    let depth = 0;
    for (; i < toks.length; i++) {
      const t = toks[i];
      if (t.tag === 'HEADING') depth += t.close ? -1 : 1;
      if (t.tag === 'HEADING' && t.close && depth === 0) { i++; break; }
    }
  }
  let out = '';
  const stack = [];
  let dropNewline = true; // 块级标签之后吞掉一个换行
  let inCode = false;
  const open = (t) => {
    const arg = stripQuotes(t.arg);
    switch (t.tag) {
      case 'B': return '<strong>';
      case 'I': return '<em>';
      case 'U': return '<u>';
      case 'S': return '<s>';
      case 'COLOR': { const c = safeColor(arg); return c ? `<span style="color:${c}">` : '<span>'; }
      case 'BGCOLOR': { const c = safeColor(arg); return c ? `<span class="bg" style="background:${c}">` : '<span>'; }
      case 'FONT': return `<span data-font="${esc(arg || '')}">`;
      case 'SIZE': { const m = /^(\d{1,3})(px)?$/.exec(arg || ''); return m ? `<span style="font-size:${Math.min(+m[1], 48)}px">` : '<span>'; }
      case 'CENTER': return '<div class="align-center">';
      case 'LEFT': return '<div class="align-left">';
      case 'RIGHT': return '<div class="align-right">';
      case 'INDENT': { const n = Math.min(parseInt(arg || '1', 10) || 1, 6); return `<div style="margin-left:${n * 2}em">`; }
      case 'HEADING': { const n = Math.min(Math.max(parseInt(arg || '1', 10) || 1, 1), 3); return `<h${n + 1} class="bb-heading">`; }
      case 'LIST': return arg ? '<ol>' : '<ul>';
      case 'TABLE': return '<table class="bb-table">';
      case 'TR': return '<tr>';
      case 'TD': case 'TH': {
        const w = /width="(\d{1,3})%"/.exec(t.attrs || '');
        return `<${t.tag.toLowerCase()}${w ? ` style="width:${w[1]}%"` : ''}>`;
      }
      case 'QUOTE': return '<blockquote>';
      case 'SPOILER': return `<details class="spoiler"><summary>${esc(arg || '剧透')}</summary>`;
      case 'ISPOILER': return '<span class="ispoiler">';
      case 'CODE': return '<pre class="bb-code"><code>';
      case 'URL': { const href = arg && /^https?:\/\//.test(arg) ? arg : null; return href ? `<a href="${esc(href)}">` : '<span>'; }
      case 'ATTACH': return '<span class="attach" title="论坛附件（未收录）">';
      case 'HR': return '<hr>';
      default: return '<span>';
    }
  };
  const closeTag = (name, arg) => {
    switch (name) {
      case 'B': return '</strong>';
      case 'I': return '</em>';
      case 'U': return '</u>';
      case 'S': return '</s>';
      case 'CENTER': case 'LEFT': case 'RIGHT': case 'INDENT': return '</div>';
      case 'HEADING': { const n = Math.min(Math.max(parseInt(arg || '1', 10) || 1, 1), 3); return `</h${n + 1}>`; }
      case 'LIST': return arg ? '</ol>' : '</ul>';
      case 'TABLE': return '</table>';
      case 'TR': return '</tr>';
      case 'TD': return '</td>';
      case 'TH': return '</th>';
      case 'QUOTE': return '</blockquote>';
      case 'SPOILER': return '</details>';
      case 'CODE': return '</code></pre>';
      case 'URL': return arg && /^https?:\/\//.test(stripQuotes(arg)) ? '</a>' : '</span>';
      case 'HR': return '';
      default: return '</span>';
    }
  };
  const top = () => stack[stack.length - 1];
  for (; i < toks.length; i++) {
    const t = toks[i];
    if ('text' in t) {
      let s = t.text.replace(/\r\n/g, '\n');
      if (inCode) { out += esc(s); continue; }
      const ctx = top() && top().tag;
      if ((ctx === 'LIST' || ctx === 'TABLE' || ctx === 'TR') && !s.trim()) continue; // 结构标签之间的空白
      if (dropNewline && s.startsWith('\n')) s = s.slice(1);
      dropNewline = false;
      out += esc(s).replace(/\n/g, '<br>\n');
      continue;
    }
    const name = t.tag;
    if (!t.close) {
      if (name === '*') {
        if (top() && top().tag === '*') { out += '</li>'; stack.pop(); }
        out += '<li>';
        stack.push({ tag: '*' });
        dropNewline = true;
        continue;
      }
      if (name === 'HR') { out += '<hr>'; dropNewline = true; continue; }
      out += open(t);
      stack.push({ tag: name, arg: t.arg });
      if (name === 'CODE') inCode = true;
      if (BLOCK.has(name)) dropNewline = true;
    } else {
      if (name === 'HR') continue;
      if (name === 'LIST' && top() && top().tag === '*') { out += '</li>'; stack.pop(); }
      // 弹出到匹配的标签为止；不匹配的关闭标签按原样输出为文字（保证不丢字符）
      const idx = stack.map((x) => x.tag).lastIndexOf(name);
      if (idx < 0) { out += esc(t.raw); continue; }
      while (stack.length > idx) {
        const x = stack.pop();
        out += x.tag === '*' ? '</li>' : closeTag(x.tag, x.arg);
      }
      if (name === 'CODE') inCode = false;
      if (BLOCK.has(name)) dropNewline = true;
    }
  }
  while (stack.length) { const x = stack.pop(); out += x.tag === '*' ? '</li>' : closeTag(x.tag, x.arg); }
  return `<div class="bb">${out}</div>`;
}

// ---------- 起点纯文本 ----------

function renderText(unit) {
  const lines = unit.content.split('\n');
  const body = lines.slice(1); // 第一行是章名
  return body.map((l) => (l.trim() ? `<p class="o qd">${esc(l)}</p>` : '')).filter(Boolean).join('\n');
}

export function renderUnit(unit, assetBase = '/assets/docx') {
  switch (unit.format) {
    case 'docx-paragraphs': return renderDocx(unit, assetBase);
    case 'bbcode-tokens': return renderBBCode(unit);
    case 'text': return renderText(unit);
    default: throw new Error('未知格式 ' + unit.format);
  }
}

// ---------- 校验用：渲染结果去标签后的文字，以及原文应有的文字 ----------

const unesc = (s) => s.replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');

export function htmlText(html) {
  // 只去掉标签与转义；<br>、块边界不产生字符（校验时忽略换行）
  return unesc(html.replace(/<summary>[^<]*<\/summary>/g, '').replace(/<[^>]+>/g, ''));
}

export function expectedText(unit) {
  if (unit.format === 'docx-paragraphs') {
    const out = [];
    const walk = (items) => {
      for (const it of items) {
        if ('t' in it) out.push(it.t);
        else if (it.kind === 'textbox') for (const q of it.paragraphs) walk(q.c || []);
      }
    };
    unit.content.forEach((p, k) => {
      if (k === 0 && ((p.ppr && p.ppr.style) || '').startsWith('heading')) return;
      walk(p.c || []);
    });
    return out.join('');
  }
  if (unit.format === 'bbcode-tokens') {
    // 原文的全部文字，减去开头标题块中的文字
    const toks = unit.content;
    let i = 0;
    while (i < toks.length && 'text' in toks[i] && !toks[i].text.trim()) i++;
    if (toks[i] && toks[i].tag === 'HEADING' && !toks[i].close) {
      let depth = 0;
      for (; i < toks.length; i++) {
        const t = toks[i];
        if (t.tag === 'HEADING') depth += t.close ? -1 : 1;
        if (t.tag === 'HEADING' && t.close && depth === 0) { i++; break; }
      }
    }
    return toks.slice(i).map((t) => ('text' in t ? t.text : '')).join('');
  }
  if (unit.format === 'text') return unit.content.split('\n').slice(1).join('\n');
  return '';
}

// 校验用：原文中的图片数量（含标题段落、文本框内）
export function expectedImages(unit) {
  if (unit.format !== 'docx-paragraphs') return 0;
  let n = 0;
  const walk = (items) => { for (const it of items) { if (it.kind === 'image') n++; else if (it.kind === 'textbox') for (const q of it.paragraphs) walk(q.c || []); } };
  for (const p of unit.content) walk(p.c || []);
  return n;
}
