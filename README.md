# Memory Bridge

**一句话，让不同 AI 按需读写你自己的记忆。**

GitHub-backed, user-controlled memory for AI assistants. 一个公开的协议与工具项目，配合你自己的私有记忆仓库使用。

公开仓库放工具、协议和虚构示例；私有仓库放真实对话、记忆和附件。两个仓库独立，没有自动公开同步。

## 怎么用

给支持 GitHub 的助手一次性提供私有仓库名，并授权所需权限。之后可以说：

> 读取我的记忆，只恢复当前项目的背景，需要时查原文。

> 把我们刚确定的决定写入我的记忆，保留来源和时间。

> 这次不用历史记忆。

助手先读私有库根目录的 `AI_MEMORY.md`，再按项目和主题检索。写入时每条新记忆创建一个独立 JSON 文件，提交成功后返回提交链接。详见 [接入方法](docs/CONNECTORS.md) 和 [读写协议](docs/PROTOCOL.md)。

**GitHub 插件不一定支持写入。** 只有获得私有库访问权限且支持文件提交的连接器才能直接写回。仅搜索或读取的插件可以读记忆；写入时先生成补充文件，再由具备写权限的工具提交。本项目尚未逐一验证各平台插件，不提供“所有 App 已自动接入”的承诺。

## 记忆结构

```text
private-memory/
├── AI_MEMORY.md              # AI 接入入口与读写约定
├── SUMMARY.md                # 简略摘要，带来源
├── MEMORY.md                 # 较详细的背景导航
├── topics/                   # 按主题、项目查找
├── conversations/<platform>/ # 原始对话，记录账号标签
├── attachments/<platform>/   # 附件及关联索引
├── memory/events/YYYY-MM/    # 每次新增的一条记忆
└── training/                 # 未来审核后的训练数据，与记忆分开
```

已有库不用迁移整套历史：添加入口和 `memory/events/` 即可。已有的确认事实、历史卡片和对话索引继续保留。

## 本地工具

Python 3.10+，仅标准库。工具读写本地私有库，不自动上传、抓取平台或调用模型。

```sh
# 在工具项目目录运行，私有库为另一个本地目录
python3 memory_bridge.py --root ../private-memory add examples/event.json
python3 memory_bridge.py --root ../private-memory search --project demo
python3 memory_bridge.py --root ../private-memory validate
python3 -m unittest discover -s tests -v
```

示例是虚构的。`add` 自动生成 ID 和时间；直接经 GitHub 插件写文件时，助手需填全这些字段。检查后可在私有库执行 `git add memory/events`、`git commit` 和 `git push`。也可通过 GitHub 文件 API 创建单个事件。

## 为什么这样设计

- **按需加载**：先简略入口，再读取相关细节，保留项目、平台和账号范围。
- **来源可查**：每条记忆有证据、角色、日期和状态；AI 的建议与个人事实分开。
- **多助手写入**：不同文件避免共同重写一份大摘要。更正使用 `supersedes`，保留旧版本。
- **不失真**：摘要是导航，原始对话保留；冲突不靠“最后写入”自动决定。
- **为以后训练留数据**：原文、来源和审核状态保留，训练样本另行筛选。

[架构与边界](docs/DESIGN.md) · [训练数据准备](docs/TRAINING.md) · [可复制的私有库入口](docs/AI_MEMORY.template.md)

目前提供文件协议、接入说明、本地事件管理，以及 SQLite FTS5/BM25 检索和带引用的上下文组装。向量检索、自动摘要维护、账号全量导出和模型训练不在当前实现中。私有是访问控制，不是端到端加密；授权给某个 App 后，该 App 能读取你授权的内容。凭据检测只是有限的模式检查，不能保证识别所有秘密。大量视频和模型权重应另存，记忆库保留引用。

License: MIT.

## RAG 与 Agent 记忆

已经实现本地检索层：消息分块、中文/英文检索、BM25 排序、范围过滤、来源引用和上下文预算。索引放在私有库之外，原文变化后拒绝返回陈旧结果。详见 [RAG 使用说明](docs/RAG.md)。

| 记忆类型 | 当前实现 |
| --- | --- |
| 情景记忆：发生过什么 | 分平台对话及原始证据 |
| 语义记忆：明确事实和偏好 | confirmed/candidate 记忆事件与来源 |
| 程序记忆：明确的工作方式 | 用户确认的 preference/decision；工具协议作为接入规则 |
| 工作记忆：本轮需要什么 | 按范围检索的临时上下文包 |
| 项目状态和更正 | project_state/correction、时间与 supersedes |

不会自动将历史提示词升级成程序记忆，也不会把候选信息当成事实。
