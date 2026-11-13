import fs from 'node:fs';
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

// 侧边栏由 content/units.json 生成：卷为分组，组内按原书顺序排列。
const units = JSON.parse(fs.readFileSync(new URL('../content/units.json', import.meta.url), 'utf8'));

function buildSidebar() {
  const groups = [];
  let cur = null;
  for (const u of units) {
    if (u.id === 'cover') continue;
    if (u.kind === 'volume') {
      cur = { label: u.title, collapsed: true, items: [] };
      groups.push(cur);
      if (u.chars > 0) cur.items.push({ label: '卷首', slug: u.id });
      continue;
    }
    if (u.kind === 'appendix') {
      if (u.id === 'app') {
        cur = { label: '附录', collapsed: true, items: [] };
        groups.push(cur);
      } else {
        cur.items.push({ label: u.title, slug: u.id });
      }
      continue;
    }
    cur.items.push({ label: u.title, slug: u.id });
  }
  return groups;
}

// GitHub Pages：部署工作流通过环境变量传入站点地址与子路径
const SITE = process.env.SITE || undefined;
const BASE_PATH = process.env.BASE_PATH || '/';

export default defineConfig({
  site: SITE,
  base: BASE_PATH,
  trailingSlash: 'always',
  integrations: [
    starlight({
      title: 'Minecraft指令手册',
      logo: { src: './src/assets/grass-block.svg', alt: '' },
      favicon: '/favicon.svg',
      defaultLocale: 'root',
      locales: { root: { label: '简体中文', lang: 'zh-CN' } },
      sidebar: buildSidebar(),
      customCss: ['./src/styles/theme.css', './src/styles/book.css'],
      pagination: true,
    }),
  ],
});
