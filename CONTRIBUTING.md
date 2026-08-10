# 参与贡献

感谢你帮助岁实变得更稳定、可解释、易于自托管。

## 开始之前

1. 先阅读 [产品规格](./PRODUCT_SPEC.md) 和 [架构设计](./docs/ARCHITECTURE.md)。
2. 功能请求请说明它解决的具体资产管理问题，避免把项目扩展为通用低代码平台。
3. 漏洞请按 [安全政策](./SECURITY.md) 私密报告，不要提交公开 Issue。

## 本地验证

按 [开发文档](./docs/DEVELOPMENT.md) 启动项目。提交前至少运行：

```bash
npm run lint
npm test
cd backend && uv run pytest
```

修改数据库结构时，必须同时提交 Alembic 迁移、回滚逻辑与相关测试，并在本地备份数据库后进行验证。

## 数据与隐私

不要在 Issue、Pull Request、截图、测试固件或日志中提交：

- 真实资产名称、数量、估值和平台账户。
- Token、Cookie、Webhook Header、数据库凭证和备份。
- 包含个人 API 密钥的数据源脚本。

所有测试数据都应使用明显的虚构值。

## 贡献许可

提交代码即表示你有权提供该贡献，并同意其随项目按 `AGPL-3.0-only` 发布。
