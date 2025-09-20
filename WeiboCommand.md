## 推荐的运行参数
现在您可以使用以下参数来下载所有微博：
### 基础命令（推荐）： 

```bash
python weiboPicDownloader.py -u "芝芝桃桃吖_" -b ":2025-09-19" -i 3 -s 10 -r 3 -v -c "SUB=_2A25FzJMKDeRhGeVH41YT9yfLyzuIHXVmo6rCrDV6PUJbktANLRnRkW1NTrjFDmm_vcD6kt9UOoBq_NHV7v4UlX1J" -d "D:\weiboPic"
```

### 参数说明：
- `-i 2` - 请求间隔2秒，避免被限制
- `-s 10` - 并发数10，平衡速度和稳定性
- `-r 3` - 重试3次，提高成功率
- `-o` - 覆盖已存在的文件

### 如果网络不稳定，使用更保守的设置：
```bash
python weiboPicDownloader.py -u GIVENCHY紀梵希 -i 3 -s 5 -r 5 -o
```

### 如果想指定时间范围：
```bash
# 下载2020年至今的微博
python weiboPicDownloader.py -u 阿璇学妹 -b "2023-02-06:" -i 2 -s 10 -r 3 -o
# 下载2020-2023年的微博
python weiboPicDownloader.py -u GIVENCHY紀梵希 -b "2020-01-01:2023-12-31" -i 2 -s 10 -r 3 -o
```

# 基础下载命令（仅图片）
python weiboPicDownloader.py -u "用户名1" "用户名2" "用户名3"

# 下载图片和视频
python weiboPicDownloader.py -u "用户名1" "用户名2" -v

# 指定保存目录
python weiboPicDownloader.py -u "用户名1" -d "D:\weibo_images"

# 覆盖已存在文件
python weiboPicDownloader.py -u "用户名1" -o

# 从文件批量导入用户
python weiboPicDownloader.py -f "WeiboUserLog.txt"

# 组合使用：从文件导入用户，下载图片和视频，覆盖已存在文件
python weiboPicDownloader.py -f "WeiboUserLog.txt" -v -o

# 高性能设置：增加线程数和重试次数
python weiboPicDownloader.py -f "WeiboUserLog.txt" -v -o -s 50 -r 5

# 设置请求间隔（避免被限制）
python weiboPicDownloader.py -f "WeiboUserLog.txt" -v -o -i 2

# 指定微博ID范围下载（从某个微博ID开始）
python weiboPicDownloader.py -u "用户名1" -b "5200000000000000:"

# 完整配置示例
python weiboPicDownloader.py -f "WeiboUserLog.txt" -v -o -d "D:\weibo_downloads" -s 30 -r 3 -i 1.5

# 单个用户快速下载
python weiboPicDownloader.py -u "小七很贪玩" -v -o

# 多个指定用户下载
python weiboPicDownloader.py -u "小七很贪玩" "云祈ww" "也旎旎" -v -o

# 注意事项：
# 3. 使用 -s 参数可以调整线程数（默认20，建议10-50）
# 4. 使用 -r 参数可以调整重试次数（默认2）
# 5. 使用 -i 参数可以调整请求间隔（默认1秒）
# 6. 使用 -d 参数可以指定保存目录
# 7. 使用 -f 参数可以从文件批量导入用户
# 8. 使用 -b 参数可以指定微博ID或日期范围
# 10. 如果遇到限制，可以增加 -i 参数的值或减少 -s 参数的值

## 本次对话摘要（问题与修复）
- **现象**: 使用昵称下载时，出现 `invalid account` 或解析到错误 UID（如“E姐写真集”昵称解析成 `2980015457`，而真实 UID 为 `7886910382`）。日志出现 `visitor.passport.weibo.cn` 访客跳转，或扫描结果为 0 资源。
- **根因**:
  - 默认 `SUB` Cookie 过期/无效，未登录被导向访客页，昵称→UID 解析失败。
  - 旧的 `nickname_to_uid` 逻辑在访客重定向与个性域名场景下不够稳健。
- **修复**:
  - 已增强 `nickname_to_uid`：
    - 直接从最终 URL 提取 `/u/<uid>`（兼容后缀参数）。
    - 如命中 `visitor` 跳转，解析其 `url` 参数中的真实目标，再提取 UID，并必要时二次请求目标提取。
    - 新增接口 `https://weibo.com/ajax/profile/info?custom=<昵称>` 获取 UID（更稳）。
    - 最后再用 `m.weibo.cn` 搜索接口兜底。
- **使用建议**:
  - 仍可直接用“昵称”运行命令；若已知 UID，优先用 UID，最稳。
  - 提供有效 `SUB` Cookie 可显著降低跳转/限流问题。
  - 若遇到 432 限流或 0 资源：增大 `-i`（如 3~5）、降低 `-s`（如 5），并检查 `-b` 时间范围内是否确有图/视频内容。

### 示例
```bash
# 使用昵称（已增强解析）并携带有效 SUB
python weiboPicDownloader.py -u "E姐写真集" -b "2025-01-01:" -i 2 -s 10 -r 3 -v -c "SUB=你的SUB"

# 使用 UID（最稳）
python weiboPicDownloader.py -u 7886910382 -b "2025-01-01:" -i 2 -s 10 -r 3 -v -c "SUB=你的SUB"
```

## 对话变更摘要（2025-09）

- **API 错误诊断**: 当 `ok != 1` 且 `msg` 为空时，打印响应片段，提升定位能力。
- **请求头与 Cookie**: 
  - 仅在提供 Cookie 时设置 `Cookie` 头，补充 `Accept`、`X-Requested-With` 更贴近 m 站；
  - 下载直链请求也携带 Cookie，避免直链 403/未登录。
- **极验拦截回退**: 识别 m 站返回 `ok:-100` 且包含 `geetest` 时，自动切换到桌面接口 `https://weibo.com/ajax/statuses/mymblog`，并从 Cookie 中提取 `XSRF-TOKEN` 注入 `X-XSRF-TOKEN` 头以提升成功率。
- **移除默认 SUB**: 代码中已移除写死的默认 `SUB`，必须通过命令行 `-c` 或环境变量提供。

### 推荐提供 Cookie 的方式

- 命令行参数（显式且便于替换）
```bash
python weiboPicDownloader.py -f "WeiboUserLog.txt" -v -i 3 -s 6 -r 3 -c "SUB=你的SUB; XSRF-TOKEN=你的XSRF"
```

- Windows PowerShell 环境变量（避免在命令行历史中暴露）
```powershell
$env:WEIBO_SUB="SUB=你的SUB; XSRF-TOKEN=你的XSRF"
python weiboPicDownloader.py -f "WeiboUserLog.txt" -v
```

### 极验/限流建议

- 遇到 `ok:-100 geetest` 或 432 限流：将 `-i` 调高到 3~5，将 `-s` 降低到 4~6，并保证提供 `XSRF-TOKEN`（桌面接口）。
- 检查 `-b` 的时间范围是否覆盖实际发图/视频日期。