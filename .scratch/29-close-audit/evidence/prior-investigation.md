# close 证据审计：可以结束这轮 campaign，不能据此结束目标
## 结论
用户的质疑有实质依据：总分掩盖了很强的逐题互补；verification 的消融测的是当前流程的净结果，不能把“不显著”叫作“zero-information”；tree 的惨败还混入一个非常重大的交付路径差异，不能归因为“拆解本身有害”。
本次最重要的新发现是：**tree 只交付拿到内部 claim 的候选，而 leaf 会交付未能 claim 的代码。两个 tree arm 各有 52 个未 claim 的失败，52/52 的交付 Python 源码仍与 pristine 相同；leaf 则有 39/70 个未 claim 却通过外部 grader 的成功。**这不是对模型能力的同一种观察方式，也不只是多几个 planning calls。
因此，可以准确说“45ebb32 的这套 tree/verification/交付实现没有收益，预注册 campaign 跑到上限”；不能说“模型已经到极限”“Test 没信息”“Review 不可能改善”“拆解/字段细化已经被有效隔离并否定”。已有 close 文档同时承认目标未达成、产品不存在、便宜缺陷未修，但若干标题和归纳比证据更强。
## 范围与证据等级
- 只读审计，无联网、模型调用、测试、grader 重跑、项目修改或 commit；只在指定的外部交付路径写本报告。
- 阅读入口：`README.md`、`docs/STATUS.md`、`docs/LEARNINGS.md`、`docs/ROADMAP.md`；沿 ticket 28 的明确引用读取 parity/verification forensics、N25、R2/R3 原始记录与分析 driver，并限界检查 `harness/leaf.py`、`harness/tree_run.py`、`harness/node.py`、`bench/v2_leaf.py`、`bench/v2_tree.py`。
- 当前 HEAD 为 `72f25fac838afa5b6ff1b7799225ebfd6e252a1e`，不是测量 revision；`git diff 45ebb32 HEAD -- harness/leaf.py harness/tree_run.py harness/node.py bench/v2_leaf.py bench/v2_tree.py` 无差异，故本报告的代码行号可用于最终测量实现。审计起点 `git status --porcelain` 为空。
- 下文“本次核实”指重读 raw rows/源码或逐字节对照；“历史记录”指此前 forensics 中记录的 grader 重跑结果，本次没有重跑其测试；“推断”不升级成测量。
## 1. R1：总分接近，逐题并不接近
### 1.1 本次从 N25 raw rows 重算
从 `/tmp/wave1/final/n25/analyze_n25.py:47-112` 声明的七组原始数据根读取；不是从 Markdown 表抄数。两臂各 1000 行、各有 1000 个唯一 `(task, seed)`，每题每臂 25 次。结果重现 ours 616、pi 624，差 8/1000；分题结果如下。
表内 O/P 为通过次数，均以 25 为分母，乘 4 即通过率百分比；“O独有/P独有”只是在同编号 repeat 上一方过、另一方不过，**不代表共享随机种子控制后的反事实**，因为这些“seed”实际上没有传给模型 RNG。
| task | O/25 | P/25 | O独有 | P独有 |
| --- | ---: | ---: | ---: | ---: |
| A-01-word-count | 1 | 4 | 1 | 4 |
| A-02-protein-translation | 0 | 0 | 0 | 0 |
| A-03-book-store | 0 | 0 | 0 | 0 |
| A-04-connect | 0 | 0 | 0 | 0 |
| A-05-zebra-puzzle | 0 | 1 | 0 | 1 |
| T-01-ttl-seconds-ms | 25 | 24 | 1 | 0 |
| T-02-off-by-one | 25 | 24 | 1 | 0 |
| T-03-wrong-comparison | 23 | 23 | 2 | 2 |
| T-04-missing-default | 25 | 25 | 0 | 0 |
| T-05-mutable-default | 10 | 17 | 4 | 11 |
| T-06-tz-naive-compare | 25 | 24 | 1 | 0 |
| T-07-f-string-sql | 23 | 25 | 0 | 2 |
| T-08-add-cache-invalidation | 20 | 22 | 3 | 5 |
| T-09-add-rate-limit-hook | 24 | 17 | 8 | 1 |
| T-10-port-dict-keys-view | 25 | 25 | 0 | 0 |
| T-11-wrong-exception-type | 25 | 25 | 0 | 0 |
| T-12-str-enum-compare | 24 | 6 | 18 | 0 |
| T-13-add-retry-backoff | 1 | 6 | 1 | 6 |
| T-14-add-export-sorting | 18 | 22 | 2 | 6 |
| T-15-stale-registry-entry | 24 | 23 | 2 | 1 |
| T-16-class-state-leak | 17 | 25 | 0 | 8 |
| T-17-log-hour-format | 22 | 20 | 4 | 2 |
| T-18-env-config-precedence | 15 | 16 | 6 | 7 |
| T-19-slug-separator | 25 | 25 | 0 | 0 |
| T-20-average-truncation | 25 | 25 | 0 | 0 |
| T-21-swallowed-corruption | 25 | 21 | 4 | 0 |
| T-22-case-sort-order | 23 | 25 | 0 | 2 |
| T-23-stack-is-empty | 25 | 25 | 0 | 0 |
| T-24-json-report-flag | 2 | 10 | 2 | 10 |
| T-25-chunked-helper | 25 | 20 | 5 | 0 |
| T-26-plan-dataclass-port | 2 | 10 | 1 | 9 |
| T-27-snakecase-ingest | 0 | 0 | 0 | 0 |
| T-28-plugin-registry-scaffold | 7 | 10 | 2 | 5 |
| T-29-prerelease-version-parsing | 19 | 12 | 10 | 3 |
| T-30-naive-datetime-compare | 15 | 25 | 0 | 10 |
| T-31-parameter-threading | 25 | 21 | 4 | 0 |
| T-32-sliding-window-limiter | 2 | 0 | 2 | 0 |
| T-33-serializer-contract | 23 | 1 | 22 | 0 |
| T-34-expression-tokenizer | 0 | 0 | 0 | 0 |
| T-35-interval-merge-invariants | 1 | 20 | 0 | 19 |
| 合计 | 616 | 624 | 106 | 114 |
- 同 repeat 两边都过 510、都失败 270、ours 独有 106、pi 独有 114。若事后让外部 grader 选任一正确答案，可达 730/1000；这只是**oracle 上界**，不是实现了一个 73% agent，也不构成端到端提升。
- 逐题期望通过率取两臂较高者之和为 27.96/40（本表可复算）；相对任一单臂约多 3 题，是互补的描述量，不是持出集验证过的路由器。
- 最强对照：T-33 ours 92% vs pi 4%；T-12 96% vs24%；反向 T-35 4% vs80%、T-30 60% vs100%、T-16 68% vs100%。不是“同一个模型在同一批题上已经做到一样的极限”。
- 两边 25 次全败的五题是 A-02、A-03、A-04、T-27、T-34；这仍只是两个配置没有找到解，不证明解不可由该模型经别的流程得到。
### 1.2 失败模式：最终 rows 提供什么，尚未提供什么
本次逐题筛最终 rows 的 `grader_notes`，可确认失败表现，而不从 `stop_reason` 猜根因：
- T-35 ours 24 次失败，seed1 外部 grader 为 `assert [[1, 6]] == [(1, 6)]`、touching/chain 类同，指出列表/元组返回契约等问题；pi 也有5次失败，但20次成功。不能说这题是模型极限，也不能把24次损失都归为同一原因。
- T-30 ours 10次失败，seed2 `NameError: name 'time...`；pi25次全过。T-16 ours8次失败，seed2 `test_carts_are_independent`，pi25次全过。
- T-26 ours23次失败，seed1 `test_old_dict_access_still_works - TypeError: 'Pl...`；这是兼容契约漏失，不能因内部 IV 红就说“验证正确地阻止了好解”或“模型写不出来”。
- T-33 pi24次失败，seed1 `test_load_refuses_foreign_bytes[PickleSerializer]`；ours2次失败中的seed7是 collection error。T-12 pi19次失败，seed1为 `test_webhook_parsed_editor_may_publish`；ours只一次失败，`no-change-delivery`。
这些是**最终交付的症状分类**，并非本次对所有失败逐 revision 的因果重建；完整最终 N25 的逐尝试失败审计并没有由本次完成，也没有在已读 close 证据中找到。
### 1.3 昨天之前到底做过 trajectory 审计吗？做过，但不是全量最终版
`parity-forensics.md:13-17` 明确方法是读取 trajectory、重建每次写入 revision、在 pristine 上跑 withheld grader；不是只看总分。其具体历史证据：
- `parity-forensics.md:68-136`：T-28 attempt4 添加 module-level API 后4/4过，交付版本4/4败；坏版本凭 review 证据排名更高。
- `parity-forensics.md:138-183`：T-17七次写入中四次过，交付却选错输入格式 fixture 所青睐的坏 revision；pi 同模型曾在 trace 中自行发现 fixture 格式错误。
- `parity-forensics.md:185-241`：T-07六次写入四次过；测试自己的 SQL 字符串不转义，报错归因未被接纳，M1反复清草稿，最后交付回退。
- `parity-forensics.md:375-401` 明确承认12个共同失败没有逐题打开；`docs/ROADMAP.md:45-49` 也承认旧 revision 的 per-task verdict 没覆盖最终 wave 改变后的失败集合。不能把“有过取证”写成“最终全部失败已解释”。
### 1.4 哪些 harness defect 没修，哪些不能重复称没修
`28-three-requirements.md:125-129`、`docs/LEARNINGS.md:270-275` 明列仍未修：拒绝后的有效 redirect；跨attempt多文件累积；按所需覆盖面而非单纯证据 tier 选择交付；plain-green 路径上的 non-discriminating claim 规则；逐attempt输出留存完整性。
必须按 revision 区分：当前 `bench/v2_leaf.py:774-777` 已给 IV 加 desired-state 规则，所以旧 forensics 说 IV 没这条提示是**历史诊断，不是当前代码事实**。`harness/leaf.py:8664` 附近已有 deterministic contract-clear capture，不能笼统说“从未修过 best evidence”。当前 `harness/leaf.py:8435-8440` 仍会 M1 erase，但有 snapshot；它是可能丢累积/排序失真的机制，不是已经证明每次 erase 都毁掉好解。
新增、以前 close 未充分凸显的问题是本报告第3节的 **tree 将 claim 当成代码晋级前提**。
## 2. R2：Test / independent Test / Review 的实际流程及证据边界
### 2.1 它们不是三个抽象标签
| 阶段 | 输入 | 输出与反馈进入哪里 | 不能由此推出 |
| --- | --- | --- | --- |
| own test | goal、AC、可见source，desired-state提示；不看隐藏grader | 模型写完整pytest；先pristine红；每次implementation后执行，失败摘录进`last_excerpts`；judge尝试归因code/test/spec；可以修test、改code或升级；无效/症状节点可改写或删除 | “红→绿”本身不证明断言的oracle对或覆盖完整 |
| independent test | fresh context；goal、编号AC、改动文件 ORIGINAL/FINAL，不看own test | 单独生成完整pytest；按original红/final绿、收集/报告、每AC节点等机械条件评估；可一次repair；红会阻claim/引导后续循环，exhaustion可能重新author | fresh context不等于独立权重，且给了FINAL会有对答案适配风险 |
| review | fresh context；一个angle、goal、AC、original/final、repo docs/coverage、review原因 | ordinal grade+具体evidence；weighted critical-angle gates；正向证据须指artifact/AC/observable；拒绝的`why`进入`last_excerpts`，下一轮implementation使用；review不是自己直接改代码 | 语句具体不代表语句正确，审核也没执行独立可信oracle |
代码坐标：`bench/v2_leaf.py:94-145,708-794`；`harness/leaf.py:8028-8088`（review何时不可进入）、`:8090-8185`（own-test partition与改写）、`:8575-8624`（执行失败/归因）、`:8640-8663`（review反馈）。这是一条“测试/审核→反馈→模型重写代码”的闭环，不是单独测一个reviewer的识错率。
### 2.2 消融证明的是当前stage bundle的净流程效果，不是信息论或诊断准确率
历史测量表位于 `requirement-2-ablation.md:24-100`：A0 raw70/120，A1 own66，A2 own+IV65，A3 own+review71，A4 full77。A0通常第一次落盘就停（`harness/leaf.py:8564-8575`），A1还增加judge、测试、repair、升级、交付选择，故 A1−A0 并不是“只增加一个测试信号而其他计算过程完全相等”。它回答启用这个**整套机制**的产品净效果，不独立回答测试本身有多少有效信息。
- own A1−A0 `−1.33 tasks [-5.67,+3.00], p=.549`：没有检测到净收益，仍容纳负效应和最高+3题正效应；不能等同“零信息”或“worthless”。测等价/接近零需要另行给等价界及证据。
- IV A2−A1 `−.33 [-3,+2.33]`；A4−A3 `+2 [-.67,+4.67]`。没检测到 correctness 效应，不是效应=0。后一对比 false claims 减少是有证据的当前流程效应。
- Review A4−A2 `+4 [1.33,7], p=.012` 是一个支持该组合的正向结果；A3−A1 `+1.67 [-1.33,5.33]` 不显著，**不证明“只有IV在场才有效”这个交互本身显著**。一个contrast显著另一个不显著，不等于两个contrast之差显著。
- A4−A0 `+2.33 [-.33,+5.33], p=.344`，全栈总体净提升仍不确定。`requirement-2-ablation.md:197-210` 诚实承认样本小、6 contrasts×3 metrics未校正、stage成本不匹配、stage join不是因果。文档正文/README删掉这些限制后叫 zero-information，超过原始证据。
- `claimed_basis`没有own-test并不证明own test不影响结果：它可能先改变code或阻断别的claim。A0/A1从来不claim，两者false=0也不是其正确性/诚实能力完美。
- `requirement-2-ablation.md:89-100` 的 full IV：110次运行、18 approve（1假）、92不approve（57实际通过）；这是审批与最终grader的关联，不是完整诊断准确率，且最终代码可能已受这些反馈影响。原文`:118`写“57 of 92 grader-passing runs”有分母措辞错：92是blocked总数，full实际过是77/120，不是92。
### 2.3 具体失效层，不是泛称“弱模型”
| 失效层 | 已有具体证据 | 修订后的正确解释 |
| --- | --- | --- |
| 测试生成/执行失效 | `verification-decomposition-forensics.md:109-119` T-21 `load(path)`未绑定、raises错误；`parity-forensics.md:349-370` T-35 own test没import merge | 测试失败不是source失败；需区分collection/runtime/setup与行为assertion |
| oracle方向错 | 同forensics`:76-108` T-06断言应抛naive/aware TypeError、T-10断言IndexError，恰是要求消除的症状 | 红绿有区分力也可能区分错方向；当前已补提示但不能声称彻底消灭此类 |
| 归因/反馈不用 | `parity-forensics.md:210-230` T-07模型曾blame=test，但deterministic filter要求命名具体断言而coerce，随后继续改正确source | 有诊断信号不等于控制器利用正确 |
| 好revision交付丢失 | T-17/T-28历史逐revision grader结果见1.3 | 失败总分包含harness损失，不等于模型从未生成正确内容 |
| 反馈未修全契约 | `parity-forensics.md:243-278` T-14自己的test要求tuple+两位小数，几次代码仍只返回sorted dicts/保留死代码 | 正确test存在仍可能没有被有效转化为完整实现 |
| 两个checker同错、覆盖是假象 | **最终R2原始行** `/tmp/wave1/final/r2/runs/c4/full/full/results.jsonl:28` A-05#1，IV+review均approve，外部grader两个函数均fail | 以下是当前revision的直接反例，不依赖旧诊断 |
A-05#1 的 IV 给21个不同AC命名的函数，却都重复同两个assert：`drinks_water() == 'water'`、`owns_zebra() == 'Japanese person'`；例如“Norwegian first house”“all attributes different”也只检查这两个错误常量。review两个angle还明确称返回这两个值“directly match required answers”。这是 **oracle错+语义覆盖不足+同模型相互确认**。不同函数名/每AC节点、pristine红final绿都没发现。该行记录 basis=`review+independent-test`, actual=false；这足以直接驳斥当前组合具有100%正确审批能力。
“review100%是否能由已有研究判断”：可以判断**当前实现不是100%**，上述反例即证；不能从这份单模型单corpus消融或无外部文献的本次审计，判断所有未来review设计必然/不可能100%。若100%指每次都跑review而不是审核正确率，full仅72/120跑，own-review64/120跑，名称不等于覆盖所有运行（`requirement-2-ablation.md:91-96`）。
### 2.4 强模型参考、通用改进试过没有
- 在本次限定的最终campaign及其引用记录里，没有强模型作reference writer/reviewer的实验；所有stage共享同一4B。不能冒充已用强模型诊断了各层上限。
- 通用harness改进并非没试：已有desired-state提示、逐criterion discrimination、归因filter、coverage/documented API、revision fingerprint、deterministic delivery anchor；历史还测过context index、knowledge pack、顺序、tournament，`docs/STATUS.md:181-195`列小样本结果。它们是各自实现与配置的实测，不构成所有可能通用改进已穷尽。
- improved-prompt pi arm明确没测（`docs/LEARNINGS.md:276-279`、ticket`:108`）；pi own-test劣化只在旧8k测过，不能外推32k；强模型“likely erase gap”（`docs/LEARNINGS.md:56-57`）是推测。
## 3. R3：tree负结果真实，但它没有隔离拆解，也没隔离字段细化
### 3.1 数字核实与最关键的交付不对称
本次重读 `/tmp/wave1/final/r3/{leaf,tree-greedy,tree-tournament}/*/run.json`，各70个：
| arm | actual且claimed | actual未claimed | false claim | 两者都否 |
| --- | ---: | ---: | ---: | ---: |
| leaf | 8 | **39** | 0 | 23 |
| tree-greedy | 14 | **0** | 4 | **52** |
| tree-tournament | 15 | **0** | 3 | **52** |
再次逐字节比较每个失败run的`work/`与该corpus pristine repo里全部非tests、非test_的`*.py`：leaf失败中7/23完全未改；tree-greedy52/56完全未改；tournament52/55完全未改。两个tree的52个“都否”正好全部未改。
源码解释非常直接：
1. `harness/tree_run.py:1540-1567`：仅`result.claimed and result.stop_reason == 'closed'`才进入closed集合。
2. `harness/tree_run.py:1637-1643`：若没有closed，abandon所有候选并park。
3. `harness/tree_run.py:1673-1678`：只有从closed选出的winner才merge回外层work。
4. leaf driver直接grade run_leaf后的work，未要求先claimed：`bench/v2_leaf.py:814-858`调用run_leaf并保留work，后续评分；本次raw明确39个unclaimed过。
所以“tree vs leaf”同时改变了 **拿不到内部证据时是否交付代码**。外部grader虽然相同，喂给grader的字节选择规则不同；“actual使用同一grader”并未消除此混杂。这也解释为什么tree的actual恰好等于claims减false，而leaf未claim成功很多。**它不证明那52个被删除候选原本都能过，也不能直接算修完这个机制能恢复多少题。**被abandon候选目录确实不在，本次不能重建其中每个版本；但交付规则差异和最终回到pristine已是代码/字节两条独立证据。
### 3.2 一个forced-leaf具体例子
`/tmp/wave1/final/r3/tree-greedy/T-02-off-by-one-1/run.json:1`：
- 第一候选`forced-leaf`，确实没拆；随后第二/三候选fallback-leaf；46/48 calls，三个How均失败，winner为空。
- 第一个How是offset分页，第二个How竟改谈cursor-based分页；manager理由引用verification失败继续换How。最终record中的judge原始话说“source pagination logic is correct”，blame=test，却被filter coerce到implementation。
- 最终`work/catalog/pagination.py:11`还是`end = start + per_page - 1`，外部grader2 fail/2pass；独立leaf同题同编号repeat actual=true但claimed=false。
- 删除的HOW-1候选已经不存在，不能把judge那句话当grader证明曾经正确；它只说明内部已有“测试错”信号且流程最终交付原始bug。
这个例子无需真正拆解即可发生大幅损失，因此forced-leaf崩溃不是“拆了也不行”的证据。
### 3.3 最早偏离：先在输入和plan字段上偏离，后在交付上锁死
从代码而非结果标签看路径：
- standalone leaf `bench/v2_leaf.py:288`构造原始goal/AC/source，直接进实现；tree先`_plan_hows`（`tree_run.py:1134-1151`）只给goal、write_boundary文件名、candidate_files文件名、depth，**没有文件内容**。
- 接着`tree_run.py:1192-1200`调用`plan_node`，`harness/node.py:524-532,596-639`也是goal/paths/depth及How evidence，不是检查源码后的受控细化。
- `node.py:206-229`把模型新写goal、files、AC、behavior、implementation_notes、planned_tests/reviews等变成新spec；`tree_run.py:1500-1507`的普通leaf-How使用`decomp.spec`，不是原始spec；即使没有孩子，需求文字、可见/可写范围、测试计划、审核配置都可变。
- `tree_run.py:727-734`把behavior/implementation_notes并入leaf goal；`:736-784`根据spec.files裁source view和write boundary。一个没有拆的tree也不是原来的leaf加一条“不要拆”。
- forced分支`:1478-1488`保留原spec，但仍增加How文本、预算分配、候选复制、manager重试及上述交付策略。root review angles也不同（`bench/v2_tree.py:204-213` vs `bench/v2_leaf.py` root）。
因此最早可观察的机制偏离是**无源码内容的How生成/plan重新描述契约**；最决定最终actual解释的是**closed-only交付**。哪一项贡献多少损失未知，不能仅凭静态代码认定唯一原因。
### 3.4 少数触发不等于有效因果隔离
`requirement-3-result.md:109-147`：B1仅3/70运行拆，3/9任务；B2仅9/70，4/9任务。预注册门槛达到说明“机制存在且偶尔跑了”，不是“实验只改变了拆解”。同文`:255-277`承认多数结果是planning overhead、threshold未扫、root review不对称、tree没trajectory。
- 可以维持的负结论：**这版tree整体方案在这组任务、模型、预算和交付政策下显著更差**。
- 不可维持的更强结论：拆解本身导致差、requirement-level splitting无用、字段细化被证伪、planner少触发就证明适用任务上因果成立。
- fired任务的五seed均值包含未fired seed；只选fired实例也是planner自选择，不能直接当随机处理组。无收益的实例不等于隔离出无收益的机制。
- `docs/STATUS.md:142-147`把“mechanism fired”接成“valid negative”“structural superiority refuted”跨了一步。原始输出重算正确，并不能自动验证这个因果归纳；独立重算文档也重复了该归纳而没有查交付差异。
## 4. close：证据、推断、未知分别是什么
### 有证据
- 最终N25总分近、固定M=3判INCONCLUSIVE；没有测得优于pi，零false success未达成；当前tree bundle负收益。
- 两臂有显著的描述性逐题互补，而非同一批题上的统一天花板。
- 测量之前确做过有价值的失败轨迹/所有写入revision取证，并修了一批harness defect；仍有明确已知缺陷未修。
- R2 full至少有一个IV+review一起错的最终反例；当前审核不是100%；不少正确解不能获内部批准。
- R3交付有closed-only差异，未claim的tree输出大批保持pristine。
- `docs/ROADMAP.md:19-24,45-51`明列V3未闭、V4未达、V5未尝试、V6不存在；ticket`:115-129`明确无不可能性证明、A2未测、cost/wall不完整。
### 可以作出的有限推断
- 继续不变设计地堆seed，大概率不能有效解决当前task-clustered统计精度问题；这是统计设计的判断，不是能力目标无法达到。
- 停止这轮预注册campaign是合理的资源决策；如果用户当时明确要求close，ticket`:92`记录了这一点。但本次没有原始用户会话证据来独立确认当时授权范围，不能用记录自己的陈述证明用户批准放弃全部目标。
- 某些已知defect修复值得尝试，但这不是保证提升；尤其不能将历史discarded-correct案例推成最终所有损失都可确定修复。
### 未知/没有完成
- 最终N25每个失败从第一次写入到交付的完整因果审计；哪些当前失败仍有被丢的grader正确revision。
- 将tree和leaf统一“未claim也交付最佳代码”的规则后，拆解及字段细化的独立效应。
- 同一模型更合理的反馈利用、语义oracle/coverage修复、强模型参考，以及improved-prompt pi的净效果。
- 任意仓库与可见回归测试上的迁移、真实产品命令、完整可比pi tokens和单lane wall。
### 需要收窄的文档话术
1. `docs/STATUS.md:102-117`、`docs/LEARNINGS.md:194`：“zero-information / worthless”应读成“当前消融未检测到净正确率收益，区间仍宽”，不是一个已证明的属性。
2. `docs/STATUS.md:142-147`：“valid negative / structural superiority refuted”只能指当前tree bundle，不是拆解/细化已隔离证伪。
3. `docs/STATUS.md:59-70`、N25报告`:67-75`：“more seeds cannot resolve”是基于当前点估计/方差分解的投影，不是逻辑不可能；分题异质性正是互补信号，也不能拿它当能力终止理由。
4. “review only有效于IV组合”是本次显著contrast分布，尚未单独证明交互；“review negative information”混淆审批策略损失与诊断信息量。
**可向用户直接交付的close表述：这轮campaign结束了，但你的目标没有完成，也没有被证伪。之前确实发现并修过harness自损，却没有把最终全部失败解释完；Test/Review的问题不只是模型弱，还有oracle、覆盖、归因与反馈利用；tree的负数真实，但未把拆解和字段细化从计划改写、预算及交付策略里隔离。不能用这些结果替代对目标的继续判断。**
## 5. 可复算命令（只读、小数据，不调用模型/测试）
以下是本次使用的核心计算；不运行分析器的main（会写analysis JSON），仅加载已检查的函数，并用`-B`不写pycache。
```sh
cd /home/z/vibe/helpagent
python3 -B - <<'PY'
import runpy, collections
m = runpy.run_path('/tmp/wave1/final/n25/analyze_n25.py')
o, p = m['collect'](25)
a = {(r['task'],r['seed']):r for r in o}
b = {(r['task'],r['seed']):r for r in p}
assert len(o)==len(p)==len(a)==len(b)==1000
allc = collections.Counter()
maxsum = 0
for t in sorted({k[0] for k in a}):
    c = collections.Counter((bool(a[t,s]['actual']),bool(b[t,s]['actual'])) for s in range(1,26))
    x = sum(a[t,s]['actual'] for s in range(1,26))
    y = sum(b[t,s]['actual'] for s in range(1,26))
    maxsum += max(x,y); allc.update(c)
    print(t,x,y,'both',c[1,1],'O-only',c[1,0],'P-only',c[0,1],'neither',c[0,0])
print('quadrants', allc, 'taskwise-max',maxsum/25)
PY
python3 -B - <<'PY'
from pathlib import Path
import json, collections
root=Path('/tmp/wave1/final/r3')
for arm in ['leaf','tree-greedy','tree-tournament']:
    c=collections.Counter(); unchanged=0; failed=0
    for p in (root/arm).glob('*/run.json'):
        r=json.loads(p.read_text()); c[(r['actual'],r['claimed'])]+=1
        if r['actual']: continue
        failed+=1
        original=Path('bench/corpus')/r['task']/'repo'
        files=[q for q in original.rglob('*.py') if 'tests' not in q.relative_to(original).parts and not q.name.startswith('test_')]
        assert files
        w=p.parent/'work'
        unchanged+=all((w/q.relative_to(original)).is_file() and q.read_bytes()==(w/q.relative_to(original)).read_bytes() for q in files)
    print(arm,c,'failed-original-python',unchanged,'/',failed)
PY
git diff 45ebb32 HEAD --stat -- harness/leaf.py harness/tree_run.py harness/node.py bench/v2_leaf.py bench/v2_tree.py
git status --porcelain
```
说明：raw数据当前仍在`/tmp/wave1/final/`，本次能读到不等于长期有可靠归档；只在临时目录保存主要raw是复审可恢复性的残余风险。本次未移动、复制进项目或清理它们。
## 审计限制
- 无外部文献检索，故不作“已有研究已证明所有review上限”的判断。
- 本次不执行旧grader反事实；历史passing revision依赖此前forensics所留证据，不声称本次重新验证。
- 没有恢复已删除的tree候选，也没有对140个tree失败重跑模型；52个pristine交付事实不等于52个潜在正确候选。
- 最终逐题模式基于grader notes和局部raw rows，不是1000个失败/成功trajectory全量因果重建；涉及根因时已区分历史证据、当前观察与推断。
