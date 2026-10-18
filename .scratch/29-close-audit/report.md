# Campaign close 收窄与最终 revision 有界因果取证
## 结论
结束的是这轮预注册 campaign，不是三个目标：当前实现未测得总体能力优势、零 false success 未达成、最终失败未全部解释；这些结果没有证明目标不可能。
本次把四份当前文档中的“zero-information / worthless”“review 只有 IV 在场才有效”“tree 证伪拆解/结构优势”“更多 seeds 逻辑上不能解决”收窄为数据实际支持的结论；原测量数字、archive 状态和验收目标保持不变。
有界轨迹显示不同失败层，不能合称“模型上限”：pi 的 T33#1 长推理后输出长度终止，T12#1 有失真的重现输入并最终出现 context-size error；ours 的 T16#2、T30#2 先写过静态上满足修复核心的中间版本，随后回退/漏 import；T26#1 丢掉兼容性断言并只写一次，IV 的真实错误反馈用于阻 claim 而未转为下一次 implementation。
共同全败也不是同一种根因：A02 的返回形状在可见接口里缺失，内部测试/审核一致认错；A03 忽略明示的分组优化反例，IV 有正确反证也混入错误 oracle；A04 自写测试先互相矛盾，生成代码缺 board 初始化及 Hex 邻接；T27 除允许键集合缺失，还连续生成转换错误/非法代码；T34 自写测试把单引号改成双引号，之后归因失真和语法退化。最终 R2 A05#1 则从第一份测试就把“谁喝水”写成“water”，最后 IV/review 一起批准错误答案。
本报告没有实现修复、没有模型调用、没有重跑原 grader，也不把静态判断或另一个 run 的成功冒充这个中间版本的 grader 成功。
## 范围、revision 与证据等级
- 用户批准范围、非目标、90分钟预算和真实起始时刻见 [ticket.md](ticket.md)；baseline 为 `72f25fac838afa5b6ff1b7799225ebfd6e252a1e`，初始 working tree 干净；测量 pin 为 `45ebb32f1be0977b9149057da3a80ee93ce22840`。
- 精确代码/数据边界检查：`git diff 45ebb32 HEAD -- harness/leaf.py harness/tree_run.py harness/node.py bench/v2_leaf.py bench/v2_tree.py bench/pi_baseline.py bench/corpus bench/anchor` 为空；故本报告的源码行号和保留的 corpus 原件适用于测量 revision。最终 patch 只改四份当前文档和本工作记录。
- **本次直接证据**：读 raw row、原始模型输入/输出、test execution 记录、控制器事件；逐字节比对/哈希及不执行代码的 AST parse；“某 stage 当时绿/红”指日志记载，不是本次执行。
- **历史 grader 证据**：最终 raw row 的 `actual/grader_notes` 是测量时的外部 grader 结果；本次保存当时 `grade/<task>/repo` 的实际输入字节；未重新验证其运行环境或重跑测试。
- **推断**：由源码或轨迹解释为什么某错误会影响交付；“静态正确候选”表示按可见契约检查、或与 passing control 的实现一致，未取得该中间候选的独立 grader verdict；模型自己说“correct”不计入正确性证据。
- **unknown**：潜在最早认知偏离、未保存/未评分的中间版本实际 grader 结果、服务端 context 错误的底层容量/请求原因、修复后的净收益；都不填成零或 model-ceiling。
- 选择是目的性样本，不是失败发生率估计：11题两臂各一个代表（T30/T16 取#2，其余#1）、T26 加 pi#2 成功对照、R2 A05#1，共24个 run。只对这些 run 逐轨迹查看；没有宣称全量 N25 轨迹已解释。
- [sample-router.md](sample-router.md) 给全部24个 raw source/行号及本地副本；[sample-map.json](sample-map.json) 定义下文 `OT33`、`PT33` 等别名；`OT16/trajectory.jsonl:15` 即 `evidence/ours-T-16-class-state-leak-s2/trajectory.jsonl:15`，不是源码第15行；下文 `specs/` 是本记录 `evidence/specs/` 的简写。
- [revision-table.md](revision-table.md) 路由12份 ours/R2 trajectory 中50个 source_write 的完整 SHA256、模型 payload 行和最终 graded 字节身份；每个 run 的 `index.md` 是由原始记录生成的视图，完整 prompt、artifacts、raw 和 envelope 留在相应 `trajectory.jsonl`。
- pi 的 streaming deltas 不全量复制：只保留 `message_end/tool_execution_start/tool_execution_end`，每行带原 `events.jsonl` 行号，原文件 hash 在 [manifest.json](manifest.json)。这保留最终模型内容/工具参数和结果，不能重建 streaming 的逐 token 时序。
## 1. 先分清总分、症状与原因
[summary-check.txt](summary-check.txt) 从 N25 明确根路径重算 ours `616/1000`、pi `624/1000`，并与 frozen analyzer 的 collect 结果交叉核对；[outcomes-selected.json](outcomes-selected.json) 仅保存指定11题两臂25次的550条有界字段投影（含 raw 行 hash、source/行号）；不是完整 raw 的第二份存储。
| task | ours /25 | pi /25 | pi 失败且 files_touched 为空（元数据） |
| --- | ---: | ---: | ---: |
| T33 | 23 | 1 | 24 |
| T12 | 24 | 6 | 19 |
| T35 | 1 | 20 | 2 |
| T30 | 15 | 25 | 0 |
| T16 | 17 | 25 | 0 |
| T26 | 2 | 10 | 15 |
| A02 | 0 | 0 | 10 |
| A03 | 0 | 0 | 25 |
| A04 | 0 | 0 | 25 |
| T27 | 0 | 0 | 23 |
| T34 | 0 | 0 | 24 |
“files_touched 为空”只说明 driver 没记录 write/edit tool path，不能排除 bash 写文件；本报告仅对所选 pi 失败 run 另外核实了 `work` 与 pristine Python 字节相同。不能由这张表把其他 repeat 都归为同一个原因。
**新的边界证据**：T33#1 `PT33/events-selected.jsonl:30` 明载 `stopReason=length`、output=8192；T12#1 `PT12/events-selected.jsonl:32`、A02#1 `PA02/events-selected.jsonl:15`、A04#1 `PA04/events-selected.jsonl:3`、T27#1 `PT27/events-selected.jsonl:17` 明载 `errorMessage="Context size has been exceeded."`；A03#1 `PA03/events-selected.jsonl:14` 和 T34#1 `PT34/events-selected.jsonl:22` 是 length/output8192。
这些 raw rows 的 `timed_out=false` 与上述事件不冲突：`bench/pi_baseline.py:323-337` 的 timeout 指 subprocess deadline，不是 inference error；`:63-71,137-145` 声明的是 contextWindow32768/maxTokens8192。**配置声明不证明每个请求获得的有效上下文容量**；这里不能擅自推断 slot 大小、服务端限制或实际被截断的所有 token 数，更不能仍把“0 crashes/timeouts”读成“所有 inference 都成功完成”。
## 2. 两臂差异最大与反向差异题
### 2.1 T33 — pi#1：未交付修复，不是写出的 serializer 修复都错
- **目标与可见输入**：`PT33/prompt.txt:3-9` 与 `specs/T-33-serializer-contract/request.md:1-6` 给 roundtrip、ValueError 和 frozen base；`PT33/events-selected.jsonl:7,11-15` 包含读取全部 serializer 源码及 README 的工具结果。
- **首偏离边界**：没有 source-write revision。模型 `PT33/events-selected.jsonl:23` 已花6213 output tokens 反复讨论 JSON 默认 escape 与“foreign bytes”的解释，又搜索隐藏测试；`:30` 的8192-token thinking 末尾已经指出 pickle 外来字节会抛 UnpicklingError、应转 ValueError，却在发出 write/edit 前 length 终止。这是**生成/执行预算与交付停在零修改**的直接证据；哪一句思考最早导致失控不能由末态日志严格确定，不把“思考很长”作为单一因果测量。
- **最终症状/字节**：`PT33/row.json:1` 的 grader 为1 fail/5 pass，唯一摘要失败是 PickleSerializer foreign bytes；`PT33/grade-repo/serialize/pickle_ser.py:13` 仍是 `return pickle.loads(data)`，JSON 和 pickle 交付均与 pristine 相同。
- **成功对照**：`OT33/trajectory.jsonl:12-14` 第一次 implement 就写出两个 serializer 修复，grader actual=true；可写源 hash 前缀 `276d190635cb` / `36c18f9e929d`。`:34-44` 的 IV 要求 JSON bytes 直接包含 café（超出 roundtrip 的更强格式要求），`:46-49` 第二份 IV 还有非 ASCII bytes literal 语法错误，阻了 claim 却未破坏外部成功；不能把“IV 红”当成源码错。
- **正确 candidate 与下一检查**：所选 pi run 没有已落盘正确 candidate；同 revision 的 ours control 有历史 grader 成功。若要解释 pi 所有24个失败是否同因，下一检查是各自终止事件、write action 与最终字节，不是再堆模型实验；底层 context/length 原因需要当时请求/server日志，当前未取到。
### 2.2 T12 — pi#1：重现 fixture 掩盖 identity bug，再在 context error 前停止
- **首个明确错误产物**：`PT12/events-selected.jsonl:28` 用字面量 `"editor"` 代替“解析自 webhook header”的等值但不同对象；`:30` 实际输出 app/webhook 均True、identity均True。模型之前已在`:24`认出 `is` 应改 `==`，却因这个不忠实 fixture 又进入字符串驻留的长推理；`:32` 以 context error 结束，没有 edit。不能把 fixture 与容量错误之间的相邻顺序说成已隔离的因果效应。
- **最终症状/字节**：`PT12/row.json:1` 为 webhook parsed editor failure；`PT12/grade-repo/access/gate.py:20` 仍是 `author.role is r`，与 pristine 相同。信息并非完全不足：源码/README 明示相等角色应同待遇；失败链是**重现/推理预算/未交付**，不是可证明的生成能力天花板。
- **成功对照也会被 verifier 错拒**：`OT12/trajectory.jsonl:8-9` 一次落盘 `==`（`62dff31b50c5`），外部 actual=true；`:20-26` 的 IV 将“webhook editor rejected”的症状写成目标，assert False；`:37` judge 甚至建议改回 `is`，但没有后续源码写入，最终 claim=false，actual=true。当前已有 desired-state 提示仍不保证不反转 oracle。
- **正确 candidate 与下一检查**：pi所选失败 run无 candidate；ours有历史 grader 成功 final candidate。下一最小检查是其余pi失败的最终事件/字节，或保留当时 server请求以解释 context error；不能由汇总0timeout否定这个错误。
### 2.3 T35 — ours#1：坏测试最先偏离，最终仍有独立的返回形状缺陷
- **首偏离**：`OT35/trajectory.jsonl:2` 的 own test（`payloads/L002/spans/test_merge.py:8-25`）没有 import merge；第21行还把应合并成 `[1,4]` 的 touching chain 期望成两个残缺 interval。`:3` pristine红是NameError，不是行为区分力；`:6-8` 第一次写出 merge 后仍同一NameError。
- **传播**：`:10-12` judge 标签说test、理由却说“merge不在源码定义”，filter归implementation；`:15` 的 implementation artifacts.failure_output 真的注入这段误归因。八次 source_write 位于`:7,16,22,28,34,40,46,52`；`:45` deterministic diagnosis在只许改source的step里要求“add import”，但测试根本未修。own-test八次红一直是未绑定名字，并不能区分这八版算法。
- **最终偏离**：最终payload `L051/spans/merge.py:17-25` 对未合并元素沿用输入 tuple，对合并结果新造list，hash `399e8d6a0256`；外部 grader 的 overlapping/touching/chain 三个失败与 list-vs-tuple 完全对应（`row.json:1`、`specs/T-35-interval-merge-invariants/repo/tests/test_merge.py:10-27`）。这不是单纯“验证把正确代码挡掉”。可见契约的返回注解只是list，未明说元素必须tuple；这是**接口表示信息缺口 + test生成/归因 + 最终生成**的混合，不把隐藏形状要求当模型本已知道的事实。
- **Test/Review状态**：`:58-69` IV首次语法错、repair后采用list输入/list期望而approve；`:70-75` best-evidence接纳IV版本，但own-test仍NameError，verifier conflict阻claim，普通review未运行。IV绿只是它那套fixture通过，非外部契约被证明。
- **成功对照/unknown**：`PT35/events-selected.jsonl:18` 首次write始终返回tuple，final actual=true；`:22-46` pi自己也写错预期，但后来只修test不改正确source。所选ours run没有grader证实的中间正确candidate；前七版的外部结果unknown，第八版与实际graded final字节一致（`revision-table.md:18`），保留的`OT35/row.json:1`记载历史外部grader失败（3 failed、3 passed），不是本次重跑。下一检查是对前七版保留payload做授权后的有界grader反事实，尤其返回形状；本次不重跑。
### 2.4 T30 — ours#2：不区分的own test消失，正确核心曾出现，最终漏import
- **首偏离**：`OT30/trajectory.jsonl:2-7` own test两次都构造naive expires_at和naive at（`payloads/L002/test_tokens.py:10-15`），没有制造请求里的aware expiry/naive caller不匹配；两次pristine绿后被丢掉。`:11` 转review，后面没有可运行的own-test目标。
- **逐版关键变化**：`:13-14` v1/v2（第二次`:28-30`相同）用本地 `datetime.now().astimezone().tzinfo`，不是明示UTC；`:41-42` v3补 `timezone.utc` 且在文件末尾 import timezone（hash `4af3dc7d5344`）；`:53-54` v4又用本地timezone；`:65-66` v5、`:78-79` v6用 `timezone.utc` 却都漏import，final hash `9cc3a3dd8a6e`。
- **传播到选择/交付**：每轮review文字都approve但被`review_not_grant_calibre`拒（`:25,38,49,61,73,86`），下一轮implementation收到的是审核证据措辞不够的feedback（`:28,41,53,65,78` artifacts.failure_output），不是修实现的行为反例；M1提示明确“previous draft was erased”。没有任何best_evidence_revision事件，v3未被证据排名留作交付，最后v6落盘。
- **最终证据**：`:91-97` IV终于用aware expiry/naive caller，记录NameError timezone未定义；`:98-101` judge错误归test，deterministic reconciliation拒绝override；`:103`24calls stop。`row.json:1` 的外部两个失败与最终`grade-repo/tokens/tokens.py:16`完全一致。review知道“replace timezone.utc”不等于检查过import。
- **正确candidate与对照**：v3静态上有正确的UTC处理和import，与`PT30/grade-repo/tokens/tokens.py:3,19-21`的passing逻辑一致；该中间版本未获grader verdict，不能称“本次证明被丢弃的grader正确版本”。pi#2 final actual=true。下一检查为v3最小反事实评分；这里已有可定位的**fixture不足/反馈利用/生成退化/证据选择**链，不需用模型上限解释。
### 2.5 T16 — ours#2：缺import的测试掩盖正确中间修复，再被M1回退
- **首偏离**：`OT16/trajectory.jsonl:2-3` 自写test直接`Cart()`无import（`payloads/L002/test_cart.py:6`）；pristine红与后续红均NameError。测试名`new_cart_is_not_empty`不正确，但断言是空列表；不能仅凭名称诊断方向反转。
- **关键revision**：v1`:6-7`原样共享class list（`c302c53493ad`）；v2/v3`:15-16,20-22`新增无参数`__init__`、`self.items=[]`（`8171a419e763`），静态满足独立cart核心；`:27-28` M1重生又回到class list，后续`:34,40,46,52`同样坏字节。v2/v3的own test仍NameError，不是其实现失败。
- **传播**：`:10-12` judge同时写出“Cart未在test导入”和class-list问题，最终被filter归implementation；`:15`收到这段反馈后确写对核心。`:27` artifacts仍携NameError、question明说draft erased；`:45`仅source可写却要求“Cart定义在cart/cart.py，add import”。直到`:57` ladder用尽10calls，IV/review从未运行，没有best_evidence_revision可恢复v2。
- **最终/对照**：`row.json:1` 外部1fail/1pass；`grade-repo/cart/cart.py:6`共享list，与v1/v4后字节相同。`PT16/grade-repo/cart/cart.py:5-8`无参构造器+instance-list获historical actual=true。v2/v3是静态正确核心候选，不是本run已评分正确candidate；下一检查可对保留v2做授权后的最小grader反事实。
### 2.6 T26 — ours#1：兼容断言与错误type断言一并删除，IV发现缺陷后只停止
- **首偏离**：`OT26/trajectory.jsonl:2` own test把“保留dict式访问”扩成`isinstance(plan, dict)`（`payloads/L002/test_plan.py:6-19`），额外限制具体类型，不能替代dict式访问契约；同一函数内也有应保留的`plan['name'] / ['steps'] / ['done']`断言。`:5-10`一次rewrite未改变问题，控制器把两个pristine绿函数整段删除；最终own test只测attribute access。这里有明确的**契约误读 + 覆盖选择损失**，不是所有绿测试都是“症状”。
- **唯一实现**：`:12-13` port成plain dataclass，无`__getitem__/__setitem__`，hash `cf0cf2a54f8d`，与自己注释“public surface plan['name'] must keep working”相矛盾。`:14` own绿后，`:18-21`两个review都称dict-style preserved，错误批准有直接字节反证。
- **IV与反馈利用**：`:22-25` IV在原版import Plan失败，在最终版报`Plan not subscriptable`；`:27`控制器马上`review_blocked_by_red_independent_test`并stop，不是call-budget耗尽。最终阶段`:29-35`再次记录相同错误，judge提出加`__getitem__`，但后面只有review，无第二次implement。代码`harness/leaf.py:7292-7297`正是这条stop分支；不能把它描述成“测试已经指导模型修过仍不会”。
- **最终/对照/unknown**：历史外部grader1fail/1pass，缺兼容接口与final字节一致。`PT26bad`#1也是未写源码的失败；`PT26good/events-selected.jsonl:25`#2实现dataclass与mapping兼容并获actual=true，自己的验证曾因`dataclass.declared_fields`错误而失败，`:33`修test后成功。ours没有中间正确candidate；不知道真实IV反馈后若再implement能否修好，下一检查为控制器反馈/停止策略的受控验证，未获本任务实施授权。
## 3. 双方25次共同全败题（仅所选repeat的原因）
### 3.1 A02 — ours#1：输出接口缺口被三个checker共同固定为错误string
- **输入信息边界**：`specs/A-02-protein-translation/request.md:5-36`给codon映射和STOP，但没有Python返回类型、list格式或错误输入行为；可见source只有`def proteins(strand): pass`。隐藏grader的list期望见`repo/protein_translation_test.py:13-16,83-86`。不能把这部分称“明确契约都给了而模型仍不会”；也不能说完整算法信息都没有。
- **首偏离/逐版**：`OA02/trajectory.jsonl:2` own test先选择`'Methionine-Phenylalanine-Serine'`和空string作为oracle；`:6-7` v1按该形状生成，还把STOP当普通值追加；`:15-17` v2注释声称已修，hash却与v1相同；`:22-23` v3真正停止处理STOP，但保留`return '-'.join(result)`（`cebed312ddee`）。所有已落盘版本都返回string，未见正确list候选。
- **传播/审批**：`:28-31`review认可hyphen join，`:32`IV给17个AC节点，多数重复相同string断言，连外部知识链接也重复同一个返回断言；`:51-70`原红/终绿、逐AC机械覆盖通过，claim basis=review+IV。`row.json:1` external26fail，final`grade-repo/protein_translation.py:25`与v3相同。
- **pi对照**：`PA02/events-selected.jsonl:7`读到stub，`:15`长思考后context error，未写代码，final仍pass stub；没有成功control（两臂25次全败）。pi有关于list/STOP的思考不算candidate。下一检查是明示可见API返回约定的来源，以及pi终止原因；不把隐藏测试灌给run，不以改验收替代解释。
### 3.2 A03 — ours#1：明示反例没有进入own test；IV既有有效反例也有矛盾oracle
- **信息足够的部分**：request明给同一8本书5+3=$51.60不如4+4=$51.20，要求最大折扣；单位cents/dollars未在可见stub约定，而隐藏grader用cents（`specs/A-03-book-store/repo/book_store_test.py:14-16,42-44`）。这两个问题须分开，不能把忽略分组优化都归为单位信息缺失。
- **首偏离**：`OA03/trajectory.jsonl:2` own test只有2/3/4/5不同书各一套，没有重复书或request中的核心8本反例；`:6-7`唯一source是`len(set(basket))`选一个折扣率、对全basket统一折扣（`ec3c4d4fb02e`）。即使按dollars，8本被算48、重复第四本被错误打折，已违明示要求。
- **Review/IV传播**：`:12-15`review称8本例子是51.20，但代码公式不可能给出该数；`:16`IV的同一8本basket同时被要求51.60和51.20（payload L016），把说明中的次优方案也机械变成函数oracle。`:50-53`IV red-on-final有真实证据28.8≠29.6，也有错误51.60断言，不能把全部红归对或全部归错。
- **停止/最终**：`:91-93`judge终于点出多组优化，却建议优先5再4的greedy，尚未证明能处理明示反例；之后只有review（`:95-100`仍approve），无新implementation。`:101`10个IV未满足项伴随9calls停；raw external19fail/1pass，`grade-repo/book_store.py`即唯一坏实现。没有已知正确candidate。
- **pi/下一检查**：`PA03/events-selected.jsonl:14`输出8192后length，final stub，25次files_touched都空仅是metadata统计。下一检查先分离有效/矛盾IV oracle及可见单位契约，再看控制器如何把有效反例送入下一implementation；本次不执行修复。
### 3.3 A04 — ours#1：测试从输入表示和互斥oracle偏离，代码另有实质算法错误
- **首偏离**：`OA04/trajectory.jsonl:2` test把request的文本board改成不规则nested list；同一个board分别期望`'O'`与None（`payloads/L002/test_connect.py:14-36`）；这不是一套可同时满足的确定性函数契约。`:6`rewrite仍同board双oracle，`:9`整函数删除没成功（removed=false），错误fixture保留。
- **逐版与归因**：`:11-12` v1构造器仍pass，马上`self.board` AttributeError（`:13`）；`:15-16`judge理由说应初始化source、blame却是test，被接纳后重写同一test而失败（`:17-18`）。`:20-21` v2补self.board，`:29-30` v3几乎同逻辑，但仍只直下/直右、只选第一个起点、未解析文本行、边界成功判定先于确认终格player。
- **反馈和预算**：`:24-25`judge明确指出Hex六邻接；`:29`下一implementation artifacts.failure_output包含这个有效诊断，代码却未落实。这一项有“反馈真的送进生成但未应用”的证据，不是泛称控制器没反馈。三次attempt后`:33,54`attempt cap停止，10calls，不是24-call预算耗尽；IV有inverted节点（`:48,55`），ordinary review未运行。
- **最终/unknown**：raw external12fail，与final `f9eadeab4b7e` 对文本board当字符网格等缺陷一致；无中间正确candidate。隐藏grader no-winner=`""`，可见stub无return约定，另属信息缺口，不足以解释连有winner样本也全败。
- **pi/下一检查**：`PA04/events-selected.jsonl:3`第一轮长推理就context error，无工具/无write，final stub；不能称它已经尝试过算法实现。下一检查是输入/输出接口记录、互斥fixture的机械检查及已送达邻接反馈为何未落实；本任务只保留假设。
### 3.4 T27 — ours#1：schema未给全，但从第一版就违背给定样例，最后交付syntax error
- **输入信息缺口**：可见request/module/README没有允许键集合，虽然明确firstName→first_name和unknown dropped；隐藏grader还要求user_id保留、junkField丢弃（`specs/T-27-snakecase-ingest/repo/tests/test_records.py:6-15`）。未提供schema是当前直接观察，不能据此推成任务逻辑不可能，也不能让模型凭空知道allowlist。
- **首个源码偏离**：`OT27/trajectory.jsonl:2-3` own test给了firstName/lastName转换和unknownKey丢弃，可在这些范围内提供有效反馈；`:6-8` v1只是lowercase、保留所有键，连明示样例都不满足。`:10-13`judge理由正确指出lowercase不足，标签自相矛盾被filter归implementation；`:16`下一写入确增加helper，但语法坏（curly quote）。
- **逐版传播**：6个写入分别`:7,17,24,31,36,43`；v2/v3语法错，v4/v5调用`str.split`传三个string参数而TypeError，v6最后又语法错。`:42`的最终payload含`key.split("[", "_"]")`，hash `88e78b580a61`；`:45,50`source_unparseable记录，`:51`ladder exhaustion8calls；IV/review未运行。
- **最终/对照/下一检查**：raw grader collection error与final syntax error一致；没有正确candidate。`PT27/events-selected.jsonl:17` context error，final仍直通dict；这不是同一种代码错误。下一检查一是找本来应暴露的schema来源，二是按生成/语法/执行分离已有失败反馈；不以补隐藏答案或task特化冒充通用改进。
### 3.5 T34 — ours#1：字符串方向一开始就错，返回形状也不可见，后来语法退化
- **首偏离**：`OT34/trajectory.jsonl:2` own test用double-quoted `"hello"`和`"unterminated`，而request/module明写single quotes；同份test还自定返回裸string数组，隐藏grader却期望`('int',value)`等typed tuples。typed-token约定没有出现在可见request/module/stub，属于接口信息缺口；doublequote错误则不是信息缺失。
- **逐版**：`:6-7` v1识别single quote但闭合逻辑反了，正常结束会raise、未闭合反而append，own test报doublequote非法字符；`:10-12`judge把“期望doublequote”与“实现只认doublequote”混为一谈，被归implementation。v2`:15-18`出现未闭合triple quote；v3/v4`:22-29`重复原来问题；v5`:33-35`能取单引号内容但不解码escaped quote且仍裸strings；v6/v7`:38-49`坏反斜线literal导致syntax error。
- **传播/最终**：后续implementation持续收到wrong doublequote测试的失败；`:46-47`最终`38a3096c4a79`，`:54-55`source_unparseable/ladder9calls，IV/review从未运行；外部collection error与final字节一致。无外部证实的正确candidate，且保留各版都有可见的实质问题，不能把“曾parse成功”升级成grader正确。
- **pi/下一检查**：`PT34/events-selected.jsonl:22`length/output8192，final仍return[]；25次中24次失败files_touched为空只是metadata。下一检查先确认typed-token接口本应从何获得，并分开singlequote oracle与语法错误；不是用旧revision tokenizer案例替代当前原因。
## 4. 最终 R2 A05#1 — Test / Review 错误批准的完整链
- **首偏离在own test而非review**：`R2A05/trajectory.jsonl:2` own test把“哪个居民喝水”写成`drinks_water() == "water"`，owns_zebra期望Japanese；`:3`因路径属于withheld grader而未落盘。它虽未执行，说明模型的第一份oracle已经错，不是后来IV才独立发现了这个答案。
- **唯一实现**：`:5-6`模型写死water/Japanese person，`1bd694e5574e`；`:7-8`无expected-tests的表面绿被gate拒。`:10`judge文字已说hardcoded wrong、应解15条约束，却仍blame=test；`:11-12`filter归implementation。这条信号存在，但没有第二次implementation。
- **审核为何放行**：`:13-16`两个fresh review输入有goal/AC和final code，仍声称water/Japanese person“directly match required answers”；这不是泛泛缺证据，而是明确错误语义判断。`:17`以review rank1记best evidence；review并没有可信执行oracle。
- **IV为何也放行**：`:18`写21个AC函数，多数对同两个常量重复断言；AC14 Norwegian-first-house、AC20 all-attributes-different也没有验证对应约束。`:19-40`pristine None对这些常量全红，`:41-62`final全绿，`:63`记录21/21 covered；节点编号与红绿只证明能区分stub和常量实现，不证明oracle对、更不证明语义覆盖。
- **如何变成false claim**：`:64`IV rank3晋级同一源码，`:65-67`green/claimed=true；`row.json:1` basis=review+independent-test、actual=false；实际graded两个函数仍wrong，`grade-repo/zebra_puzzle.py:1-6`与唯一write相同；withheld `specs/A-05-zebra-puzzle/repo/zebra_puzzle_test.py:14-18`期望Norwegian/Japanese。Japanese person连接口字符串也不符。
- **层次/unknown**：这是**契约问句误读、算法未做、测试oracle与覆盖错误、review错误批准、控制器机械admissibility无法辨语义**共同传播；没有正确candidate。现有直接证据足以否定“当前组合审核正确率100%”；不能推出所有未来review设计必然失败，也不能由一次同错推测所有相关错误率。
- **下一检查**：若另行获授权，先用不泄露本题答案的契约语义/覆盖判别负控和有效诊断后的重写闭环验证假设；本次不实现、不改目标、不把题目正确常量写进harness。
## 5. 为什么 R2 / R3 的 close 结论必须收窄
- **R2测的是workflow bundle净效应**：A0通常第一次落盘停（`harness/leaf.py:8564-8575`），A1另加test/judge/rewrite/升级/交付选择；不可能从A1−A0不显著独立推断测试无信息。`−1.33 [−5.67,+3.00]`容纳负与正效应；没有等价界检验。A4−A2显著而A3−A1不显著，也不等于交互显著。
- **有具体反证而不是单一stage标签**：OT26的IV报真实缺失接口但流程停止；OT12的IV错拒外部正确代码；OA03的IV混有真反例与矛盾oracle；R2A05的IV+review共同错批。当前stage-final joins不测纯诊断准确率，更不能把“未携claim”当测试没有影响代码。
- **R3输出负数已重新核实**：[r3-observations.json](r3-observations.json)、[summary-check.txt](summary-check.txt)来自210个run.json及最终非tests Python source hashes：leaf实际通过且未claim39；两个tree arm均有52个未claim失败，全部final Python与pristine相同。source判据固定为pristine里非tests、非test_的*.py；它不度量候选内部正确率，也不度量新增非Python文件。
- **交付路径不是同一个处理**：`harness/tree_run.py:1540-1567`只将claimed且closed候选放入closed；`:1637-1643`无closed就abandon；`:1673-1678`仅从closed挑winner才merge。leaf没有这个交付前提。故“grader相同”不代表grader得到的候选字节经同样规则选择；即使forced-leaf也保留这一差异。
- **保留一个可恢复例子**：`evidence/r3-tree-greedy-T-02-s1/run.json:1` first how为forced-leaf，无winner、46/48calls；`work/catalog/pagination.py:11`仍off-by-one。对照`evidence/r3-leaf-T-02-s1/run.json:1` actual=true/claimed=false；tree-tournament同编号也留了run/source。被abandon的tree目录不在，不能从judge“源码正确”一句话声称候选已过grader。
- **最早bundle差异还在plan**：先前审计保留在 [evidence/prior-investigation.md](evidence/prior-investigation.md) §3.3；本次又沿这些坐标核实`harness/tree_run.py:1134-1151,1192-1200,1500-1507`、`harness/node.py:206-229,524-532,596-639`：无source-content的How/plan可重写goal/files/AC/test/review，`harness/tree_run.py:727-784`再影响leaf输入/边界。这个静态证据说明处理混合，不量化各机制贡献。
- **可维持的结论**：这版tree bundle在该模型、corpus、预算、planning和delivery政策下显著更差；splitting/field refinement本身的效应未被隔离。既不改负数字，也不将“mechanism fired”当因果隔离或结构优势总体被证伪。
## 6. 不能从这些样本推出什么；只保留通用改进假设
- 最终N25有逐题互补，但没有持出验证的路由器；本任务没有实现选择器、改baseline prompt、开新实验或修harness。
- T16/T30有静态正确核心中间候选，但其实际grader verdict尚unknown；本任务没有借用`d24410a/6b224f5`的T07/T17/T28 grader案例来证明最终版本丢了多少正确答案。旧记录只证明历史上存在该类缺陷。
- 一些输入接口确实缺信息（返回list/typed token/cents/no-winner值/allowlist）；这些缺口不自动解释所有失败，也不授权修改corpus、泄露grader或降低验收。明示的STOP、分组优化、singlequote、instance-state等错误仍应单独解释。
- 可检验但未实施的假设：先区分测试setup/parse/runtime与行为红；保留有效compat断言而不以pristine绿一律删；语义oracle/覆盖判别优于节点名计数；有效反馈后确实产生下一次implementation；候选字节/证据绑定与生成累积；对inference终止单列预算/错误；tree/leaf统一delivery后再隔离splitting。每项都需独立受控验证，不能承诺净收益，不能task特化。
- 未建立的部分都有下一检查，而不是“model-ceiling”默认：中间版本用保留payload再评分、缺接口追到可见spec来源、pi终止追到当时server/request、tree被删除候选需原始留存/备份。不存在的记录明确missing；不能靠重跑模型恢复“同一次”历史。
## 7. 可恢复证据、复算与审查
- [manifest.json](manifest.json) 是byte-copy/selected-event/selected-row的source路径、原hash、目标hash、大小/行号；[manifest-supplement.json](manifest-supplement.json) 是三个R3对照；[summary-input-hashes.json](summary-input-hashes.json)绑定统计所读raw文件。主要raw仍在/tmp，未移动、删除或改写；这里只保存所用有界非敏感证据，不复制海量stream。
- `collect_evidence.py`只收24个指定run的row、prompt、trajectory或terminal tool/messages、work及**实际graded repo**，加公开corpus specification；`index_trajectories.py`只解析文字/AST、抽模型原样payload并核对source_write hash；`build_tables.py`生成router/revision表；不会执行候选代码。
- 无grader重跑：原grader对中间revision的反事实结果会增强T16/T30判断，但用户默认不重跑且当前验收允许unknown+下一检查；静态哈希/轨迹已经足以完成此有界解释，不需为验收额外启动测试资源。
```sh
cd /home/z/vibe/helpagent
python3 -B .scratch/29-close-audit/collect_evidence.py
python3 -B .scratch/29-close-audit/index_trajectories.py
python3 -B .scratch/29-close-audit/build_tables.py
python3 -B .scratch/29-close-audit/recompute_summary.py
python3 -B .scratch/29-close-audit/verify_evidence.py
python3 -B .scratch/29-close-audit/check_docs_semantics.py
git diff --check -- README.md docs/STATUS.md docs/LEARNINGS.md docs/ROADMAP.md .scratch/29-close-audit
```
前四条复算需要/tmp原件（缺失则失败而非伪造）；manifest哈希核对、保留样本的轨迹重建和fresh review可以仅凭本工作记录恢复。机械结果、最终diff/status及精确hash见 [checks.txt](checks.txt)、[commands.md](commands.md)、[delivery.json](delivery.json)；fresh reviewer 的判断契约见 [review-contract.md](review-contract.md)。
