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
      if (u.chars > 0) cur.items.push({ label: '卷首', link: `/${u.id}/` });
      continue;
    }
    if (u.kind === 'appendix') {
      if (u.id === 'app') {
        cur = { label: '附录', collapsed: true, items: [] };
        groups.push(cur);
      } else {
        cur.items.push({ label: u.title, link: `/${u.id}/` });
      }
      continue;
    }
    cur.items.push({ label: u.title, link: `/${u.id}/` });
  }
  return groups;
}

export default defineConfig({
  integrations: [
    starlight({
      title: 'Minecraft指令手册',
      defaultLocale: 'root',
      locales: { root: { label: '简体中文', lang: 'zh-CN' } },
      sidebar: buildSidebar(),
      customCss: ['./src/styles/book.css'],
      pagination: true,
    }),
  ],
});
