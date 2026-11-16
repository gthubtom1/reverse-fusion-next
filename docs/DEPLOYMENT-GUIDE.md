# 部署

唯一流程见[AGENT-BOOTSTRAP](AGENT-BOOTSTRAP.md)。本版Windows x64核心是Reverse＋增强REA，不走旧四组件安装链。

共享目录长期存在。用户在任意成果目录打开Codex，用白话提出任务。用户级技能/全局指引负责发现，共享目录提供方法工具，成果留在用户项目。空文件夹也能调用；移动共享目录后重新部署绝对入口。

provider路径保存在state/rea-providers.json，只含路径。更换后providers --refresh、mcp-check，并实际执行所需操作。原REA包不改，Frida绑定独立安装；增强比较回执单独标识。
