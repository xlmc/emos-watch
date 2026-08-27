# EMOS 热门片单

这个仓库每天北京时间约 07:50、16:50 检查两个 EMOS 动态片单。

- 片单 1：获取豆瓣热门的中国大陆电视剧，读取豆瓣详情里的首播/上线日期，按日期从新到旧排列，最多 50 部，再映射为 TMDB TV ID。
- 片单 2：从 TMDB 筛选中国大陆、综艺类型、优酷/腾讯视频/芒果 TV/爱奇艺网络或流媒体信息，并要求仍在制作、近期播出或即将播出；最终只按正片最近一次上线日期从新到旧排列，最多 50 部。

两个片单最终都输出 TMDB ID 和类型，封面只下载 TMDB 海报生成。每天从各自片单随机抽取 3 部，生成 960×528 的液态玻璃水波 GIF；当天两次检查保持同一组，第二天自动换图。视频列表只有检测到当天有电视剧首播或综艺正片上线时才更新；当天没有新正片时保留原视频顺序。封面地址固定不变，Actions 每次生成后会自动刷新 jsDelivr 缓存，因此 EMOS 只需填写一次图片地址。

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

3. 到 `Actions` 手动运行“更新豆瓣热门电视剧与国内流媒体综艺片单”。第一次成功后，仓库会出现 `watch-douban-tv.json`、`watch.json`、`cover-douban-tv.gif` 和 `cover.gif`。

4. EMOS 动态片单地址：

   ```text
   片单 1（豆瓣热门大陆电视剧）：https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch-douban-tv.json
   
   片单 2（国内流媒体热播综艺）：https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch.json
   ```

## CDN 地址

EMOS 推荐使用 jsDelivr CDN 地址：

片单 2（国内流媒体热播综艺）：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch.json
```

片单 1（豆瓣热门大陆电视剧）：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch-douban-tv.json
```

封面地址为：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/cover.gif
```

片单 1 封面（豆瓣热门大陆电视剧）：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/cover-douban-tv.gif
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
https://watch.zzzj.de5.net/watch.json
```

不要把 GitHub PAT、TMDB Token 写入仓库。GitHub Actions 使用仓库自带的 `GITHUB_TOKEN` 提交每日生成文件。

## 数据源说明

片单 1 以豆瓣热门大陆电视剧条目和日期为准，再用 TMDB 搜索映射为 TMDB TV ID，封面只使用 TMDB 海报。片单 2 使用 TMDB 的综艺类型、国内来源、网络/流媒体字段和播出状态，并以 `last_episode_to_air` 的正片日期排序；当指定平台当前不足 50 部时，返回实际筛选到的数量，不混入其他平台或已结束节目。

