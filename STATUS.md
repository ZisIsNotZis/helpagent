# STATUS

路由文件：只记录"它是什么、现在什么状态、进展落在哪、下一步"，数字与结论一律指向已有的权威文件，不在本文件复制。

## 它是什么

一个把小型本地模型（Spark-X2.5-4B Q4_K_M，llama.cpp）包进常规软件工程流程、并用盲评外部评分器诚实测量的研究 harness；没有产品 CLI。（`README.md:3-15`；`docs/STATUS.md:4`）

## 当前状态

**归档（研究了结）+ 恢复工作阻塞**。

- 研究战役已跑到预注册终点并给出判定，目标"未达成或未判定"，不是被证伪；产品 CLI 不存在。（`docs/STATUS.md:4`）
- 后续的 M1「harness 与测试流程恢复」里程碑只做到 P1a，状态为 **BLOCKED / INCOMPLETE**（两次独立审查额度已用尽），P1b 与 P2–P5 未开始，M1 未通过；M2 未获授权。（`docs/ROADMAP.md:32`）
- 该状态的最后落盘时间：commit `999ea9a`，2026-10-19（`git log`）。M1 目前无活跃工作者的记录在仓内。

## 最新进展落在哪个文件

- 测得的最终位置与全部数字：`docs/STATUS.md`（每条结论的原始出处见 `FINDINGS.md`）。
- 可复用/不可复用的提炼与负结果表：`docs/LEARNINGS.md`。
- 切片与验收判定的最终结论、M1 阻塞状态：`docs/ROADMAP.md`。
- 工作记录：`.scratch/28-three-requirements/issues/`（战役）、`.scratch/29-close-audit/report.md`（收尾审计）、`.scratch/30-harness-recovery/blocked-checkpoint.md`（阻塞检查点）。

## 下一步

按 `docs/ROADMAP.md:32` 与 `docs/LEARNINGS.md:229`（§8）已写明的次序，无人接手时不下任何新判定：

1. P1a 需要新的假设或记录为 blocker（两次无新证据的尝试后不得再修）；P1b → P2 → P3 → P4 → P5 → M1 用户闸门，之后才谈 M2。（`docs/ROADMAP.md:32`）
2. 研究侧仍未做：更有统计功效的语料、产品 CLI（V6）、改进 prompt 的基线臂、干净单通道 wall-clock 对比、forced-leaf 阈值扫描。（`docs/ROADMAP.md:81-90`）
