// 渲染校验：每个单元渲染出的 HTML 去掉标签后，必须与原文的文字逐字一致。
// 允许的差异只有 ASCII 空白（换行、空格、制表符）：渲染时块边界和结构标签之间的空白会被省略。
// 全角空格（U+3000）等其他字符一律要求一致。
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderUnit, htmlText, expectedText, expectedImages } from '../src/lib/render.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../content');
const units = JSON.parse(fs.readFileSync(path.join(root, 'units.json'), 'utf8'));
const squash = (s) => s.replace(/[\r\n\t ]+/g, '');
let bad = 0;
for (const meta of units) {
  const unit = JSON.parse(fs.readFileSync(path.join(root, 'original', meta.id + '.json'), 'utf8'));
  const html = renderUnit(unit);
  const imgs = (html.match(/<img /g) || []).length;
  if (imgs !== expectedImages(unit)) { bad++; console.log(`✗ ${meta.id}：图片 ${imgs} 张，原文 ${expectedImages(unit)} 张`); }
  const got = squash(htmlText(html));
  const want = squash(expectedText(unit));
  if (got !== want) {
    bad++;
    let k = 0;
    while (k < got.length && got[k] === want[k]) k++;
    console.log(`✗ ${meta.id}：位置 ${k}`);
    console.log('  渲染：', JSON.stringify(got.slice(Math.max(0, k - 30), k + 30)));
    console.log('  原文：', JSON.stringify(want.slice(Math.max(0, k - 30), k + 30)));
  }
}
console.log(`渲染校验：${units.length} 个单元，${bad ? bad + ' 个不一致' : '全部一致'}`);
process.exit(bad ? 1 : 0);
