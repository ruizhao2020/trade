# SignalLayer 部署到阿里云 ECS（单机 Docker Compose）

域名已确认 **`caopan.me`**，ECS 在中国大陆地域且**备案已通过** —— 也就是说 80/443 从
公网可达，走下面这条标准路径即可（不需要备案相关的变通方案）。

目标：

| 域名 | 内容 | 谁能看 |
| --- | --- | --- |
| `caopan.me` | 公开站（`dist-public`：只有指标分析，无登录入口） | 任何人 |
| `work.caopan.me` | 私有站（`dist-private`：登录 + 完整工作区） | 登录且已通过审核的账号 |

## 整体顺序（照着走，不要跳步）

> **懒人路径**：不想一步步敲的话，仓库里带了一个幂等脚本，一条命令做完第 1–6 步
> （生成 `.env` 随机密钥、构建、启动、**用真的读库请求确认数据库通了**、签证书、起 nginx、
> 验收两个域名并打印后续要做的两件事）：
>
> ```bash
> cd /root/trade
> bash deploy/ecs/scripts/first-deploy.sh --check   # 先干跑一遍：只检查，不改任何东西
> bash deploy/ecs/scripts/first-deploy.sh           # 正式部署（会问管理员密码与证书邮箱，其余自动生成）
> ```
>
> 下面各节是同一件事的手工版本 —— 脚本已经覆盖它们，留着是为了让你知道它在做什么、
> 出问题时该看哪一节。手工执行也完全可以。

