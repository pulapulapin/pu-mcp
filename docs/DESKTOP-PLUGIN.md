# Desktop plugin setup

仓库中的 `plugins/pu-knowledge-workbench` 是本地 stdio 插件。插件不会下载依赖、创建数据库或猜测配置。

先安装工程，再绑定解释器和配置：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python plugins/pu-knowledge-workbench/launch.py \
  --configure \
  --python /absolute/path/to/pu-mcp/.venv/bin/python \
  --config /absolute/path/to/workspace.local.json \
  --modules core,fs,longform
```

绑定保存在用户目录的 `.config/puknowledge/desktop.json`，权限设为仅当前用户可读写。更换解释器或配置时使用 `--replace` 重新绑定。

安装后在宿主中确认 `workspace_guide` 可调用，并核对其返回模块。插件出现在列表中只证明已注册，不证明宿主已成功调用服务。
