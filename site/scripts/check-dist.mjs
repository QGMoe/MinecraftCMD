// 构建产物校验：dist/ 中每个页面的正文（.sl-markdown-content）去标签后，与原文逐字一致。
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { htmlText, expectedText } from '../src/lib/render.mjs';
const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../../content');
const dist = path.resolve(here, '../dist');
const units = JSON.parse(fs.readFileSync(path.join(root, 'units.json'), 'utf8'));
const squash = (s) => s.replace(/[\r\n\t ]+/g, '');
let bad = 0;
for (const meta of units) {
  const unit = JSON.parse(fs.readFileSync(path.join(root, 'original', meta.id + '.json'), 'utf8'));
  const file = path.join(dist, meta.id === 'cover' ? '' : meta.id, 'index.html');
  const page = fs.readFileSync(file, 'utf8');
  const start = page.indexOf('<div class="sl-markdown-content">');
  const end = page.indexOf('<footer', start);
  let body = start < 0 || end < 0 ? '' : page.slice(start + '<div class="sl-markdown-content">'.length, end);
  body = body.replace(/<\/div>\s*$/, ''); // 去掉正文容器自身的结束标签
  if (squash(htmlText(body)) !== squash(expectedText(unit))) { bad++; console.log('✗', meta.id); }
}
console.log(`构建产物校验：${units.length} 个页面，${bad ? bad + ' 个不一致' : '全部一致'}`);
process.exit(bad ? 1 : 0);
