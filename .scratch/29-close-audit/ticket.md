# 29 — close 结论收窄与最终 revision 有界因果取证
## 执行契约
- 2026-10-15T12:30:50+08:00，actor=worker；用户批准建议1～2：结束的是 campaign，不是三个目标；修正文档 zero-information、拆解因果和 close 越界；以最终 revision 的有界样本深入解释失败。
- baseline=`72f25fac838afa5b6ff1b7799225ebfd6e252a1e`；`git status --short` 为空；测量 revision=`45ebb32f1be0977b9149057da3a80ee93ce22840`；已有工作全部保留，不 commit、不 push、不 stage。
- owner=单 writer 当前 working tree；budget=1 worker、禁止子委派、depth=0、最多2次无进展 attempt、90分钟，截止2026-10-15T14:00:50+08:00；只轻量读取/Python统计，无模型、无重型测试；默认不重跑原 grader，需要时先记录必要性和资源并升级。
- 输入：外部审计 investigation.md；README.md、docs/STATUS.md、docs/LEARNINGS.md、docs/ROADMAP.md、ticket28 及其明确链接；只沿布局/链接定位最终 raw，不全库扫描。
- 解释：当前实现的负结果和 archive 状态保持，三个目标未完成且未被证伪；不显著不是零信息，tree bundle 不是纯拆解处理，旧 revision 案例不能冒充最终 revision 原因；数字仅在可证明错误时改。
- 非目标：不实施 harness 修复，不启动模型实验，不做建议3～5，不改验收目标，不实现作弊特化，不移动/删除 /tmp raw，不宣称全量轨迹审计。
- 范围：四份当前文档的相关语义一致性 + 本工作记录；ticket28 是历史输入，不改其历史记录；所有最终改动限文档和 .scratch/29-close-audit/。
## 验收与证明
- 文档不再把不显著称零信息，不把 tree bundle 归因为纯拆解，不把 campaign close 称不可能性；保留真实负结果、archive 和未完成目标。
- 有界样本至少覆盖 T33/T12/T35/T30/T16/T26、共同全败 A02/A03/A04/T27/T34、最终 R2 A05#1；每题一个可追踪失败及必要成功对照。
- 从 raw row 到中间 revision、prompt、test/review、控制器反馈、最终字节：给出首偏离证据，或明确无法建立及下一检查；区分症状、当前直接证据、历史 grader 证据、推断、unknown；正确 candidate 的存在不能由模型自述证明。
- 输出详尽 report、简洁逐题矩阵、复算脚本/commands、路径/行号/revision；用于论据的有界非敏感 raw 复制到本记录并记 source/hash；不海量复制。
- scoped git diff --check、引用/哈希机械核对、最终 diff 与 status；提供精确 change set/hash 和 fresh-review contract；独立审查由 parent 安排，worker 不自称完成独立验收。
## 初始观察与计划
- 2026-10-15T12:31:23+08:00，actor=worker；已读指定入口。审计指出 R3 closed-only delivery 混杂；R2 A05 错误 oracle；最终 N25 逐题互补；四份文档有 zero-information、only when backstopped、structural superiority refuted、more seeds cannot resolve 等过强语义。
- 顺序：先就地修四份文档；再从 N25 analyzer 与 measurement records 定位指定样本，保留有界 evidence 并重建可见轨迹；最后统一报告、机械检查和 reviewer contract。
- 失败路线：缺轨迹不阻塞其他题，记录 missing 和最小下一检查；若需模型/重跑/权限或范围变化，停止该动作并上报；连续2次无进展则保存限制并换证据问题，不无限搜索。
## 执行记录（append-only）
- 2026-10-15T12:48:28+08:00，actor=worker；完成四份当前文档的语义收窄，原数值表/原C1-C5和V1-V6目标不变；更正statistically indistinguishable和阶段角色表的同类越界；不修改ticket28历史。narrow_docs.py记录首轮替换，后续聚焦更正见final.diff。
- 2026-10-15T12:48:28+08:00，actor=worker；根据明确N25 roots保留24run（11题两臂代表、T26成功对照、R2 A05#1），扩到实际grade-repo字节以免将work误当grader消费字节。source_write全50笔与模型payload SHA256相符；pi成功write/edit在内存重放，12run最终work字节一致；不执行候选。
- 2026-10-15T12:48:28+08:00，actor=worker；发现PT33#1 length/output8192；PT12#1/PA02#1/PA04#1/PT27#1 context-size error而driver timed_out=false；已向parent发一次实质发现更新。解释限于日志直接事实，不猜实际slot容量、不改公平性/验收目标、不启动新实验。
- 2026-10-15T12:48:28+08:00，actor=worker；OT16#2 instance-list中间候选和OT30#2 UTC+import中间候选均保留，但没有该中间版本grader verdict，报告明确静态推断/unknown；OT26#1真实IV反证后仅stop，OA02/OA03/OA04/OT27/OT34/R2A05逐版本与首偏离见report和矩阵。旧revision案例不冒充当前原因。
- 2026-10-15T12:48:28+08:00，actor=worker；轻量复算N25总数616/624，11题550个outcome投影；R3读210run+finalsource，复现每tree arm52个未claim且pristine交付，leaf39unclaimedpasses；三份T02 raw/source作有界例子。原/tmp证据无改写移动删除。
- 2026-10-15T12:48:28+08:00，actor=worker；必要源码扩展严格沿审计引用，核实IV-stop/whole-test删除/M1擦除/closed-only merge、plan/spec输入/输出以及pi context/output声明和driver timeout含义；与measurement revision的相关code+corpus diff为空，未编辑代码。
- 2026-10-15T12:46:46+08:00，actor=worker；verify_evidence preliminary发现报告PT12 gate.py行21越界（实际20行）；修正引用后2026-10-15T12:47:04+08:00机械gate通过。不是无进展attempt，负例确实暴露一个缺陷。保留failed输出，未将它写成pass。
- 2026-10-15T12:48:28+08:00，actor=worker；report.md、evidence-matrix.md、sample-router.md、revision-table.md、commands.md和fresh-review contract已落盘。模型/原grader/pytest/CI未运行；无子委派，无scope/authority变化；独立review仍由parent安排，不自我验收。
- 2026-10-15T12:50:21+08:00，actor=worker；最终文字自查补正LEARNINGS表格：own-test不直接携claim不等于无影响，IV减少false-claim的contrast限review在场；同步报告的artifact别名、T26类型过约束措辞、A03单位来源和tree静态核实。追加轻量检查会将新报告/矩阵数字直接对550条投影核对；不扩大实验范围。
- 2026-10-15T12:50:21+08:00，actor=worker；本package实现/取证输出ready-for-fresh-review，未执行独立验收。最终机械证据在checks.txt，baseline-to-worktree文档patch在final.diff；全部新增文件与4个修改文件的SHA256在delivery.json（自文件排除），最后状态在status.txt。剩余风险：有界非全量、无中间grader反事实、server/request底层context原因未知、tree已删candidate不可恢复；下一步仅fresh reviewer按review-contract.md审查，不授权建议3～5。
- 2026-10-15T12:50:21+08:00，actor=worker；扩展no-index whitespace wrapper错误地要求exit0，遇到干净但有新增diff的ticket.md返回1、无diagnostic而停止；不是文档whitespace缺陷。2026-10-15T12:50:45+08:00用stdin安全负控实测clean返回1、trailing-space返回3带diagnostic；修wrapper只接受0/1且无diagnostic，失败日志保留checks-noindex-preliminary.txt。run_checks.sh固定最终完整复算入口。
- 2026-10-15T12:56:28+08:00，actor=worker；fresh review verdict由本次dispatch提供：PASS，nonblocking P2=`report.md:54`把T35全部八版外部结果写为unknown，但`revision-table.md:18`第八版等于graded final，保留row记载actual=false、3 failed/3 passed。仅修此句为前七版unknown、第八版历史失败，明确不重跑；预算1worker/depth0、10分钟、最多1次无进展，截止2026-10-15T13:06:28+08:00；无委派、模型、grader、测试、stage/commit/push。验收：单句精确delta、保留source/manifest字节、既有轻量脚本gate及delivery哈希更新；不重新分析其它结论。
- 2026-10-15T12:57:19+08:00，actor=worker；P2已按dispatch修正，仅report.md:54这一行改变；精确before/after在review-fix.diff，before SHA256与修前delivery.json一致。第八版payload与graded final SHA256=`399e8d6a0256c4ba26855da19414072f0e0c39fd5b8444bad4dd677bbe443168`，保留row的actual=false及3 failed/3 passed仅历史证据，前七版仍unknown。run_checks.sh全部轻量gate通过，另核八版table/row/字节身份；两份manifest哈希、原final.diff、四份当前文档与其它源证据保持不变。更新commands/checks/status/delivery绑定，独立review PASS+nonblocking P2来自dispatch而非worker自审；无新实验/测试/模型/grader/commit/stage/push，原证据限界不变。
