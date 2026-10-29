## 变更内容

<!-- 做了什么、为什么这么做 -->

## 关联 Issue

<!-- 用 GitHub 关键字自动关闭，例如：Closes #12 -->

## 自检清单

- [ ] `ruff check .` 通过
- [ ] `python -m pytest` 通过
- [ ] 涉及数据模型时已附带 Alembic 迁移，并在空库上 `alembic upgrade head` 验证
- [ ] 涉及对外接口时已更新 README 的调用示例（`README.md` 与 `README.zh.md` 都要改）
- [ ] 未提交 `.env`、真实密钥、内网地址或员工账号
- [ ] 新增配置项已同步 `.env.example`

<!-- 三个 CI job（lint / unit-tests / migration-drift）会在 PR 上自动运行，请确认全绿 -->
<!-- 需要打标签请在右侧手动选择，或在本 PR 的评论里用 /label "needs-review" -->
