# 《Minecraft指令手册》归档

《Minecraft指令手册》是一本 Minecraft 指令教程，2020 年起在起点中文网连载，2022 年完成第一次大修，2025 年起迁移到 MineBBS、苦力怕论坛和 MC 百科社群，共十七卷、一百五十九章。本仓库把它整理成一个网站，作为这门已经结课的课程的归档。

> 本仓库正在搭建中，目前完成的是地基部分（P0）：从底本无损提取原文层，并建立校验。

## 原则

- **内容冻结**：原文一个字都不改。过时或有误的地方只加注释，注释与原文分开存放。
- **原文只用程序处理**：原文的提取、切分、转换都由脚本完成，并且必须通过逐字校验；任何人（包括 AI）都不手工重新输入正文。
- **版本只做标注**：书中的多版本交叉是教学方法，网站不提供"只看某个版本"的过滤。

## 目录

```
content/
  units.json          单元清单（顺序、ID、类型、标题、来源、字数、文本哈希）
  sources.json        底本清单（逻辑名、大小、sha256）与媒体文件清单
  original/<ID>.json  原文层：每个单元一个文件
  assets/docx/        主稿中的图片
site/                 网站（Astro + Starlight）
  src/content.config.ts  自定义加载器：读取原文层，直接渲染为 HTML（不经过 Markdown）
  src/lib/render.mjs     原文层 → HTML（目前是原文直出，只做格式映射）
  scripts/check-render.mjs  渲染校验：每个单元的渲染结果去标签后与原文逐字一致，图片数量一致
  scripts/check-dist.mjs    构建产物校验：dist/ 中每个页面的正文与原文逐字一致
tools/extract/
  docx_extract.py     主稿 docx → 段落流（无损）
  docx_crosscheck.py  用独立方法核对 docx 提取结果
  build_original.py   三种底本 → 原文层
  verify.py           原文层校验（自洽检查 / 底本比对）
```

## 单元 ID

| 类型 | ID | 说明 |
|---|---|---|
| 章 | `ch001` ～ `ch159` | 第一章至第一百五十九章 |
| 非编号小节 | `ch007-x1`、`ch096-x2` … | 挂在前一章之后，如两篇"MC新手要学习的基础"、番外、节日章 |
| 卷头 | `vol00` ～ `vol17` | 卷名与卷首语 |
| 第零卷 | `f-minebbs-preface`、`f-afterword`、`f-notes`、`f-progress` | MineBBS 发布前言、大修完成感言、阅读注意事项、大修进程表 |
| 其他 | `cover`、`preface`、`app`、`app-quiz`、`app-index`、`app-refs` | 封面、序言、附录 |

## 底本

| 单元 | 底本 | 原文层格式 |
|---|---|---|
| MineBBS 发布前言、大修完成感言、阅读注意事项、第一卷卷头、序言、第一至二十四章、两篇"基础" | MineBBS 迁移版 | `bbcode-tokens`：按标签白名单切分的词元，拼接后与底本逐字相同 |
| 第零卷进程表、第二十五至一百五十六章、番外与节日章、其余卷头、封面、附录 | 主稿 docx | `docx-paragraphs`：段落流，保留样式、字符格式、链接、书签、图片、文本框 |
| 第一百五十七至一百五十九章 | 起点原文 | `text`：原样文本 |
| 第十七卷卷名 | 起点截图 | 只有卷名 |

底本本身不在仓库中，`content/sources.json` 记录了每个底本的 sha256。

## 校验

需要 Python 3 与 `lxml`（见 `requirements.txt`）。

```bash
python3 -I tools/extract/verify.py .
```

自洽检查：任何环境都能运行，检查每个单元的文本哈希、docx 段落哈希、BBCode 往返、媒体文件哈希。

```bash
python3 -I tools/extract/verify.py . --sources <底本目录>
```

底本比对：需要底本。先核对底本的 sha256，再重新生成整个原文层，与仓库逐字节比较。

## 网站

需要 Node.js 22 或更高版本。

```bash
cd site
npm install
npm run dev      # 本地开发
npm run build    # 构建；构建前后会自动运行渲染校验与构建产物校验
```

网站部署在 <https://cmd.qingu.moe/>（GitHub Pages，工作流见 `.github/workflows/pages.yml`，只在主仓库部署）。

当前是最小可浏览版本：全书 196 个单元按卷挂在侧边栏，正文按原文直出，已支持全文搜索和深色模式；语义渲染（指令、聊天记录、汉字示意图等）尚未开始。

## 许可

暂未选定许可。书中原有的转载声明仍然有效：未经作者授权禁止转载；单次连续引用少于 1000 字，或保留署名的衍生创作，可以不经授权。
