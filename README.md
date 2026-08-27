# EMOS 豆瓣实时热门大陆影视与国漫片单

这个仓库每天北京时间约 07:50、16:50 读取豆瓣当前热门数据，只保留中国大陆地区内容，并生成固定数量的混合片单：

- 20 部大陆热门电视剧
- 10 部大陆热门电影
- 20 部大陆热门国漫（大陆动画不足 20 部时，按当前热门顺序用日番补位）

脚本使用豆瓣的实时排序选择条目，再用 TMDB 匹配对应的 `tmdb_id`。电视剧和电影始终只保留中国大陆；国漫优先中国大陆，数量不足时才加入日本动画补位。`watch.json` 只提供 TMDB ID 和类型，不公开 TMDB Token。每天按北京时间从片单中随机抽取 3 部，生成 960×528 的液态玻璃水波动图 `cover.gif`；当天两次更新保持同一组，第二天自动换图。

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

3. 到 `Actions` 手动运行“更新豆瓣热门大陆影视与国漫片单”。第一次成功后，仓库会出现 `watch.json` 和 `cover.gif`。

4. EMOS 动态片单地址：

   ```text
   https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch.json
   ```

## CDN 地址

EMOS 推荐使用 jsDelivr CDN 地址：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/watch.json
```

封面地址为：

```text
https://cdn.jsdelivr.net/gh/xlmc/emos-watch@main/cover.gif
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

最后 EMOS 地址改成：

```text
https://watch.zzzj.de5.net/watch.json
```

不要把 GitHub PAT、TMDB Token 写入仓库。GitHub Actions 使用仓库自带的 `GITHUB_TOKEN` 提交每日生成文件。

## 匹配失败时

如果某个条目在 TMDB 中名称不同，Action 会生成 `data/unresolved.json` 并停止更新。把对应映射写入 `mapping.json`，格式如下：

```json
{
  "豆瓣ID": 123456
}
```

电影和电视剧都填写 TMDB 对应类型的 ID；提交后 Action 会重新生成片单。

