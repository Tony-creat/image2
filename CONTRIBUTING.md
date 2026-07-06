# Contributing

感谢关注 Image2 生图工具。提交代码前请确认：

1. 不提交 API Key、`.env`、诊断日志、响应 JSON 或测试生成图片。
2. 修改后至少运行：

```bat
python -m py_compile image2_tool.py
python image2_tool.py --self-test
```

3. 如果修改打包逻辑，请运行：

```bat
build_exe.bat
```

4. 提交说明尽量写清楚改动目的、验证方式和影响范围。
