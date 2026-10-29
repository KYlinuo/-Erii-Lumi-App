# 公网部署说明（让 iPhone 用 5G / 流量也能连）

现在本地开发用的是「局域网 IP 直连」（`http://192.168.31.83:8000`），
只能同一 Wi-Fi 下用。要支持流量访问，需要把后端放到**有公网地址的服务器**上，
再用域名 + HTTPS 反代。

## 你需要的三样东西（缺一不可）

| 项 | 说明 |
|---|---|
| 一台公网服务器 | 1核1G 的轻量云（阿里云/腾讯云等）即可，约几十元/月 |
| 一个域名 | 已备案更稳；用 Caddy 会自动申请免费 HTTPS 证书 |
| 域名解析 | 把域名 A 记录指向服务器公网 IP |

> DeepSeek API Key 已经在 `.env` 里了，部署到服务器后照填即可，手机端永不接触密钥。

## 最短路径（有服务器 + Docker）

```bash
# 1. 在服务器上装 Docker
curl -fsSL https://get.docker.com | sh

# 2. 把整个仓库拷上去（或 git clone）
git clone <你的仓库地址> && cd <仓库>

# 3. 改域名
vim deploy/Caddyfile        # 把 your-domain.example.com 换成你的域名

# 4. 准备环境变量
cp .env.example deploy/.env
vim deploy/.env             # 填 LUMI_API_KEY、LUMI_ACCESS_TOKEN

# 5. 一键起
cd deploy && docker compose up -d
```

## 部署后

1. Caddy 自动申请并续期 HTTPS 证书（全程免手动）。
2. iPhone 设置 → 服务器地址填 `https://你的域名`，点「重新检测」。
3. 之后无论 Wi-Fi 还是 5G，都能连。

## 不用 Docker 的替代方案

```bash
# 服务器上直接跑
pip install -r backend/requirements.txt
cp .env.example .env && vim .env
uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*'

# 再装 Caddy 反代
#   https://caddyserver.com/docs/install
#   把 deploy/Caddyfile 内容放到 /etc/caddy/Caddyfile
```

## 安全约定

- 访问令牌（`LUMI_ACCESS_TOKEN`）是服务端鉴权，手机存 Keychain，不随 iCloud 备份。
- 后端已启用代理头信任，能正确识别 HTTPS；未接反代时直接 HTTP 也照常工作。
- 公网务必用 HTTPS（Caddy 已自动处理），不要裸奔 HTTP。
