// 把原文层的图片复制到 public/，供页面引用（生成物，不入库）。
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const src = path.resolve(here, '../../content/assets/docx');
const dst = path.resolve(here, '../public/assets/docx');
fs.rmSync(dst, { recursive: true, force: true });
fs.mkdirSync(dst, { recursive: true });
let n = 0;
for (const f of fs.readdirSync(src)) { fs.copyFileSync(path.join(src, f), path.join(dst, f)); n++; }
console.log(`已同步 ${n} 个图片`);
