# 本地转换字体

只放置已获授权用于本部署环境的完整 TTF、TTC 或 OTF 字体。字体文件被 Git 忽略，不随源码分发。
不要直接把 WPS 或其他软件附带字体复制到服务器；其安装授权不一定允许服务器使用或再分发。

放入字体后执行 `docker compose up -d --build gotenberg`，再运行：

```
.venv/bin/python scripts/check_document_fonts.py 待核对文件.docx
```

该检查报告文档中的字体声明、缺失声明和字体清单指纹，包含备用样式，不能替代 WPS 视觉验收。
未提供授权字体时，转换器继续使用原有字体及替代规则，不能视为与 WPS 环境完全一致。
