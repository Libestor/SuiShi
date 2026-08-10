# 安全政策

岁实会处理高度敏感的个人资产数据，也允许在隔离 Runner 中运行用户编写的 Python 脚本。请将安全问题视为高优先级。

## 报告漏洞

请不要在公开 Issue 中披露可利用细节、真实资产数据或凭证。仓库发布后，请使用 GitHub 的 **Private vulnerability reporting** 提交：

- 受影响版本或提交。
- 必要的复现步骤与前置条件。
- 影响范围与可能的缓解方案。
- 已隐去凭证和真实资产信息的日志。

在修复发布前，请不要公开漏洞细节。

## 部署基线

- 只向外网暴露开启 HTTPS 和 Basic Auth 的 Nginx 网关。
- 不直接暴露 Backend、MySQL 或 Python Runner。
- 更换 `.env.example` 中的所有开发凭证，并使用不同的 `PLATFORM_TOKEN`、`SESSION_SECRET` 和 `RUNNER_SHARED_SECRET`。
- HTTPS 环境设置 `SESSION_COOKIE_SECURE=true`。
- 将数据库、备份、Webhook Header 和个人数据源脚本保持在 Git 之外。
- 仅运行自己编写或已审查的 Python 脚本。

## 支持范围

安全修复优先提供给最新主分支。早期 MVP 暂不承诺长期维护多个旧版本分支。
