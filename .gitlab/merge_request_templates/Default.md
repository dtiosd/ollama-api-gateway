## 变更内容

## 关联 Issue

## 自检清单

- [ ] `ruff check .` 通过
- [ ] `python -m pytest` 通过
- [ ] 涉及数据模型时已附带 Alembic 迁移，并在空库上 `alembic upgrade head` 验证
- [ ] 涉及对外接口时已更新 README 的调用示例
- [ ] 未提交 `.env`、真实密钥、内网地址或员工账号
- [ ] 新增配置项已同步 `.env.example`

/label ~"needs-review"
