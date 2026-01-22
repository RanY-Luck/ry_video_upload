# 抖音Cookie完整获取指南

## ⚠️ 重要提示

你当前遇到的问题:
1. ✅ Cookie格式已修复(从多行改为单行)
2. ⚠️ 采集到0个作品 - 可能原因:
   - Cookie不完整,缺少关键字段
   - Cookie权限不足(未登录或登录状态失效)
   - 目标用户确实没有发布作品
   - 目标用户设置了隐私保护

## 📋 完整Cookie获取步骤

### 方法一: 使用开发者工具(推荐)

1. **打开抖音网页版**
   - 访问: https://www.douyin.com/
   - **必须登录你的抖音账号**

2. **打开开发者工具**
   - 按 `F12` 键
   - 或右键点击页面 → 选择"检查"

3. **切换到Network标签**
   - 点击顶部的 `Network` (网络) 标签
   - 勾选 `Preserve log` (保留日志)

4. **访问目标用户主页**
   - 在浏览器地址栏输入目标用户的主页URL
   - 例如: `https://www.douyin.com/user/MS4wLjABAAAA0r-B3uubLdhDTB1PuYZ-uKtjoD86_b1aW8HzG-G0DRg`
   - 按回车访问

5. **查找API请求**
   - 在Network标签的请求列表中,找到名为 `aweme_post` 或 `user` 的请求
   - 点击该请求

6. **复制完整Cookie**
   - 在右侧面板中找到 `Request Headers` (请求头)
   - 找到 `Cookie:` 字段
   - **复制整行Cookie值**(从第一个字符到最后)

7. **粘贴到配置文件**
   - 打开 `my_apps.yaml`
   - 找到 `douyin.cookie:` 行
   - 粘贴完整的Cookie(必须是单行)

### 方法二: 使用浏览器扩展(简单)

1. **安装Cookie编辑器扩展**
   - Chrome: [EditThisCookie](https://chrome.google.com/webstore/detail/editthiscookie/fngmhnnpilhplaeedifhccceomclgfbg)
   - Edge: 在扩展商店搜索"Cookie Editor"

2. **导出Cookie**
   - 访问 https://www.douyin.com/ 并登录
   - 点击扩展图标
   - 选择"Export" → "Netscape HTTP Cookie File"
   - 复制所有Cookie

3. **转换格式**
   - 将Cookie转换为 `key1=value1; key2=value2` 格式
   - 粘贴到 `my_apps.yaml`

## 🔍 必需的Cookie字段

完整的抖音Cookie应该包含以下关键字段:

```
msToken=xxx; 
ttwid=xxx; 
__ac_nonce=xxx; 
__ac_signature=xxx; 
passport_csrf_token=xxx; 
passport_csrf_token_default=xxx; 
s_v_web_id=xxx; 
sessionid=xxx; 
sessionid_ss=xxx; 
sid_guard=xxx; 
sid_tt=xxx; 
sid_ucp_v1=xxx; 
ssid_ucp_v1=xxx; 
store-region=xxx; 
store-region-src=xxx; 
uid_tt=xxx; 
uid_tt_ss=xxx
```

**你当前的Cookie只有3个字段,这是不够的!**

## ✅ 正确的Cookie示例

```yaml
douyin:
  cookie: msToken=FTG__I_qCKTsW9xJeCUGE9hwEzC_SVOjxL_WUazyYunN3WNt7VZWVkHqX4zIkBziZOv5XONPTiN80dmo6RNmFW3KD0KXJsJhTp2oI-w5ZWURpNM91nIcTQAYeMGp7nk=; ttwid=1%7C9Mic0Lvfa_WZ5ICeMY5oXtr7fXfdiJD4MfLYscRd6T0%7C1768978564%7C668fc86dc679da33202192a67ca2a831f523a84238a6056c777c351350b591b9; __ac_nonce=7597705065105180198; __ac_signature=_02B4Z6wo00f01example; passport_csrf_token=example; s_v_web_id=verify_example; sessionid=example; sessionid_ss=example; sid_guard=example; sid_tt=example; uid_tt=example; uid_tt_ss=example
```

## 🔧 验证Cookie是否有效

运行以下命令测试:

```bash
f2 dy -c my_apps.yaml -u https://www.douyin.com/user/MS4wLjABAAAA0r-B3uubLdhDTB1PuYZ-uKtjoD86_b1aW8HzG-G0DRg -m post
```

**成功的标志**:
- 能看到用户信息
- 能看到作品列表
- 开始下载视频

**失败的标志**:
- "第 X 页没有找到作品"
- "所有作品采集完毕" 但实际有作品
- "Cookie失效" 或 "请登录"

## 🎯 快速解决方案

### 方案1: 重新获取完整Cookie

1. 清除浏览器缓存和Cookie
2. 重新登录抖音网页版
3. 访问任意用户主页
4. 按F12 → Network → 找到请求 → 复制完整Cookie
5. 更新到 `my_apps.yaml`

### 方案2: 使用手机抓包(高级)

如果网页版Cookie不work,可以尝试抓取手机APP的Cookie:
1. 安装抓包工具(如Charles、Fiddler)
2. 配置手机代理
3. 打开抖音APP
4. 抓取请求中的Cookie
5. 复制到配置文件

### 方案3: 更换目标用户

当前用户可能:
- 没有发布任何作品
- 设置了隐私保护
- 账号被封禁

尝试采集其他用户:
```python
# main.py 第72行
self.MAIN_COMMAND = ['f2', 'dy', '-c', 'my_apps.yaml', '-u', 'https://www.douyin.com/user/其他用户ID']
```

推荐测试用户(公开账号):
- 抖音官方账号
- 知名博主账号

## 📊 Cookie有效期

- **短期Cookie**: msToken、ttwid (几小时到1天)
- **长期Cookie**: sessionid、sid_guard (几天到几周)
- **建议**: 每天刷新一次Cookie

## 🚨 常见错误

### 错误1: Cookie格式错误
```yaml
# ❌ 错误 - 多行格式
cookie:
  msToken=xxx;
  ttwid=xxx;

# ✅ 正确 - 单行格式
cookie: msToken=xxx; ttwid=xxx; __ac_nonce=xxx
```

### 错误2: Cookie不完整
```yaml
# ❌ 错误 - 只有3个字段
cookie: msToken=xxx; ttwid=xxx; __ac_nonce=xxx

# ✅ 正确 - 包含所有必需字段
cookie: msToken=xxx; ttwid=xxx; __ac_nonce=xxx; sessionid=xxx; sid_guard=xxx; ...
```

### 错误3: Cookie包含换行符
```yaml
# ❌ 错误 - 有换行
cookie: msToken=xxx;
        ttwid=xxx

# ✅ 正确 - 单行无换行
cookie: msToken=xxx; ttwid=xxx
```

## 💡 下一步

1. **立即操作**: 按照"方法一"重新获取完整Cookie
2. **验证**: 运行测试命令确认Cookie有效
3. **启动**: `python main.py` 开始自动采集

## 📞 需要帮助?

如果仍然无法解决:
1. 检查是否已登录抖音网页版
2. 确认目标用户有公开作品
3. 尝试更换浏览器(Chrome/Edge)
4. 查看日志文件 `logs/f2-*.log` 了解详细错误
