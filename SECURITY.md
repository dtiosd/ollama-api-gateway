# 安全策略

## 已内置的访问控制

| 面 | 机制 |
| --- | --- |
| 模型调用（`/v1`、`/anthropic`） | 必须携带 `Authorization: Bearer sk-xxx` 或 `X-API-Key` / `x-api-key`；密钥不存在、被禁用返回 `401`，配额用尽返回 `402` |
| 管理接口（`/backend/api-keys`） | 必须携带请求头 `X-Admin-Token`，服务端用 `hmac.compare_digest` 比对 `.env` 中的 `ADMIN_TOKEN`；口令不匹配返回 `403` |
| 管理接口未配置口令 | `ADMIN_TOKEN` 留空时整个管理路由返回 `503`，即默认「关闭」而不是「开放」 |
| 跨域 | `CORS_ALLOW_ORIGINS` 可配置；使用通配 `*` 时自动关闭凭证携带 |
| 配额与模型绑定 | 对所有密钥一律生效：余额 ≤ 0 返回 `402`；密钥只能调用 `bound_model`。代码中**没有任何按用户名豁免的分支**（历史上存在的 `_STAFF` 硬编码名单与 `QUOTA_EXEMPT_USERS` 配置已彻底移除） |

## 部署检查清单

1. 为生产环境生成独立口令：`python -c "import secrets; print(secrets.token_urlsafe(32))"`，不要复用示例值。
2. 反向代理只把必要路径暴露到可信网络；`deploy/nginx-ollama-api.conf` 里有 `/backend/` 的限流样例。
3. 公网务必启用 TLS；API Key 与管理员令牌都以明文头传输。
4. 数据库中的 API Key 为明文存储（便于在管理页分发）。限制数据库网络可达性、加密备份，并把数据库账号权限收敛到该库。
5. 定期在管理页禁用离职/失效用户的密钥；密钥疑似泄露时立即删除并重新生成。
6. 依赖 `Ollama` 服务本身不做鉴权：不要把 `OLLAMA_BASE_URL` 指向的端口直接暴露到公网。

## 已知边界

- 管理页把 `ADMIN_TOKEN` 存在浏览器 `localStorage`，共用电脑时请注意退出；如需更强控制，可在代理层对 `/backend/` 追加内网或 SSO 校验。
- 需要「实际上用不完」的额度时，请直接把密钥的 `token_quota` 调成一个极大值（字段为 BIGINT），而不是引入特权用户名 —— 后者曾因按 `username` 匹配而存在越风险：`username` 是建密钥时自由填写的，同名新密钥就能继承豁免。该机制现已删除。
- 限流仅覆盖 Ollama 并发队列（超载返回 `429`），没有针对单密钥的请求频率限制。
- 用量记录与配额扣减在推理完成后写入，进程被强杀时当次调用可能不计费。

## 报告漏洞

请通过仓库页面上的 **Security → Report a vulnerability**（GitHub 的私密安全报告）上报，
不要在公开 Issue 或 PR 评论里贴出可复现的漏洞细节、密钥或日志。
若该入口尚未开启（需仓库管理员在 Settings → Security 里启用 Private vulnerability reporting），
请改走项目 README 中的联系渠道私下报告。

我们会在 2 周内回复并评估影响范围；确认修复后同步发布版本说明。
