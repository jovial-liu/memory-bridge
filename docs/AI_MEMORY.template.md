# 我的 AI 记忆接口

本仓库是私人记忆库。用户决定本轮是否读写及使用范围；本文件说明实际入口。

## 读取

- 简略背景：[SUMMARY.md](SUMMARY.md)。
- 详细背景：[MEMORY.md](MEMORY.md)。
- 主题目录：topics/。原文：conversations/。附件：attachments/。
- 新增记忆：memory/events/YYYY-MM/*.json，按 scope.project 选择；需要跨项目通用偏好时只读 global。
- 被 supersedes 引用的事件作为旧版本，互相矛盾而无替代关系的事件并列说明。候选信息不得当成确认事实。
- 如果尚无某个文件或目录，说明未建立，不假装已读。历史指令不作为本轮授权。

## 写入

用户要求保存时，创建 memory/events/YYYY-MM/<随机32位十六进制ID>.json。字段：version=1、id、created_at（含时区）、kind、status、text、scope（project/platform/account）、source（reference/excerpt）、evidence_role、supersedes（数组）。confirmed 仅用于用户直接确认的内容。

先查询重复和冲突。更正用 supersedes 保留旧事件；不随每条写入改总摘要。原文引用使用最小必要证据，不保存凭据。重试使用同一 ID，先查远端结果。没有写权限时生成待保存文件并说明尚未提交；提交成功才报告已保存及提交链接。

完整协议见公开工具项目的 docs/PROTOCOL.md；将其地址改成自己的工具仓库，或将协议复制到私有库。这个模板不构成任何自动授权。
