# 技能库

这个仓库存放可复用的 Codex Agent 技能。

## 目录结构

- `.agents/skills/`：本地技能定义目录
- `SKILL.md`：每个技能的主说明文件
- `scripts/`：技能使用的辅助脚本
- `assets/` 或 `references/`：可选的支持文件

## 已包含的技能

- `save-usehook-markdown`：抓取 `aicompanion.usehook.cn` 的文章页面并保存为 Markdown 文件
- `git-commit-message`：根据当前 Git 工作区变更生成 git-cz 兼容的提交信息

## 说明

- 不要将密钥或其他敏感信息提交到这个仓库中。
- 尽量保持技能小而独立，说明清晰，并减少不必要的依赖。
