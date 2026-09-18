# 生产部署

目标：`root@36.151.147.66`，网站 `https://jinbang.matrix-net.tech`，部署目录 `/opt/jinbang`。
现有 Traefik 使用外部网络 `matrix-network`、入口 `websecure`、证书解析器 `aliyunresolver`。
生产使用独立的 `compose.prod.yml`，不与开发 Compose 叠加。只有网页容器接入共享网络，
所有服务均不绑定主机端口。生产核心服务为网页、API、worker、PostgreSQL 和 Redis；
当前附件使用共享 uploads 卷，未使用的 MinIO、PDF 转换和 LLM 网关不在本次部署中启动。

## 首次配置

1. 确保目标主机已安装 Docker Compose、Python 3、flock 和 curl，且上述 Traefik 网络与域名已配置。
   CD 会自动执行 `init-production.sh`，也可在目标主机以 root 手动执行。
   它创建 `/opt/jinbang/.env`，生成随机数据库密码、令牌密钥和管理员初始密码，权限为 600；
   已存在的文件保持不变。变量说明见 `production.env.example`。
   `JB_ADMIN_PASSWORD` 仅用于空库首次创建 admin；后续修改此变量不会重置现有账号。
2. 镜像使用阿里云容器镜像服务 ACR，默认仓库地址为 `registry.cn-hangzhou.aliyuncs.com`，
   命名空间为 `yuanyuexiang`，需创建私有仓库 `jinbang-api` 和 `jinbang-web`。
   以 ACR 控制台提供的公网登录地址为准；若与默认值不同，在 GitHub `production` 环境
   Variables 中设置 `REGISTRY`（仅主机名，不含协议），命名空间可用 `REGISTRY_NAMESPACE` 覆盖。
   新版个人实例地址通常为 `crpi-xxx.cn-<region>.personal.cr.aliyuncs.com`。
   确保 runner 和部署机能访问该仓库，部署机能拉取 `pgvector/pgvector:pg15` 和 `redis:7-alpine`。
3. 在 GitHub 仓库 Settings → Environments 创建 `production`，添加下列 Secrets：

   | Secret | 内容 |
   | --- | --- |
   | `DEPLOY_HOST` | 目标服务器 IP：`36.151.147.66` |
   | `DEPLOY_USER` | SSH 用户：`root` |
   | `DEPLOY_SSH_KEY` | 可登录目标主机 root 的完整 SSH 私钥 |
   | `REGISTRY_USERNAME` | ACR 控制台「访问凭证」中的登录用户名 |
   | `REGISTRY_PASSWORD` | ACR「访问凭证」中设置的镜像仓库登录密码 |

   镜像推送和部署拉取均使用上述 ACR 凭据。`REGISTRY_PASSWORD` 是独立设置的仓库密码，
   不是阿里云控制台账号登录密码；无需 GitHub Packages 写入权限。

   `deploy/known_hosts` 固定当前目标主机的 SSH 公钥，主机重装后需核对并更新。
   本地 `ci-cd.md` 含私钥，已加入 Git 忽略；Docker 构建上下文使用白名单，排除凭据和客户样本。
4. 将工作流及配套部署文件推送至 `main`。首次 CI 通过后自动部署；也可在 Actions → CI/CD 手动运行 main。
   其他分支和 PR 只执行检查，不部署。CI 同时校验部署脚本语法、生产 Compose 和主机公钥记录。
   缺少 Secrets 时，部署任务会明确报出对应名称；私钥需完整保留 BEGIN/END 行，且不带口令。

## 发布过程

CI 完整通过 → 在 GitHub Linux runner 构建 amd64 镜像 → 以完整提交 SHA 为标签推送阿里云 ACR →
SSH 上传本次 Compose 和镜像引用 → 拉取镜像 → 停止 API/worker → 备份数据库 → 执行 Alembic →
启动并等待容器健康 → 检查 HTTPS 首页及 `/api/health` → 更新 `current` 和 `previous` 链接。

应用发布期间会有短暂不可用。主分支发布串行执行，服务器另用 flock 防止并发部署。
worker 默认并发为 1，可通过服务器 `.env` 中的 `JB_WORKER_CONCURRENCY` 调整。
worker 探针只通过 broker 向本容器发送 Celery ping，不导入解析和数据库业务模块；
启动宽限期为 60 秒，单次探针上限 30 秒，应用启动等待上限为 360 秒。
Secrets 不写入镜像或发布文件；业务环境变量始终从目标主机 `/opt/jinbang/.env` 读取。
部署通过 SSH 标准输入传入镜像仓库密码，使用独立的临时 Docker 配置目录，
部署结束后删除；不会覆盖服务器已有 Docker 登录配置。
日后手动拉取私有镜像需另行登录 ACR，或重新运行工作流；本地已有镜像的回退不需要登录。

## 故障与恢复

- 镜像拉取失败：不停止现有应用。
- 备份或迁移失败：应用保持停止，发布返回失败；先检查迁移状态和备份，再决定恢复。
- 容器或 HTTPS 检查失败：有旧版本时自动恢复旧应用镜像，工作流仍返回失败；首次发布则停止应用。
- 失败时先输出容器状态、OOM 标志和健康检查历史，再执行恢复或停止。
  若 worker 已打印 `ready` 但探针启动超时，检查主机可用内存、CPU 和 I/O；
  共享主机资源耗尽仍可能导致发布失败，延长等待时间不能替代容量调整。
- 自动恢复**不回退数据库结构**。迁移必须保持上一版本应用兼容；破坏性迁移需要单独维护窗口。
- 数据库备份在 `/opt/jinbang/backups/<release>.dump`。备份不含 uploads 附件，附件卷应另行备份。
- 发布目录、数据库备份和旧镜像暂不自动清理，需定期按保留策略维护。

检查当前服务：

```bash
cd /opt/jinbang
docker compose --env-file .env --env-file current/release.env -f current/compose.prod.yml ps
docker compose --env-file .env --env-file current/release.env -f current/compose.prod.yml logs --tail 100
```

若新版本发布成功后需要回退，确认数据库兼容后，使用 `previous` 的 Compose 和 release.env
执行 `up -d --no-build --pull never --wait`，验证 HTTPS 后再调整 current 链接。
若发生迁移失败或备份恢复，先停 API/worker，并由维护者确认对应备份及数据损失范围；
不要直接运行 `down -v`，也不要盲目降级数据库。

配置依据：[Traefik Docker 路由](https://doc.traefik.io/traefik/reference/routing-configuration/other-providers/docker/)、
[Compose 健康等待](https://docs.docker.com/reference/cli/docker/compose/up/)。

镜像认证依据：[阿里云 ACR 访问凭证](https://www.alibabacloud.com/help/en/acr/user-guide/configure-access-credentials)。
