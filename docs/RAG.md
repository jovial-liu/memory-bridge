# 检索与上下文组装

GitHub 是可追溯的记忆底座，检索索引是本地可重建的缓存。索引含私有文字，保存在仓库之外，不提交到公开库，也不作为 GitHub 上不断改写的数据库。

## 已实现

`rag.py` 使用 SQLite FTS5/BM25 排序，支持英文单词、中文单字与相邻双字组合，无模型下载、网络调用或 API 密钥。按消息边界切分长文本为 1200 字符片段，重叠 160 字符；保留源文件、消息编号、字符位置、SHA-256、角色、账号、覆盖说明及候选/确认状态。

```sh
python3 rag.py --root ../private-memory --db ../local-index.sqlite3 index
python3 rag.py --root ../private-memory --db ../local-index.sqlite3 retrieve '论文投稿' --topic research --limit 8
python3 rag.py --root ../private-memory --db ../local-index.sqlite3 context '模型训练' --topic ai-infrastructure --budget 12000
```

`retrieve` 输出带引用 ID 的 JSON；`context` 输出受字符预算约束的背景包，供调用方 AI 生成回答。工具不调用生成模型，因此是 RAG 的检索和上下文组装层。预算按字符计算，不保证等于模型 token 上限；接入具体模型后调用方需再次按 token 预算裁剪。

`--project` 严格匹配明确的项目字段，不从对话标题猜项目。旧对话没有项目标签时为 unknown，可按 `--topic`、`--platform`、`--account` 检索。主题来自已有 index.json；没有索引的库不自动推断主题。跨项目通用偏好需要明确查 global，不自动加入。

新记忆更正链在索引时排除已替代事件。原始历史对话仍是历史证据，可检索但不能当作当前事实。索引记录源目录快照；源文件增删改、主题索引变化或新增更正后，检索拒绝使用旧索引并要求重建。返回片段前再核对源文件 SHA-256。索引在临时文件中构建，完成后原子替换。

附件索引和原始图片本轮不进入文本检索；需通过原文关联查附件。截图不是原图、角色推断不是验证身份，这些限制随来源保留。

## 升级路径

当前是词法检索，不能保证同义表达的语义召回。后续可配置 embedding 模型，按 source SHA、模型 ID 和切分版本缓存向量，将向量候选与 BM25 候选合并后重排。若使用外部 embedding 服务，须明确哪些私人数据将发送；默认不发送。

语义向量、重排器、图谱检索和在线 MCP 服务尚未实现。GitHub 插件若无法运行本地工具，可沿 SUMMARY/topics/index 做文件检索，但不能假装已经运行 RAG。

评估应使用用户实际问题形成小型标注集，记录正确来源、召回率、错误跨项目引用及陈旧记忆误用。本项目目前通过结构、过滤、引用与更新失效测试，尚未声称生产检索质量已完成评估。

参考：[SQLite FTS5](https://www.sqlite.org/fts5.html)、[RAG 原论文](https://arxiv.org/abs/2005.11401)。本项目是检索增强工作流工具，不复现论文中的模型训练。
