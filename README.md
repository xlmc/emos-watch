# EMOS 豆瓣实时热门华语电视剧片单

这个仓库每天北京时间约 07:50、16:50 读取豆瓣当前热门电视剧综合榜，只筛选中国大陆剧集，保留大陆热门排名前 50；随后用剧名和年份匹配 TMDB，只把 TMDB 的 `tmdb_id` 写入 `watch.json`，并随机选 3 部 TMDB 海报生成静态 `cover.jpg`。

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

3. 保存后到 `Actions` 手动运行“更新豆瓣热门华语电视剧片单”。第一次运行成功后，仓库会出现 `watch.json` 和 `cover.jpg`。

4. EMOS 动态片单地址使用：

   ```text
   https://xlmc.github.io/emos-watch/watch.json
   ```

## 使用你的域名

如果 Cloudflare 可以管理 `zzzj.de5.net` 的 DNS，添加：

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

如果豆瓣某部剧在 TMDB 的名称不同，Action 会生成 `data/unresolved.json` 并停止更新。把对应映射写入 `mapping.json`，格式如下：

```json
{
  "豆瓣ID": 123456
}
```

其中值必须是电视剧的 TMDB ID，不是豆瓣 ID。提交后 Action 会重新生成片单。
