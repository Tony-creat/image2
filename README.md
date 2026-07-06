# Image2 生图工具

Image2 生图工具是一个 Windows 桌面应用，用 ChunxueAPI 的 `gpt-image-2` 进行文生图和图片编辑。工具提供图形界面，支持 API Key 读取、输出目录选择、白色默认主题、友好的错误提示，以及不在用户输出目录保存接口响应 JSON。

## 功能

- 文生图：输入提示词生成 PNG 图片。
- 改图：上传参考图，按提示词生成对应图片。
- 自动读取 `CHUNXUE_API_KEY`，也可以在界面内手动填写。
- 余额不足、服务不可用、网络异常等错误会显示中文提示。
- 用户选择的输出目录只保存最终 PNG。

## 快速开始

1. 下载或构建 `dist\Image2Tool.exe`。
2. 双击运行。
3. 填写 API Key，或先在 Windows 用户环境变量中设置 `CHUNXUE_API_KEY`。
4. 选择 `文生图` 或 `改图`。
5. 填写提示词、尺寸、输出目录和文件名。
6. 点击 `开始生成`。

## 从源码运行

```bat
python -m pip install -r requirements.txt
python image2_tool.py
```

## 打包 EXE

```bat
build_exe.bat
```

打包结果：

```text
dist\Image2Tool.exe
```

## 配置说明

- `CHUNXUE_API_KEY`：ChunxueAPI 访问密钥。不要提交到 GitHub，也不要写入公开文件。
- 输出目录：只保存生成后的 PNG 图片。
- 程序目录日志：`image2_generation_log.jsonl` 和 `image2_diagnostic_log.jsonl` 仅用于本地排错，已在 `.gitignore` 中忽略。

## 文档

- [使用手册](docs/usage.md)
- [常见问题](docs/faq.md)

## 安全提醒

- 不要公开 API Key。
- 不要上传本地诊断日志、响应 JSON、测试图片或个人路径文件。
- 如果 Key 曾经暴露，建议立即到平台撤销或重置。

## License

MIT License
