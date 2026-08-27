# EMOS 热门片单

这个仓库每天北京时间约 07:50、16:50 检查 EMOS 动态片单。

- 片单 1：保留现有豆瓣热门中国大陆电视剧片单；本次自动任务不修改电视剧片单。
- 片单 2：从 TMDB 筛选中国大陆、综艺类型、优酷/腾讯视频/芒果 TV/爱奇艺网络或流媒体信息，并要求仍在制作、近期播出或即将播出；只取当前年度已上线的最新普通季，当天有正片更新的优先，其他按该季上线日期从新到旧排列，最多 50 部。
- 片单 3：假面骑士 2000 年至今的正剧 TV 系列，按首播时间从新到旧。
- 片单 4：东映超级战队从 1975 年《秘密战队五连者》至今的正剧 TV 系列，按首播时间从新到旧。

所有片单最终都输出 TMDB ID 和类型，封面只下载 TMDB 海报生成。电视剧片单保持现有内容；综艺片单按当前年度最新普通季排序，当天有正片更新的优先，只有检测到当天有新季上线或正片更新时才重排并刷新综艺片单和封面，没有更新时保持原样。假面骑士和超级战队使用正剧白名单，只查询 TMDB TV 系列并排除电影、剧场版、特别篇和衍生剧。两个新片单每天生成当天随机的液态玻璃 GIF 封面，地址固定不变，Actions 每次生成后会自动刷新 jsDelivr 缓存。

## 第一次设置

1. 在仓库 `Settings → Secrets and variables → Actions` 新建 Secret：

   ```text
   名称：TMDB_ACCESS_TOKEN
   值：TMDB API Read Access Token
   ```

2. 在 `Settings → Pages` 设置：

   ```text
   Source：Deploy from a branch
   Branch：main
   Folder：/(root)
   ```

3. 到 `Actions` 手动运行“更新豆瓣热门电视剧、综艺、假面骑士与超级战队片单”。第一次成功后，仓库会出现电视剧、综艺、假面骑士和超级战队的 JSON/GIF 文件。`watch.json`、`cover.gif` 作为旧地址兼容保留。

4. EMOS 动态片单地址：

   ```text
   片单 1（豆瓣热门大陆电视剧）：https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch-douban-tv.json
   
   片单 2（国内流媒体热播综艺）：https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch-variety.json

   片单 3（假面骑士正剧）：https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch-kamen-rider.json

   片单 4（东映超级战队正剧）：https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch-super-sentai.json
   ```

## CDN 地址

EMOS 推荐使用 jsDelivr CDN 地址：

片单 2（国内流媒体热播综艺）：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch-variety.json
```

片单 1（豆瓣热门大陆电视剧）：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch-douban-tv.json
```

旧综艺封面兼容地址：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/cover.gif
```

综艺封面新地址：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/cover-variety.gif
```

片单 1 封面（豆瓣热门大陆电视剧）：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/cover-douban-tv.gif
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

片单 1 以豆瓣热门大陆电视剧条目和日期为准，再用 TMDB 搜索映射为 TMDB TV ID，封面只使用 TMDB 海报。片单 2 使用 TMDB 的综艺类型、国内来源、网络/流媒体字段和播出状态，读取 `seasons` 中当前年度最新普通季的 `air_date`，再用最新普通正片的 `air_date` 将当天更新节目置顶；当天有新季上线或正片更新才会触发更新。当指定平台当前不足 50 部时，返回实际筛选到的数量，不混入其他平台或已结束节目。片单 3 和片单 4 使用固定的正剧系列白名单逐条查 TMDB `/search/tv`，按 `first_air_date` 从新到旧输出；这样只保留假面骑士主剧和东映超级战队主剧，不录入电影、特别篇、剧场版或衍生作品。

