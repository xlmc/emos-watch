# EMOS 热门片单

这个仓库每天北京时间约 07:50、16:50 检查 EMOS 动态片单。

- 片单 1：TMDB 大陆电视剧、国漫和国内电影混合片单，顺序固定为最多电视剧 20 部、国漫 20 部、电影 5 部；电视剧取 TMDB 当前仍在更新的剧集，不限制首播月份，允许正常短篇网络剧，排除竖屏微短剧和宣传项目。
- 片单 2：从 TMDB 筛选中国大陆、综艺类型、优酷/腾讯视频/芒果 TV/爱奇艺网络或流媒体信息，并要求仍在制作、近期播出或即将播出；只取当前年度已上线的最新普通季，当天有正片更新的优先，其他按该季上线日期从新到旧排列，最多 50 部。
- 片单 3：假面骑士 2000 年至今的正剧 TV 系列，按首播时间从新到旧。
- 片单 4：东映超级战队从 1975 年《秘密战队五连者》至今的正剧 TV 系列，按首播时间从新到旧。

所有片单最终都输出 TMDB ID 和类型，封面只下载 TMDB 海报生成。电视剧混合片单每天检查 TMDB 当前更新剧集和新上线内容；优先剧情类、片长较长且评分/投票质量较好的剧集，同时允许正常短篇网络剧，不限制首播月份。有新剧、新国漫或新电影时按“电视剧 → 国漫 → 电影”重新生成，电视剧大结局检测到 3 天后自动移除；严格条件不足时返回实际符合条件的数量，不用异常内容补数。无新上线时保持视频顺序，但仍可生成当天随机的液态玻璃 GIF 封面。综艺片单按当前年度最新普通季排序，当天有正片更新的优先，只有检测到当天有新季上线或正片更新时才重排综艺片单。假面骑士和超级战队使用正剧白名单，只查询 TMDB TV 系列并排除电影、剧场版、特别篇和衍生剧。

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

3. 到 `Actions` 手动运行“更新 TMDB 电视剧、综艺、假面骑士与超级战队片单”。第一次成功后，仓库会出现 TMDB 混合片单、综艺、假面骑士和超级战队的 JSON/GIF 文件。`watch.json`、`cover.gif` 作为旧综艺地址兼容保留。

4. EMOS 动态片单地址：

   ```text
   片单 1（TMDB大陆电视剧、国漫与国内电影）：https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch-tmdb-mix-v4.json
   
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

片单 1（TMDB大陆电视剧、国漫与国内电影）：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch-tmdb-mix-v4.json
```

旧综艺封面兼容地址：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/cover.gif
```

综艺封面新地址：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/cover-variety.gif
```

片单 1 封面（TMDB大陆电视剧、国漫与国内电影）：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/cover-tmdb-mix-v4.gif
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

片单 1 最终使用 TMDB 数据：电视剧以 TMDB 详情校验中国大陆、剧情类型、更新状态和质量条件；豆瓣只用于补充 TMDB discover 漏掉的国产剧检索词，不作为最终输出源。电视剧排除动画、综艺、新闻、脱口秀、竖屏微短剧和宣传项目，并按首播时间从新到旧；不限制上个月，当前在更新的老剧也可进入，优先长篇和有足够评分数据的剧集，也允许正常短篇网络剧。国漫调用 TMDB 最新中国大陆中文动画 TV；电影调用 TMDB 近期最新中国大陆非动画、已上映长片。三类分别按上线时间从新到旧排列，再按电视剧、国漫、电影拼接；数量不足时不补入异常内容。脚本每天比较当前 TMDB 结果与已发布片单，发现新上线或到期移除时才更新 JSON；电视剧状态为 `Ended` 且最后一集上线满 3 天后移除。片单 2 使用 TMDB 的综艺类型、国内来源、网络/流媒体字段和播出状态，读取 `seasons` 中当前年度最新普通季的 `air_date`，再用最新普通正片的 `air_date` 将当天更新节目置顶；当天有新季上线或正片更新才会触发更新。当指定平台当前不足 50 部时，返回实际筛选到的数量，不混入其他平台或已结束节目。片单 3 和片单 4 使用固定的正剧系列白名单逐条查 TMDB `/search/tv`，按 `first_air_date` 从新到旧输出；这样只保留假面骑士主剧和东映超级战队主剧，不录入电影、特别篇、剧场版或衍生作品。

