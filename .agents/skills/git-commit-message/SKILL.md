---
name: git-commit-message
description: Generate concise git commit message text from the current repository changes. Use when the user asks for a git commit message, git-cz or Conventional Commit format, VSCode git-commit-plugin style messages, or wants a commit message based on the current diff/staged/unstaged code changes. Supports repo types such as feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert, and init.
---

# Git Commit Message

## Workflow

1. Inspect only the current working tree diff before writing the message:
   - Use `git diff` as the source of truth.
   - Do not use staged/cached diff commands such as `git diff --staged` or `git diff --cached` unless the user explicitly asks for staged changes.
   - Use `git status --short` only to understand which files changed when `git diff` needs path context.
2. Identify the primary intent of the change, not every touched detail.
3. Choose a git-cz compatible type:
   - `🎉 init`: 项目初始化.
   - `✨ feat`: 添加新特性.
   - `🐛 fix`: 修复 bug.
   - `📝 docs`: 仅仅修改文档.
   - `🌈 style`: 仅仅修改空格、格式缩进、逗号等，不改变代码逻辑.
   - `🦄 refactor`: 代码重构，没有加新功能或者修复 bug.
   - `⚡️ perf`: 优化相关，比如提升性能、体验.
   - `✅ test`: 增加测试用例.
   - `🔨 build`: 依赖相关的内容.
   - `👷 ci`: CI 配置相关，例如 k8s、docker 的配置文件修改.
   - `🐳 chore`: 改变构建流程，或者增加依赖库、工具等.
   - `⏪ revert`: 回滚到上一个版本.
4. Pick a concise scope from the package/app/module when obvious, such as `render`, `xiaodouya`, `e2e`, or a feature folder.
5. Write the subject in Chinese when the user communicates in Chinese, otherwise match the user's language.

## Output Rules

- If the user asks for “只需要这条” or similar, output exactly one commit subject line and nothing else.
- Default format: `<icon> <type>(<scope>): <subject>`.
- Include the icon that corresponds to the selected type by default, following the git-commit-plugin style.
- Omit the icon only when the user explicitly asks for no emoji/icon output.
- Omit the scope only when no meaningful scope is visible.
- Keep the subject short, imperative/summary style, and under about 50 Chinese characters or 72 English characters when possible.
- Do not include markdown fences unless the user asks for a block.
- Do not run `git commit` unless explicitly requested.

## Examples

- Current diff fixes route/tab sync in `packages/render`: `🐛 fix(render): 修复跳转消息通知时页面反复切换`
- Current diff adds a renderer feature: `✨ feat(render): 支持批量导入素材任务`
- Current diff only updates docs: `📝 docs: 更新本地开发说明`
