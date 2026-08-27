# EMOS 热门片单

这个仓库每天北京时间约 07:50、16:50 更新两个 EMOS 动态片单。

- 片单 1：联合 TMDB、Bangumi、AniList 获取今年 1 月 1 日至今天已上线的日本 TV 动画，按 `first_air_date` 从新到旧排列，最多 50 部，不足就返回已有数量。
- 片单 2：从 TMDB 筛选中国大陆、综艺类型、优酷/腾讯视频/芒果 TV/爱奇艺网络或流媒体信息，并要求仍在制作、近期播出或即将播出，按热度返回最多 50 部。

两个片单最终都输出 TMDB ID 和类型，封面只下载 TMDB 海报生成。每天从各自片单随机抽取 3 部，生成 960×528 的液态玻璃水波 GIF；当天两次更新保持同一组，第二天自动换图。

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

3. 到 `Actions` 手动运行“更新热门日番与国内流媒体综艺片单”。第一次成功后，仓库会出现 `watch.json`、`watch-japan.json`、`cover.gif` 和 `cover-japan.gif`。

4. EMOS 动态片单地址：

   ```text
   片单 1（日番）：https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch-japan.json
   
   片单 2（国内流媒体热播综艺）：https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch.json
   ```

## CDN 地址

EMOS 推荐使用 jsDelivr CDN 地址：

片单 2（国内流媒体热播综艺）：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch.json
```

片单 1（日番）：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch-japan.json
```

封面地址为：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/cover.gif
```

片单 1 封面：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/cover-japan.gif
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

片单 1 的 BGM 和 AniList 只负责发现、补充和校验日番；为符合 EMOS 接口格式，最终会用 TMDB 搜索映射为 TMDB TV ID，封面也只使用 TMDB 海报。片单 2 使用 TMDB 的综艺类型、国内来源、网络/流媒体字段和播出状态；当指定平台当前不足 50 部时，返回实际筛选到的数量，不混入其他平台或已结束节目。

