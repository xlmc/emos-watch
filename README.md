# EMOS 热门片单

这个仓库每天北京时间约 07:50、16:50 检查 EMOS 动态片单。

片单名称可在 `config.json` 的 `variety_name`、`japan_name`、`kamen_rider_name`、`super_sentai_name` 中分别设置。日番片单名称已固定为“厕纸”。配置项留空时保留仓库已有名称，首次生成才使用默认名称；后续自动更新不会覆盖自定义名称。

- 片单 1：从 TMDB 筛选中国大陆真人秀/脱口秀类型；只取当前年度已上线的最新普通季，排除未来节目和特别篇，仍在播或近 120 天有正片更新的节目优先，当天有正片更新的置顶，最多 50 部。
- 片单 2：从 TMDB 获取今年已上线的日本 TV 动画，按首播时间从新到旧，最多 50 部，片单名称为“厕纸”。
- 片单 3：从 TMDB 获取假面骑士 2000 年至今的正剧 TV 系列，按首播时间从新到旧。
- 片单 4：从 TMDB 获取东映超级战队从 1975 年《秘密战队五连者》至今的正剧 TV 系列，按首播时间从新到旧。

四个片单都直接输出 TMDB ID 和类型，封面统一使用 TMDB 图片服务生成。日番按今年已上线时间从新到旧排序；假面骑士和超级战队使用正剧白名单，从 TMDB 查询并排除电影、剧场版、特别篇和衍生剧。综艺从 TMDB 获取最新季和分集日期，不再依赖 T0DB。

## 第一次设置

1. 在 `Settings → Pages` 设置：

   ```text
   Source：Deploy from a branch
   Branch：main
   Folder：/(root)
   ```

2. 在仓库 `Settings → Secrets and variables → Actions` 新建 Secret：

   ```text
   名称：TMDB_ACCESS_TOKEN
   值：TMDB Read Access Token
   ```

   四个片单都使用此密钥，不再需要 T0DB Secret。

3. 到 `Actions` 手动运行“更新综艺、日番、假面骑士与超级战队片单”。第一次成功后，仓库会出现日番、综艺、假面骑士和超级战队的 JSON/GIF 文件。`watch.json`、`cover.gif` 作为旧综艺地址兼容保留。

4. EMOS 动态片单地址：

   ```text
   片单 1（国内流媒体热播综艺）：https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch-variety.json

   片单 2（日番，名称：厕纸）：https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch-japan.json

   片单 3（假面骑士正剧）：https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch-kamen-rider.json

   片单 4（东映超级战队正剧）：https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch-super-sentai.json
   ```

## CDN 地址

EMOS 推荐使用 jsDelivr CDN 地址：

片单 2（国内流媒体热播综艺）：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch-variety.json
```

旧综艺封面兼容地址：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/cover.gif
```

综艺封面新地址：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/cover-variety.gif
```

日番封面（名称：厕纸）：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/cover-japan.gif
```

片单 3 封面（假面骑士正剧）：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/cover-kamen-rider.gif
```

片单 4 封面（东映超级战队正剧）：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/cover-super-sentai.gif
```

## 使用你的域名

如果 Cloudflare 可以管理 `zzzj.de5.net` 的 DNS，可添加：

```text
类型：CNAME
名称：watch
目标：xlmc.github.io
代理状态：DNS Only
```

然后在 GitHub Pages 绑定 `watch.zzzj.de5.net`，并把 `config.json` 的 `site_base_url` 改成：

```text
https://watch.zzzj.de5.net
```

最后 EMOS 综艺片单地址改成：

```text
https://watch.zzzj.de5.net/watch-variety.json
```

如果使用自定义域名，另外两个地址分别是：

```text
https://watch.zzzj.de5.net/watch-kamen-rider.json
https://watch.zzzj.de5.net/watch-super-sentai.json
https://watch.zzzj.de5.net/watch-japan.json
```

不要把 GitHub PAT、TMDB Token 写入仓库。GitHub Actions 使用仓库自带的 `GITHUB_TOKEN` 提交每日生成文件。

## 数据源说明

综艺片单使用 TMDB Discover TV、详情、季和分集接口，筛选中国大陆综艺并按正片日期排序。日番片单使用 TMDB Discover TV，筛选日本、日语、动画类型且已经上线的条目，按首播时间从新到旧输出，最多 50 部。假面骑士和超级战队使用固定的正剧系列白名单从 TMDB Search TV 查询，不录入电影、特别篇、剧场版或衍生作品。

