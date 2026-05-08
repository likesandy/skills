---
name: wechat-article-archive
description: Archive one WeChat article URL into a portable offline folder. Use when Codex receives a mp.weixin.qq.com article address and should locate an existing local WeChat WebView page copy, extract the article body, rewrite images to local img/N.png files, and replace WeChat video placeholders with local video/N.mp4 elements.
---

# WeChat Article Archive

## Workflow

Normal input is a single article URL:

```text
https://mp.weixin.qq.com/s/<article-id>
```

Run the bundled packager from this skill directory:

```bash
python3 .agents/skills/wechat-article-archive/scripts/package_wechat_article.py \
  --url "https://mp.weixin.qq.com/s/<article-id>"
```

The script defaults to:

- WeChat WebView path: `/Applications/WeChat.app/Contents/MacOS/WeChatAppEx.app/Contents/MacOS`
- Local profile root: `~/Library/Containers/com.tencent.xinWeChat/Data/Documents/app_data/radium/web/profiles`
- Output root: `~/Desktop`

Use only local WebView page copies or user-supplied workspace files. Do not ask for title, HTML path, profile path, image list, or video list unless URL lookup fails. If lookup fails, ask the user to open the article once in WeChat and rerun the same URL-only request.

## Output

The output folder is named from the article title:

```text
~/Desktop/<article-title>/
├── index.html
├── video/
│   ├── 1.mp4
│   └── ...
├── img/
│   ├── 1.png
│   └── ...
└── 视频地址.txt
```

The generated `index.html` should contain only the article body, reference images through `./img/`, remove leftover WeChat-only markers such as `<mp-style-type>`, and replace every WeChat video placeholder, including `mp-common-videosnap` cards and `mpvideo` iframe embeds, with a labeled local video block. Each block shows `视频 N` above a `<video controls playsinline>` element whose source is `./video/N.mp4`; the visible label must match the element's `data-video-index`. If the article contains any video placeholders, create the output `video/` folder and write `视频地址.txt` with each index, expected local filename, optional `vid`, and any playable `mpvideo.qpic.cn` mp4 URL found in the local cache. Do not download videos into the folder; the user fills them in manually.

Do not generate `video-loader.js` or `视频映射.json`; if either file exists in an existing output folder, remove it. If the article has no video placeholders, do not create `video/`; if an old empty `video/` folder exists, remove it.

## Verification

After packaging, verify the archive:

```bash
find "/Users/tao/Desktop/<article-title>" -maxdepth 2 -type f
rg 'mmbiz\.qpic|findermp\.video|finder\.video|mp-common-videosnap' "/Users/tao/Desktop/<article-title>/index.html"
test ! -e "/Users/tao/Desktop/<article-title>/video-loader.js"
test ! -e "/Users/tao/Desktop/<article-title>/视频映射.json"
```

No matches from `rg` means the packaged HTML no longer depends on the original remote image or video-card references.

## Fallbacks

- `--html /path/to/article.html`: maintenance fallback only when the user explicitly supplies an HTML file.
- `--output-root` or `--output-dir`: use only when the user requests a non-default destination.
- `--include-maps`: use only when the user asks for legacy image mapping files.

## Final Response

After a successful package, respond only:

```text
已打包完成：

<output-folder-path>
```

Do not include counts or verification details unless verification fails or the user asks for them.
