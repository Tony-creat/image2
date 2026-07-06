# 使用手册

## 运行方式

### 方式一：直接运行 EXE

```text
dist\Image2Tool.exe
```

### 方式二：从源码运行

```bat
python -m pip install -r requirements.txt
python image2_tool.py
```

## API Key

工具支持两种方式读取 Key：

1. 在界面里手动填写。
2. 在 Windows 用户环境变量中设置 `CHUNXUE_API_KEY`。

点击界面里的保存按钮时，工具会把 Key 写入当前 Windows 用户环境变量。请不要把 Key 写入源码、README、截图或公开 issue。

## 文生图

1. 模式选择 `文生图`。
2. 输入提示词。
3. 选择尺寸和输出目录。
4. 填写文件名。
5. 点击 `开始生成`。

## 改图

1. 模式选择 `改图`。
2. 选择原图。
3. 可选上传 mask。
4. 输入提示词。
5. 尺寸建议保持 `auto`。
6. 点击 `开始生成`。

## 输出文件

用户选择的输出目录只保存最终 PNG。接口响应 JSON 不会保存到用户输出目录。

程序目录下可能产生本地日志：

- `image2_generation_log.jsonl`
- `image2_diagnostic_log.jsonl`

这些文件用于排错，默认不应提交到 GitHub。
