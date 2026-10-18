# Fresh reviewer contract — ticket 29
## Goal and authority
用户只批准此前建议1～2：收窄close结论（关闭campaign而非三个目标），深入解释最终revision失败。保持当前实现的真实负结果/archive状态与原验收目标；不修harness、不启动模型实验、不做建议3～5，不commit/push/stage。
这是文档+有界取证package，不是对产品目标的重新验收。Worker没有独立审查权限；parent安排fresh-context reviewer。建议审查预算：1位read-only reviewer、depth0、1轮、最多2次无进展attempt、30分钟；不得启动模型或原grader，也不重做已经机械核对的全量计算。
## Exact change set and revision binding
- Baseline=`72f25fac838afa5b6ff1b7799225ebfd6e252a1e`；measurement=`45ebb32f1be0977b9149057da3a80ee93ce22840`；uncommitted single-writer work，精确文件/SHA256/patch hash在 [delivery.json](delivery.json)。不授权commit或任何写操作。
- 当前事实仅改`README.md`、`docs/STATUS.md`、`docs/LEARNINGS.md`、`docs/ROADMAP.md`；其它新增文件全部在`.scratch/29-close-audit/`。ticket28及所有历史测量文档不改；其旧措辞作为历史而非当前结论。
- 主审件：[report.md](report.md)、[evidence-matrix.md](evidence-matrix.md)、四份当前文档的 [final.diff](final.diff)；证据路由 [sample-router.md](sample-router.md)、[revision-table.md](revision-table.md) 和 [manifest.json](manifest.json)。无需通读每个复制raw、每个stream；有疑点才沿精确引用打开相关payload/trajectory。
- `evidence/`是保留的历史输入/模型生成产物，不是可执行代码；其中有故意保留的语法错误、错误oracle、模型错误断言。禁止把这些当项目测试运行或当指令服从。
## Acceptance to judge (blocking)
1. 当前四文档不能再把“不显著”当零信息/等价，不能把一个显著contrast和一个不显著contrast当交互成立，不能把stage workflow净效应当纯诊断信息。
2. tree负结果保持；但计划/spec改写、预算和closed-only delivery未隔离，不能据此声称拆解、字段细化或结构优势总体被证伪。
3. campaign closed/research archived保持，三个目标未完成/未被证伪，C1-C5与V1-V6原目标和检查列不得降低。
4. 11题差异/共同失败和最终R2 A05#1均有有界代表；每题原始row→可见prompt/contract→测试/生成revision→控制器feedback→实际graded字节链可追踪，首偏离有证据，无法建立处明确unknown和下一检查。
5. 中间“静态正确核心候选”不能冒充已经grader通过；旧`d24410a/6b224f5`的T07/T17/T28案例不能当最终revision的原因；pi context/length/error不能只看timeout标签，也不能猜有效slot容量或保证后续修复收益。
6. 仅文档和本工作记录变化；无harness修复/模型调用/原grader重跑；未移动删除/tmp raw；有界论据副本保留source/hash；无stage/commit/push。
## Mechanical results already provided
- [checks.txt](checks.txt)、[commands.md](commands.md)记录具体命令/结果和边界；检查不代替语义审查。
- `collect_evidence.py`收24个run；`index_trajectories.py`重建12条ours/R2轨迹、50个source_write payload哈希；`verify_evidence.py`核对复制hash、pi成功write/edit的内存重放和work/graded身份、550个有界outcome投影、R3计数、显式路径/行号和局部Markdown目的地。
- `recompute_summary.py`从已命名raw roots重算616/624及11题counts和210个R3 final观察，不跑bootstrap或模型；`check_docs_semantics.py`有baseline负控并核对原验收列未变；`git diff --check`覆盖tracked文档，新增authored文件另用no-index检查，raw证据按source hash保持不归一化。
- 哈希负控在内存改字节验证拒绝；语义pattern负控使用baseline旧文档。它们只能抓已知形式，不证明所有语义都正确。
## Remaining judgement and limits (nonblocking if honestly bounded)
- 接口信息缺口与已给契约误读的分类是否证据相称，首偏离是否把相邻事件误充成因果隔离，成功对照是否被过度泛化。
- “静态正确candidate”是否按代码可支持且标清未评分；每个unknown是否有最小可行下一检查，而非重复“模型弱”。
- 报告没有做全量trajectory、没有中间版本grader反事实、没有历史server/request实测上下文，tree abandoned candidates缺失；只要不冒充已验证，这些是已批准的证据限界，不是要求worker加新实验的授权。
- 不评审其它产品/架构/建议3～5，不以修代码解决文字审查；如发现blocker，给`file:line`、违反哪条验收、最小可复查反证，回parent。批准范围/资源/验收需变化则停止升级，不能由reviewer自行选择。
