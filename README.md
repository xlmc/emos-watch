# EMOS 热门片单

这个仓库每天北京时间约 07:50、16:50 检查 EMOS 动态片单。

片单名称可在 `config.json` 的 `variety_name`、`kamen_rider_name`、`super_sentai_name` 中分别设置。配置项留空时保留仓库已有名称，首次生成才使用默认名称；后续自动更新不会覆盖自定义名称。

- 片单 1：从 T0DB 筛选中国大陆、综艺/真人秀/音乐/脱口秀类型；只取当前年度已上线的最新普通季，排除未来节目和特别篇，仍在播或近 120 天有正片更新的节目优先，当天有正片更新的置顶，最多 50 部。
- 片单 2：假面骑士 2000 年至今的正剧 TV 系列，按首播时间从新到旧。
- 片单 3：东映超级战队从 1975 年《秘密战队五连者》至今的正剧 TV 系列，按首播时间从新到旧。

所有片单最终都输出 T0DB 关联的 TMDB ID 和类型，封面使用 T0DB 图片服务生成。综艺片单按当前年度最新普通季排序，当天有正片更新的优先，只有检测到当天有新季上线或正片更新时才重排综艺片单。假面骑士和超级战队使用正剧白名单，从 T0DB 查询并排除电影、剧场版、特别篇和衍生剧。

## 第一次设置

1. 在 `Settings → Pages` 设置：

   ```text
   Source：Deploy from a branch
   Branch：main
   Folder：/(root)
   ```

2. 在仓库 `Settings → Secrets and variables → Actions` 新建 Secret：

   ```text
   名称：TODB_API_TOKEN
   值：T0DB Postman 集合中 api_token 的实际值
   ```

   T0DB 对 GitHub Actions 出口请求会返回 403，因此需要这个 Bearer token；不要把 token 写入仓库文件。

3. 到 `Actions` 手动运行“更新综艺、假面骑士与超级战队片单”。第一次成功后，仓库会出现综艺、假面骑士和超级战队的 JSON/GIF 文件。`watch.json`、`cover.gif` 作为旧综艺地址兼容保留。

4. EMOS 动态片单地址：

   ```text
   片单 1（国内流媒体热播综艺）：https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch-variety.json

   片单 2（假面骑士正剧）：https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch-kamen-rider.json

   片单 3（东映超级战队正剧）：https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch-super-sentai.json
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

片单 2 封面（假面骑士正剧）：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/cover-kamen-rider.gif
```

片单 3 封面（东映超级战队正剧）：

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

最后 EMOS 片单 2 地址改成：

```text
https://watch.zzzj.de5.net/watch-variety.json
```

如果使用自定义域名，另外两个地址分别是：

```text
https://watch.zzzj.de5.net/watch-kamen-rider.json
https://watch.zzzj.de5.net/watch-super-sentai.json
```

不要把 GitHub PAT、TMDB Token 写入仓库。GitHub Actions 使用仓库自带的 `GITHUB_TOKEN` 提交每日生成文件。

## 数据源说明

片单 1 使用 T0DB 的 `/api/video/list`、`/api/video/{id}`、`/api/video/{id}/season/{season}/episode/all` 和 `/api/external/list`，筛选中国大陆、综艺类型及当前年度最新普通季，再用最新正片日期将当天更新节目置顶。T0DB 公开接口没有流媒体平台字段，因此不再伪造优酷、腾讯、芒果或爱奇艺平台筛选。当候选不足 50 部时，返回实际筛选到的数量，不混入未来节目或无法关联 TMDB ID 的项目。片单 2 和片单 3 使用固定的正剧系列白名单从 T0DB 查询，按首播时间从新到旧输出；这样只保留假面骑士主剧和东映超级战队正剧，不录入电影、特别篇、剧场版或衍生作品。

