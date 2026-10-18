# 协作规则

这份规则用于人和 AI 一起开发，目标是让每个人基于同一份事实工作。

## 唯一事实来源

1. 接口以 `docs/api.md` 为准，聊天里说过但没有写进文件的内容不算已确认。
2. 数据字段以 `data/*.schema.json` 为准，示例以同目录的 `*.example.json` 为准。
3. 产品决定和字段变更写进 `docs/decisions.md`，并在合并前通知 A、B、C。
4. `main` 始终保持可运行；未完成内容放在功能分支。

## 分支和提交

- A：`feature/frontend-...`
- B：`feature/backend-...`
- C：`feature/content-...`
- 一次提交只解决一个清楚的问题。
- 提交信息说明动作，例如 `Add mock recognition endpoint`。
- 不直接把未测试的代码推到 `main`。

## 合并前检查

- 代码能启动，或文档说明为什么暂时不能启动。
- 接口请求和返回仍符合 `docs/api.md`。
- JSON 能解析，字段符合 schema。
- 没有 API Key、密码、个人隐私数据或未授权素材。
- 变更影响其他成员时，在 PR 描述中写明影响的文件和需要谁确认。

## 给 AI 的固定工作提示

把下面内容放在每个 AI 任务的开头：

```text
你在红树林研学 App 仓库中工作。先阅读 README.md、CONTRIBUTING.md、docs/api.md 和相关 data schema。
不要自行改接口字段、speciesId、路由或目录结构；需要变更时先更新 docs/decisions.md，并在结果中明确说明。
只修改本任务负责的文件。完成后运行相关测试，报告修改文件、测试命令和未解决问题。
```
