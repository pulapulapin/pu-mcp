---
name: setup
description: Bind the PuKnowledge local plugin to an installed Python environment and an explicit workspace configuration.
---

Use local execution. This plugin starts stdio directly; no cloud App ID or Tunnel is required. Web/mobile execution is not supported by this package.

1. Find the user's downloaded PuKnowledge repository and Python 3.11+ environment. Read its pyproject.toml and installation documentation. Never infer a project or use an author's personal paths.
2. Prefer an existing environment with this package installed. If installation is needed, create a virtualenv and install that trusted checkout. Check proxy/download size before network operations; never auto-download an unknown or large payload. Do not install dependencies during MCP startup.
3. For an existing user, locate their explicit config and data_dir, and reuse them. Do not create a second database or migrate records just to install the plugin. For a new user, show a neutral sample workspace config and obtain the project location before saving it.
4. Run this plugin's launch.py with --configure --python ABSOLUTE_VENV_PYTHON --config ABSOLUTE_CONFIG. Add --modules core,fs,longform only when those modules are wanted; default core. Existing binding changes require --replace. This checks configuration without opening the MCP database. Store no secrets in this plugin.
5. Have the supported local host load the plugin and start a new local chat if needed. Actually call workspace_guide, workspace_list_projects, and a chosen read-only query. Missing tools mean BLOCKED. Do not count terminal stdio tests as ChatGPT host acceptance, do not call old cloud tools as a fallback, and do not disable the old connection until the new one passes.

Runtime configuration is stored outside the plugin cache in ~/.config/puknowledge/desktop.json. Plugin updates must not move or overwrite the data directory. Report installation, stdio, and host results separately.
