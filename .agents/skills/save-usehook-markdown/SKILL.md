---
name: save-usehook-markdown
description: Fetches article pages from aicompanion.usehook.cn or similar usehook-style Next.js pages, extracts the main article body from the page payload, and saves it as a Markdown file in the current working directory. Use this when the user gives a usehook article URL or path and wants the content stored locally as a .md file.
---

# Save Usehook Markdown

Use this skill when the user wants a page from `aicompanion.usehook.cn` saved into the current directory as Markdown.

Prefer the project-local copy of this skill when it exists under `.agents/skills/save-usehook-markdown`.

Typical requests:

- "把这个网页存成 md"
- "获取这个 usehook 页面内容到当前目录"
- "把 `https://aicompanion.usehook.cn/...` 落成 markdown"

## Workflow

1. Treat the user's current workspace as the output directory unless they ask for another path.
2. Run the bundled extractor from that target directory:

```powershell
node C:\Users\tao\Desktop\AI 电子伴侣企业级项目实战\.agents\skills\save-usehook-markdown\scripts\extract_usehook_page.js <url-or-path>
```

3. The script writes `<slug>.md` in the working directory and may also create a temporary `<slug>.html`.
4. Verify the Markdown is not truncated:
- Check file size or line count.
- Preview the first 40-60 lines.
- If the file only contains the title/source header, the site structure likely changed and the extractor needs inspection.
5. Delete the temporary `.html` file after validation unless the user wants it kept.
6. Report the generated Markdown path back to the user.

## Notes

- The script accepts either a full URL or a path like `/3-setup-first-call/`.
- For path input, it defaults to `https://aicompanion.usehook.cn`.
- The extractor is built for usehook-style Next.js pages that embed article content in `self.__next_f.push(...)` flight payloads.
- If the user asks for multiple pages, run the script once per URL and clean up each temporary `.html`.

## Validation

Prefer this quick check sequence after generation:

```powershell
Get-Item '<slug>.md' | Select-Object Name,Length,LastWriteTime
Get-Content -Path '<slug>.md' -TotalCount 40
(Get-Content -Path '<slug>.md' | Measure-Object -Line).Lines
```

If the content looks incomplete, inspect the generated `.html` and the extractor logic before telling the user the job is done.
