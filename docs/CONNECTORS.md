# 其他 App 的一句话接入

首次设置：告诉助手你的私有仓库 `OWNER/PRIVATE_MEMORY_REPO`，通过 App 的 GitHub 连接授权这个仓库。不要把 token 粘贴到对话或记忆文件。

复制 [入口模板](AI_MEMORY.template.md) 到私有库根目录 `AI_MEMORY.md`，根据实际目录修改链接。根目录入口只需设置一次；后续每次一句话指定任务。

## 读取提示词

> 使用我的私有 GitHub 记忆库 OWNER/PRIVATE_MEMORY_REPO。先读 AI_MEMORY.md，只读取本轮项目相关的记忆，必要时查原文。区分事实和历史，告诉我用了哪些来源。

## 写入提示词

> 把这次确定的信息写入 OWNER/PRIVATE_MEMORY_REPO 的记忆。按 AI_MEMORY.md 创建独立事件，保留来源、范围和时间；如更正旧记忆，用 supersedes 关联。提交成功后给我提交链接。

读写都可以用普通自然语言，不需要每次输入完整提示词；前提是该 App 的当前上下文或设置已知道仓库名和协议。

## 能力核对

| 连接器能力 | 可执行的动作 |
| --- | --- |
| 仅搜索或读取 | 读取摘要、检索原文；生成待写入补充文件 |
| 可创建、更新仓库文件 | 创建新事件，读回核对结果 |
| 可本地克隆、提交、推送 | 使用 Python 工具并提交 Git |

GitHub Contents API：读取文件使用 GET；创建/更新文件使用 PUT 和 Base64 内容。更新已有文件需要当前 blob SHA。fine-grained 权限通常读取需要 Contents: read，写入需要 Contents: write。实际 GitHub App/OAuth 授权方式以连接器为准。

每次写入优先创建新事件文件，减少多个助手争用同一个摘要。GitHub 内容创建、更新或删除操作的并发可能冲突；失败时按协议核对并重试。项目本身不运行远端同步服务。

官方参考：[GitHub 文件 API](https://docs.github.com/en/rest/repos/contents)。