| 步骤 | 做什么 | 关键点 |
| --- | --- | --- |
| 1 | [架构与端口暴露](#1-架构与端口暴露) | 只有 nginx 的 80/443 对公网开 |
| 2 | [ECS 准备](#2-ecs-准备) | 安全组 22/80/443；装 Docker + 配镜像加速 |
| 3 | [域名解析](#3-域名解析) | `@` 与 `work` 两条 A 记录指向该 ECS |
| 4 | [拉代码、写配置](#4-拉代码写配置) | `.env` 里换掉 token 密钥与两个密码 |
| 5 | [首次签发证书](#5-首次签发证书) | **先签证书，再起 nginx**（顺序不能反） |
| 6 | [验证](#6-验证) | 必须用读库接口验证，不能用 `/health` |
| 7 | [日常运维](#7-日常运维) | 证书 reload、备份 crontab、升级 |
| 8 | [数据迁移](#8-把现有数据搬到-ecs可选) | 可选：把现有库搬过来 |

中国大陆 ECS 的一个顺带好处：后端要连的 akshare 数据源都是境内站点，拉行情比境外机器快
且不依赖代理。（反过来说，万一将来把服务挪到境外地域，行情抓取会明显变慢，别把地域换错。）

---

## 0. 上线前的三个前置检查

备案已通过，但这三件事仍要自己确认一遍，它们是"页面打不开"的绝大多数原因：

```bash
# 1) 域名确实解析到这台 ECS 的公网 IP（备案也要求域名指向该接入的 ECS）
getent hosts caopan.me work.caopan.me

# 2) 本机没占 80/443（例如系统自带 nginx/apache 抢了端口，compose 会启动失败）
sudo ss -lntp | grep -E ':80|:443' || echo "80/443 空闲"

# 3) 安全组 + 系统防火墙都放行（阿里云控制台的安全组与 OS 防火墙是两回事）
sudo firewall-cmd --list-services 2>/dev/null || sudo ufw status 2>/dev/null || true
```

**证书签发的备用方案**：大陆机器连 Let's Encrypt 的
`acme-v02.api.letsencrypt.org` 偶尔会超时（不是常态，但会遇上）。如果第 5 节反复报连接
超时，就改用阿里云「数字证书管理服务」申请免费 DV 证书，下载后把
`fullchain.pem` / `privkey.pem` 放到容器的 `/etc/letsencrypt/live/caopan.me/` 下
（路径与 edge.conf 一致），再 `docker compose -f deploy/ecs/docker-compose.yml
--env-file deploy/ecs/.env restart nginx`。这条路要手动续（阿里云免费证书有效期较短），
所以能签 Let's Encrypt 就别换。

> **别长期关掉 80**：备案通过后阿里云会抽查域名的可访问性（80 端口要能响应），
> 本文档的配置在 80 上保留了 ACME 校验与 301 跳转，正常跑着就满足要求。
> 如果以后排障时长时间停掉 nginx，记得不要停太久。

---

## 1. 架构与端口暴露

```
                    ┌─────────────────────────── nginx 容器（唯一对公网开 80/443） ──┐
 caopan.me ────────▶│ server caopan.me       → root /usr/share/nginx/public        │
 work.caopan.me ───▶│ server work.caopan.me  → root /usr/share/nginx/private       │
                    │ 两个 server 的 /api/ 与 /ws → proxy_pass http://backend:8000 │
                    └───────────────────────────────────────────────────────────────┘
                                              │  compose 内网（不发布端口）
                        ┌─────────────────────┴──────────────────────┐
                        ▼                                            ▼
              backend 容器（只绑 127.0.0.1:8000）            mysql 容器 / redis 容器
              连通腾讯云以外的外部数据源：akshare
```

- 前端产物里用的是**同源相对地址** `/api/v1`，所以两个域名共用同一个后端、没有跨域，
  换域名/加 CDN 都不需要重新构建前端。
- 公开站与私有站的差别只在**静态产物不同**：`src/public-main.tsx` 不含登录与私有模块；
  真正的权限判定在**后端**（Token + `private.access` + 模块权限），前台页面差异不是安全边界。
- 端口暴露：只有 nginx 的 80/443 对外；后端只绑回环；MySQL/Redis 完全不发布端口。

---

## 2. ECS 准备

**规格建议**：2 核 4G 起（后端要跑 pandas/akshare，1 核 2G 会在拉数据时被 OOM 杀），
系统盘 ≥ 40G ESSD（镜像约 3G，行情表会长期增长）。

**安全组**（阿里云控制台 → 网络与安全 → 安全组 → 入方向）：

| 端口 | 来源 | 说明 |
| --- | --- | --- |
| 22 | 你的办公/家庭 IP（尽量不要 0.0.0.0/0） | SSH |
| 80 | 0.0.0.0/0 | 证书校验 + HTTP 跳转 |
| 443 | 0.0.0.0/0 | 正式访问 |

**不要**开 3306 / 6379 / 8000。

**系统自带防火墙**也要放行（阿里云 Linux/ CentOS 常见 firewalld 默认开着，安全组通了
本机仍会被挡）：

```bash
# 阿里云 Linux / CentOS（firewalld）
sudo firewall-cmd --permanent --add-service=http --add-service=https
sudo firewall-cmd --reload

# Ubuntu / Debian（ufw）
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw enable
```

**装 Docker + Compose 插件**：

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo systemctl enable --now docker
docker compose version   # 应输出 v2.x
```

大陆机器建议改用阿里云的 docker-ce 源（`download.docker.com` 往往只有几十 KB/s）：

```bash
# Alibaba Cloud Linux 3 / CentOS / RHEL
sudo dnf install -y dnf-utils
sudo yum-config-manager --add-repo https://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
# Ubuntu / Debian 把上面的 repo 换成 https://mirrors.aliyun.com/docker-ce/linux/ubuntu
sudo systemctl enable --now docker
```

两种方式都行，装完必须确认 `docker compose version` 有输出 —— 本文档全部命令依赖 compose v2。

**配镜像加速**（国内直连 Docker Hub 往往超时。加速地址在阿里云控制台
「容器镜像服务 → 镜像工具 → 镜像加速器」里拿）：

```bash
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json >/dev/null <<'JSON'
{
  "registry-mirrors": ["https://<你的加速器地址>.mirror.aliyuncs.com"],
  "log-driver": "json-file",
  "log-opts": { "max-size": "50m", "max-file": "3" }
}
JSON
sudo systemctl restart docker
```

---

## 3. 域名解析

在域名 DNS 处添加两条 A 记录，指向 ECS 公网 IP：

| 记录类型 | 主机记录 | 值 |
| --- | --- | --- |
| A | `@` | ECS 公网 IP |
| A | `work` | ECS 公网 IP |

验证（在 ECS 上执行）：`getent hosts caopan.me work.caopan.me` 都应返回你的公网 IP。

---

## 4. 拉代码、写配置

```bash
cd /root
git clone <你的仓库地址> trade
cd trade

# 要么手工：cp deploy/ecs/.env.example deploy/ecs/.env && vim deploy/ecs/.env
# 要么交给脚本：它会在这一步生成随机密钥、问你管理员密码与证书邮箱
bash deploy/ecs/scripts/first-deploy.sh
```
（下面手工说明只在你选择手工配置时才需要。）

`.env` 里**必须**改的几项（其余可留默认）：

```bash
openssl rand -base64 32   # 生成随机串，用于下面两个密钥
```

- `SIGNAL_TOKEN_SECRET`：登录令牌签名密钥。留成默认值且 `SIGNAL_DEBUG=false` 时，
  后端会**直接拒绝启动**（这是刻意留的保护）。
- `SIGNAL_BOOTSTRAP_ADMIN_PASSWORD`：首个管理员密码。
- `MYSQL_ROOT_PASSWORD`：容器内 root（不对公网暴露，但仍按秘密对待）。
- `SIGNAL_MYSQL_PASSWORD`：后端业务账号密码。

> **注意 `$` 符号**：docker compose 会对 `.env` 里的 `$` 做变量插值。用
> `openssl rand -base64 32` 生成的串只含 `A-Za-z0-9+/=`，是安全的；
> 若你自己设了带 `$` 的密码，必须写成 `$$`。

`.env` 已被仓库 `.gitignore` 的 `**/.env` 忽略，不会被提交。

后面几条命令要用到里面的值，先这样取出来（**不要** `source` 整个 `.env`：里面的值若含
`$` 或空格，会被 shell 展开成别的东西，而你看到的是"密码错误"这种误导性报错）：

```bash
cd /root/trade
ROOT_PW=$(grep -E '^MYSQL_ROOT_PASSWORD=' deploy/ecs/.env | cut -d= -f2-)
ACME_EMAIL=$(grep -E '^ACME_EMAIL=' deploy/ecs/.env | cut -d= -f2-)
C="docker compose -f deploy/ecs/docker-compose.yml --env-file deploy/ecs/.env"
```

（`$C` 这个简写后面一直用。）

---

## 5. 首次签发证书

顺序很重要：nginx 还没起 → 80 端口空闲 → 用 certbot 的 standalone 模式直接签发。
（nginx 起来之后再签就用 webroot，见第 7 节「证书续期」。）

```bash
# 先起数据库和后端（后端首次启动会建表、初始化管理员，约 1 分钟）
$C up -d --build mysql redis
$C up -d backend

# 签发（两个域名放在同一张证书里，证书目录名取第一个 -d 域名 = caopan.me）
#
# ⚠️ 必须带 --entrypoint certbot：certbot 服务的 entrypoint 被改成了自动续期循环，
#    不覆盖它的话后面这些参数会被那个 shell 循环忽略，命令看起来在跑、证书根本没签。
docker compose -f deploy/ecs/docker-compose.yml --env-file deploy/ecs/.env \
  run --rm --entrypoint certbot -p 80:80 certbot certonly --standalone \
  -d caopan.me -d work.caopan.me \
  --email "$ACME_EMAIL" --agree-tos --no-eff-email

# 证书就位后再起 nginx 与自动续期
$C up -d nginx certbot
```

若这步报 `Timeout during connect`：先确认 DNS/安全组/系统防火墙都通（备案已通过，不是备案
问题），也别反复重试（Let's Encrypt 对失败有频率限制）。若网络确实没问题却仍连不上 ACME
服务器，改用第 0 节提到的阿里云免费证书方案。

---

## 6. 验证

```bash
$C ps                            # 全部 Up/healthy
curl -I https://caopan.me        # 200
curl -I https://work.caopan.me   # 200
curl -s https://caopan.me/api/v1/symbols/markets | head -c 200   # 公开站的行情接口可用
```

**最关键的一步：确认后端真的连上了 MySQL。**
MySQL 连不上时后端**不会**切换到 SQLite（`app/db/__init__.py::_get_db_url()` 恒为配置里的
MySQL），它只是打一条 warning 然后继续启动。结果是：`/health` 依然返回 200、前端页面正常
打开，但**每个需要数据库的接口都返回 500**。这个组合最容易让人误判成"前端坏了"。

```bash
# 1) 看后端有没有连着库
$C logs backend | grep -iE "Database initialized|Database init failed"
# 期望：只有 "Database initialized"，没有 "Database init failed"

# 2) 别用 /health 判断：它不查库，永远 200
$C exec -T backend curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/health

# 3) 用一个真的读库的请求判断：拿不存在的账号登录
$C exec -T backend curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  -H "Content-Type: application/json" \
  -d '{"username":"__probe__","password":"__nope__"}' \
  http://127.0.0.1:8000/api/v1/auth/login
# 期望：401（= 库通了、users 表查得到）。500 就是没连上库
# 再来一个业务接口确认中间件与模块表也在正常工作：
$C exec -T backend curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/v1/symbols/markets
# 期望：200

# 4) 交叉确认：MySQL 里应该已经有启动时创建的管理员
$C exec -T mysql mysql -uroot -p"$ROOT_PW" -e "select id,username,status from signal_layer.users"
# 期望：至少一行 admin / active。空表说明后端根本没能建表
```

然后浏览器打开 `https://work.caopan.me`，用 `SIGNAL_BOOTSTRAP_ADMIN_USERNAME/PASSWORD`
登录，进「系统 → 用户管理」确认模块与角色都在。

**Swagger 不对外**：后端的 `/docs`、`/openapi.json` 在中间件里属于「公开路径」（不需要
Token），所以 nginx 的配置刻意没有反代它们 —— 对外访问 `https://work.caopan.me/docs` 只会
落到前端路由。要看得用 SSH 隧道（后端只绑了回环）：

```bash
ssh -N -L 8001:127.0.0.1:8000 root@<ECS 公网 IP>   # 在你自己的电脑上执行
# 然后本地浏览器打开 http://127.0.0.1:8001/docs
```

---

## 7. 日常运维

### 日志

```bash
$C logs -f backend        # 后端（含 akshare 拉取、回测、错误）
$C logs -f nginx          # 访问与 5xx
$C logs --tail=100 backend | grep -i error
```

### 升级代码

```bash
cd /root/trade && git pull
$C up -d --build          # 只重建有变化的镜像，随后按依赖顺序重启
$C ps                     # 确认 healthy
```

前端是打进镜像的静态文件，所以**前端改动也必须重新 build**（`up -d --build` 已包含）。
若怀疑构建缓存导致没更新：`$C build --no-cache nginx`。

### 证书续期（有一个容易漏的坑）

certbot 容器每 12 小时尝试一次自动续期，证书文件会更新 —— **但 nginx 不会自动重新加载，
它仍然用内存里的旧证书**，等旧证书过期就会出现「续期成功却打不开」。所以加一条每天一次的
无损 reload：

```bash
sudo crontab -e
# 每天 04:30 重载 nginx（reload 不断连接，成本可忽略）
30 4 * * * cd /root/trade && docker compose -f deploy/ecs/docker-compose.yml --env-file deploy/ecs/.env exec -T nginx nginx -s reload
```

检查证书状态：`docker compose -f deploy/ecs/docker-compose.yml --env-file deploy/ecs/.env run --rm --entrypoint certbot certbot certificates`

### 备份与恢复

```bash
# 手动备份（保留最近 7 份，写到 deploy/ecs/backups/）
/root/trade/deploy/ecs/scripts/backup-db.sh

# 挂到 crontab（凌晨 3 点）
sudo crontab -e
0 3 * * * /root/trade/deploy/ecs/scripts/backup-db.sh >> /var/log/signal-backup.log 2>&1

# 恢复（ROOT_PW 见第 4 节）
gunzip -c deploy/ecs/backups/signal_layer-20261008-030000.sql.gz | \
  $C exec -T mysql mysql -uroot -p"$ROOT_PW" signal_layer
```

> **别把备份只放在这台机器上**：备份文件建议再同步到 OSS
> （`ossutil cp -r deploy/ecs/backups/ oss://<bucket>/signal-layer/`），
> 否则磁盘故障时备份和库一起没。

### 磁盘

行情数据是按 `{symbol}_{timeframe}` 动态建的表，会持续增长：

```bash
df -h                                   # 关注 /var/lib/docker 所在分区
docker system df
docker image prune -f                   # 清理旧镜像层
```

---

## 8. 把现有数据搬到 ECS（可选）

你想保留本机/腾讯云那套库里的用户、策略、权限时：

1. 在能连到现有库的机器上导出：

   ```bash
   mysqldump -h <现有库地址> -uroot -p --single-transaction --routines \
     --databases stock > stock.sql
   ```

2. 上传并导入。**把库名保持成 `stock`** 最省事（`deploy/ecs/.env` 里
   `SIGNAL_MYSQL_DATABASE=stock`），因为 mysqldump 的 `--databases` 会带上
   `CREATE DATABASE`/`USE`，改名容易漏掉动态行情表：

   ```bash
   scp stock.sql root@<ECS IP>:/root/
   cd /root/trade
   $C exec -T mysql mysql -uroot -p"$ROOT_PW" < /root/stock.sql
   ```

3. 建表脚本（`001/002/010`）只在**空数据卷**上执行，导入过的库不会被它们覆盖；
   后端启动时的 `create_all + 补列` 会把缺的列补齐。导完后改
   `SIGNAL_MYSQL_DATABASE` 与库名一致，重启 backend 即可。

如果不需要历史数据，直接跳过本节：空库启动后，行情表会在你第一次查询某个标的时
由后端自动向 akshare 拉取并落库（首次查询会慢一些）。

---

## 9. 排障对照表

| 现象 | 原因 / 处理 |
| --- | --- |
| `curl http://caopan.me` 超时，但 `curl http://<IP>` 通 | DNS 未生效（`getent hosts caopan.me` 看解析），或安全组/系统防火墙未放行 80 |
| `certbot` 报 `Timeout during connect` | 80 未通（回到第 0 节的前置检查）；确认网络正常但仍反复超时 = 大陆机器连 ACME 偶发问题，改用第 0 节的阿里云免费证书 |
| nginx 起不来，日志 `cannot load certificate` | 证书还没签（第 5 节的顺序是先签后起），或证书目录名与 `-d` 第一个域名不一致：看 `/etc/letsencrypt/live/` 下的实际目录名并对齐 edge.conf |
| 页面能打开，图表一直转圈、所有数据为空 | 前端产物里的 API 地址不对。确认构建时 `VITE_API_BASE=/api/v1`（镜像内置默认值），且 edge.conf 里 `/api/` 反代存在；`curl -I https://caopan.me/api/v1/symbols/markets` 应返回 JSON 而不是 `index.html` |
| 长任务（选股扫描、回测）报「服务暂时不可用」 | 反代超时被截断。`api-proxy.conf` 已设 240s（前端客户端超时 180s），若你把默认值改回去了会重现 |
| 登录后立刻被踢回登录页 | Token 密钥在重建容器时变了（`SIGNAL_TOKEN_SECRET` 被改/丢失）→ 重新登录即可；务必固定它 |
| 用户管理里刚注册的账号登不上 | 设计如此：注册后 `status=pending`，需在「系统 → 用户管理」审核通过 |
| `docker compose up` 报 `缺少 MYSQL_ROOT_PASSWORD` | `.env` 没写或 `--env-file` 路径不对；所有命令都要带 `--env-file deploy/ecs/.env` |
| 后端启动即退出，日志 `生产环境必须配置 SIGNAL_TOKEN_SECRET` | 正是保护生效：`.env` 里的 `SIGNAL_TOKEN_SECRET` 还是默认值 |
| 内存被打满 / 容器被杀 | akshare+pandas 峰值内存不低，升级到 4G 或给 backend 加 `deploy.resources.limits` |
| 后端日志 `cryptography is required for sha256_password or caching_sha2_password` | MySQL 8 的默认认证插件需要它（镜像里已显式安装，见 Dockerfile.backend 注释）；若自行改过镜像，`pip install cryptography` |
| 后端日志 `Access denied for user 'signal'@...` | `.env` 里 `SIGNAL_MYSQL_USER/PASSWORD` 与 mysql 容器首次初始化时创建的账号不一致。账号只在**空数据卷**上创建：改完 `.env` 要 `docker compose ... down -v` 重新初始化（会清空数据库），或进 mysql 手动 `CREATE USER`/`ALTER USER` |

---

## 10. 安全清单（上线前逐条确认）

- [ ] `SIGNAL_DEBUG=false`，且 `SIGNAL_TOKEN_SECRET` 是随机串（不是默认值）
- [ ] 管理员密码已改（首登后进「系统」改密；`SIGNAL_BOOTSTRAP_ADMIN_PASSWORD` 只影响首次创建）
- [ ] MySQL / Redis / 后端端口都没有发布到公网（`$C ps` 里只看得到 80/443，和 127.0.0.1:8000）
- [ ] ECS 安全组 22 端口只对你自己的 IP 开放
- [ ] `/docs` 不对外（本文档的 nginx 配置没有反代它；需要时走 SSH 隧道）
- [ ] 两个域名都能正常访问后再打开 edge.conf 里被注释掉的 HSTS
- [ ] 备份已挂 crontab，并同步到了 OSS 或另一台机器
- [ ] 公开站的 `/api/` 限流（`limit_req`）保留了 —— 公开站是匿名可用的

---

## 11. 本文档的验证状态

写这份文档的机器上**没有 Docker**，所以「构建镜像 / compose 启动 / 证书签发」这三件事
我没有实测，需要你在 ECS 上首次执行时观察。已经在本机核对过的部分：

- `deploy/ecs/.env.example` 的每个 `SIGNAL_*` 键都与 `signal-layer-server/app/config.py`
  的 `Settings` 字段一一对应（没有拼错的键）；用它跑通配置解析：
  `SIGNAL_MYSQL_HOST=mysql`、`SIGNAL_REDIS_HOST=redis`、`debug=False`、
  带 `+/=` 的密码会被正确 URL 编码；默认密钥 + `debug=False` 确实触发启动守卫。
- compose 里 `${...}` 引用的 4 个变量都在 `.env.example` 中定义；挂载的 3 个 SQL
  文件（含 dev compose 漏掉的 `002_market_reference_schema.sql`）路径都存在。
- 前端以 `VITE_API_BASE=/api/v1` 构建通过，产物里**没有** `localhost:8000`。
- nginx 配置的语法我无法在本机 `nginx -t`（同样没有 nginx 二进制），
  请在建完镜像后用 `docker compose exec nginx nginx -t` 先验证一次再重启。

更省事的上线顺序建议：第 4 节写完 `.env` 后，先只 `up -d mysql redis backend`，
用第 6 节的 MySQL 交叉检查确认后端在正确的库上，再去折腾证书与 nginx。
