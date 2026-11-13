import fs from 'node:fs';
import path from 'node:path';
import { defineCollection } from 'astro:content';
import { docsSchema } from '@astrojs/starlight/schema';
import { renderUnit } from './lib/render.mjs';

const CONTENT = path.resolve('../content');
// 图片路径要带上部署子路径（GitHub Pages 的项目站点为 /<仓库名>/）
const ASSET_BASE = (process.env.BASE_PATH || '/').replace(/\/$/, '') + '/assets/docx';

// 自定义加载器：直接读取原文层并渲染为 HTML，不经过 Markdown。
function bookLoader() {
  return {
    name: 'minecraftcmd-book-loader',
    load: async ({ store, parseData, logger }: any) => {
      store.clear();
      const units = JSON.parse(fs.readFileSync(path.join(CONTENT, 'units.json'), 'utf8'));
      for (const meta of units) {
        const unit = JSON.parse(fs.readFileSync(path.join(CONTENT, 'original', meta.id + '.json'), 'utf8'));
        const html = renderUnit(unit, ASSET_BASE);
        const id = meta.id === 'cover' ? 'index' : meta.id;
        const data = await parseData({
          id,
          data: {
            title: meta.id === 'cover' ? 'Minecraft指令手册' : meta.title,
            description: meta.id === 'cover' ? '《Minecraft指令手册》归档' : undefined,
            tableOfContents: false,
            editUrl: false,
          },
        });
        store.set({ id, data, rendered: { html, metadata: { headings: [] } } });
      }
      logger.info(`已载入 ${units.length} 个单元`);
    },
  };
}

export const collections = {
  docs: defineCollection({ loader: bookLoader(), schema: docsSchema() }),
};
