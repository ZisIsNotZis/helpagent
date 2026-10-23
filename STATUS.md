# STATUS

路由文件：只记录"它是什么、现在什么状态、进展落在哪、下一步"，数字与结论一律指向已有的权威文件，不在本文件复制。

## 它是什么

一个把小型本地模型（Spark-X2.5-4B Q4_K_M，llama.cpp）包进常规软件工程流程、并用盲评外部评分器诚实测量的研究 harness；没有产品 CLI。（`README.md:3-15`；`docs/STATUS.md:4`）

## 当前状态

**归档（研究了结）+ 恢复工作阻塞**。

- 研究战役已跑到预注册终点并给出判定，目标"未达成或未判定"，不是被证伪；产品 CLI 不存在。（`docs/STATUS.md:4`）
- 后续的 M1「harness 与测试流程恢复」里程碑只做到 P1a，状态为 **BLOCKED / INCOMPLETE**（两次独立审查额度已用尽），P1b 与 P2–P5 未开始，M1 未通过；M2 未获授权。（`docs/ROADMAP.md:32`）
- 该状态的原始落盘时间：commit `999ea9a`，2026-10-19；此后 `73cc4d9` 以 `docs/paper-plan.md` 把本仓交给接手的 agent，"写论文"成为最新意图。**次序已定**：2026-10-23 人用一条规则回答（论文要用的工具坏了才先修，否则先写论文），本节点据此判定 preprint 不依赖 P1a，走论文路径；逐文件证据在 `AGENTS.md`（Current facts），决定记录在 `mail/2026-10-23-helpagent-paper-first.md`。
- **当前状态以 `AGENTS.md` 为准**（接手的节点文档：roadmap、已决事实、未决问题、证据指针）。战役字节原先只存在于 `/tmp/wave1`，现已复制到仓内声明位置 `bench/runs/wave1/`，由 `bench/manifests/wave1.sha256` 校验；`git` 装不下 2.0 GB，所以那里的东西不被跟踪、只被哈希。
- **接手后的进展**：preprint 写在 `docs/paper/`（八节 + 数字表，`preprint.md` 是渲染件）；`python3 reproduce.py` 用仓内 0.5 MB 投影复算全部决定性数字（无网络、无模型、不需要 2 GB home，key 数由命令自己打印，不在本文件存数）；`python3 bench/checks/m1_acceptance.py` 在 tag `preprint-v1` 上验证“干净克隆 + 一条命令”这一判定。里程碑 M1 达成；**push 已由上层于 2026-10-23 完成、仓库已公开，DOI 与 arXiv 投稿仍待授权**（`AGENTS.md` Current facts）。

## 最新进展落在哪个文件

- 现场状态、roadmap、未决问题：`AGENTS.md`（接手节点的文档，从这里开始）。
- preprint 草稿与它的数字表：`docs/paper/README.md`（索引）、`docs/paper/numbers.md`（每个数字的出处与命令）。
- 测得的最终位置与全部数字：`docs/STATUS.md`（每条结论的原始出处见 `FINDINGS.md`）。
- 可复用/不可复用的提炼与负结果表：`docs/LEARNINGS.md`。
- 切片与验收判定的最终结论、M1 阻塞状态：`docs/ROADMAP.md`。
- 工作记录：`.scratch/28-three-requirements/issues/`（战役）、`.scratch/29-close-audit/report.md`（收尾审计）、`.scratch/30-harness-recovery/blocked-checkpoint.md`（阻塞检查点）。

## 下一步

次序已由 2026-10-23 人的规则定下（论文路径），下一步只剩三件，越界的一件在人手里：

1. 发布这一步：push 已由上层完成（仓库公开，`origin/master` 即当前 revision），preprint 在仓内当前 revision 可读；DOI 与 arXiv 投稿仍待人，本节点不取。tag `preprint-v1` 只是 `m1_acceptance.py` 的验收 revision，早于当前论文，不可当作论文本身。（`mail/2026-10-23-helpagent-paper-first.md`）
2. P1a 未被本次判定动用：人给的那一轮修复授权仍未花，P1a 维持 BLOCKED（两次审查额度已用尽）；它若再启动，需要的是新假设，不是改名。（`docs/ROADMAP.md:32`、`.scratch/30-harness-recovery/blocked-checkpoint.md`）
3. 研究侧仍未做：更有统计功效的语料、产品 CLI（V6）、改进 prompt 的基线臂、干净单通道 wall-clock 对比、forced-leaf 阈值扫描。（`docs/ROADMAP.md:81-90`）
