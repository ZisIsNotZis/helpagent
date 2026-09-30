# 20 — How axis, the selection function, and immutable plans

Status: planned (implementation starts after the ticket-19 round-3 verification lands)
Owner direction: 2026-09-30 (the scaling discussion)
Need-review: yes (independent adversarial verifier lane per step)
Need-test-cases: yes

## The model (owner-specified)

```
节点
 ├─ How[]     每个 How = 一段"怎么做"的文字 + rank + 理由 + 先验
 │             每个 How 各自拆解 → 子节点[]（拆解不可变；How 不可变）
 └─ 叶子       选定的 How → 实现产物 + 规划期声明的测试清单
```

- **需求罗列是确定性的**（同一段文字只有一种罗列）；**拆解/做法是设计空间**，这才是 scaling 的地方。
- **砍掉实现 best-of-N**：同一提示词重采样 N 份是浪费；多样性只来自 How。
- **淘汰"多棵树"这个概念**：根节点的多个 How 就是多棵树，跑在不同 worktree 里。
- **How 与拆解不可变**：失败不"改计划"，而是新增一个 How（带理由与拆解），旧的标记
  `不可行/放弃`。因此**不需要破坏性回滚**（取代 ticket 18 的 L6/L7 git reset 设计）。
- **主目录永不切分支**：候选全在 worktree 里做，最后只合并胜出者，集成只发生一次。
- **节点记录区**：每个节点有一份**模型维护、重写式**的文本记录（不是 append 日志），每次
  更新必须带一条理由。它与账本（Harness 写、只追加、永不进模型上下文）严格分开。
  **理由/记录永远不算证据。**

## Selection function (lexicographic)

```
score(候选) = (测试分, 评审分, 优先级 rank, 成本)
```

- **测试分 =（覆盖了规划清单里几个测试点, 这些测试点的通过率）**；**分母是规划清单**，
  不是候选自己写的测试。没有测试 ⇒ 0。
- **测试清单是契约**：**少了不允许**（未覆盖的声明测试点 = 阻塞项）；**多了也异常**——
  计划外的测试不进比分，但作为 **deviation 事件上报给该节点的负责 Agent**，由它决定是
  "计划漏了"（⇒ 新增 How/新计划）还是"实现在凑数"（⇒ 记录并要求修正）。
- **评审分 = 各角度的预定义权重加权聚合**（角度列表与权重都是**预定义**的，例如
  `AC-correctness` 权重最高，`maintainability` 较低）。没有评审 ⇒ 0。
- 打平 ⇒ 按 rank ⇒ 再打平按成本（更省/改动更小）。
- **负分不是落选而是行动项**：任何角度判"可能有问题/肯定有问题" ⇒ 进修复循环（修完再比）。
- **关键角度一票否决**（我加的保险）：预定义的**关键角度**（如 `AC-correctness`、
  `contract-compat`）出现"肯定有问题"时，**不被加权平均稀释**，直接判该候选不可用。
  这与 owner 的权重意图一致，同时避免"低权重角度发现硬伤被平均掉"。

## Prior table

- rank 自带**框架先验**（默认等比衰减，如 0.5 / 0.25 / 0.125），可后续**用盲测数据校准**；
- 传播：`节点可期值 = 自身先验 × 可行子 How 的最大可期值`（不可行的子 How 从乘积剔除）；
- 纪律：**先验只影响"先跑谁"，绝不影响"算不算成功"**；成功只由硬指标决定。
- 预算宽裕时**并行铺开排名靠前的若干个 How**（墙钟是主预算，本地算力便宜）。

## Failure -> manager loop

- How 失败 ⇒ 把**结构化记录**（How 列表、状态、每次失败的证据与理由、剩余未尝试分支）
  交给该节点的负责 Agent；**不给它对话记忆**（审计归数据，不归上下文）。
- 它输出**一次决策 + 理由**（四选一）：`继续下一个 How` / `写一个新 How` /
  `要求对该 How 做可行性评审` / `升级或挂起`。每次决策入账。
- **自动推进的边界**：评审判定该 How **不可行** ⇒ 自动切下一个 How；其余情况**先问负责人**。

## Review angles (predefined closed set, three levels)

| 层 | 评审对象 | 关键角度（否决） | 普通角度（加权） |
| --- | --- | --- | --- |
| How/计划 | 做法可行性 | 约束冲突、依赖可得性 | 与既有架构一致性、成本 |
| 实现 | 代码是否满足验收点 | `AC-correctness`、`contract-compat` | `edge-and-error`、`regression-risk`、`input-safety`、`maintainability` |
| 集成 | 子节点合起来是否成立 | 端到端行为 | 接口对齐、回归 |

- 每个角度的输出模板固定：**要么给出具体反例，要么明确写"该角度未发现反例"**；
- 档级五序数：肯定没问题(+2) / 可能没问题(+1) / 不确定(0) / 可能有问题(−1) / 肯定有问题(−2)；
- `review×N` = N 个**不同角度**的独立会话（同一角度重复 N 次视为浪费，记录为 deviation）。

## Implementation order (each step ships with an adversarial verifier lane)

1. 评审：计数 → **预定义角度 + 权重 + 五档 + 关键角度否决**；
2. **How 轴**：rank/理由/先验、各自拆解、删实现 best-of-N、测试清单前移到规划期；
3. **选择函数**（上面的字典序 + 清单分母 + deviation 上报 + 负分行动项）；
4. **不可变 + 追加 + worktree 分支 + 失败→负责人循环**（替换 L6/L7 破坏性回滚）；
5. 每步盲测 A/B：确认"加 N 有 N 的用途"，且提升的是**已验证的成功**而非虚报。

## Round-1 verification gaps (must be fixed before or with step 1)

An independent adversarial pass on the just-landed covenant found four concrete holes:

1. **The reason check is a keyword substring test** — any 24+ character sentence that
   contains an "activity" word and a "why" word passes, including pure boilerplate and a
   restatement of the goal. A full-leaf probe reached `claimed=True`,
   `status=unverified-success`, `reason_ok=True` on boilerplate. The reason is therefore
   NOT yet the audit artifact the owner asked for.
2. **`best_effort` is a universal escape hatch** — with `best_effort=True` the declared
   `test` floor is not enforced; only a downgrade string is recorded. A planner that sets
   it everywhere converts the covenant into an audit log while claims proceed.
3. **The N reviews are not independent** — the captured ReviewRequests for
   `review_rounds=3` differ only in a reason string: same prompt, same angle. This is the
   owner's point exactly: counting without ANGLES is the wasteful version.
4. **A non-leaf node with code but no file list is not rejected** (the brief required it).

Fixes 1-3 are inseparable from step 1 (review ANGLES with predefined weights and a
critical-angle veto, a substantive reason check, a best-effort cap that flags a diluted
run) and go in the same round; fix 4 is a one-line validation.

## Gap: not yet wired (step 2a → step 2b)

Step 2a landed the How machinery — `harness/how.py` (append-only `How`/`HowList`, the
prior table, viability, the pure `select_key`, the manager loop, `NodeRecord`, and the
candidate-directory copy/abandon/audit functions), the `how_list` envelope (SCHEMAS
26 → 27, ENVELOPE_SCHEMAS §28, KERNEL_API §10), and `PlanNode.how_id` binding — with
tests. It does NOT yet drive real runs:

- `run_node` / `_attempt_internal` in `harness/tree_run.py` still call
  `trajectory.reset_to(...)` (git checkpoints) for L6/L7. **The destructive reset path
  remains until step 2b**, so candidate isolation is NOT in effect for real runs.
- Nothing here is half-wired: no runtime module imports `harness.how`; there is no flag
  or field that would read as "candidates used" while the runner still resets git.
- Step 2b replaces the L6/L7 git-reset design with the candidate-directory path and
  updates the tests that encode the old reset behaviour (`tests/unit/test_v2_tree.py`).

## First usable measurement of the How axis (2026-09-30, reference model, six corpus tasks, N=1)

The axis now genuinely executes (this took four rounds: a nested-envelope sentinel leak, a
decode grammar that marked REQUIRED fields optional, a zero-children decomposition being
treated as a failure instead of a leaf How, and an async manager passed into a sync helper).
Every run planned 2-3 Hows, opened 2-3 candidates (both `leaf-How` and `decomposed-How`),
consulted the manager, and actually executed a leaf.

| task | claimed | actual | quadrant | calls | wall | Hows | manager decisions |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T-02 | F | F | honest-failure | 47 | 485s | 3 | continue → author-new-how → park |
| T-05 | F | F | honest-failure | 25 | 178s | 2 | continue → park |
| T-14 | F | F | honest-failure | 49 | 326s | 2 | continue → park |
| T-20 | T | T | true-success | 14 | 65s | 2 | continue |
| T-31 | F | F | honest-failure | 42 | 299s | 3 | continue → author-new-how → park |
| T-33 | F | F | honest-failure | 54 | 316s | 3 | continue → author-new-how → park |

Totals: actual 1/6, claimed 1/6, **false success 0**, 231 calls, 1670s (mean 278s and ~38
calls per run).

The leaf-only driver on the same tasks (round-11 measurement, N=2) scored 6/12 actual at
~7 calls and ~20s per run. So the How axis currently costs ~5x the calls and ~15x the wall
time and fixes FEWER tasks: the exploration and the extra planning/evaluation calls consume
the budget that the single leaf spends on iterating toward the fix. N=1 is noisy (T-05
passed in the pre-measurement acceptance run), but the cost gap is not noise.

DECISION: the How axis is NOT the default. It stays behind its flag as the right shape for
genuinely multi-part work (which this corpus does not contain) and should be revisited on
tasks that a single leaf measurably cannot do.

Also retracts ticket 18's "the planner never decomposes": that was a grammar artifact (the
decode schema marked REQUIRED fields optional, so an omitted `children` became an empty
list). Decomposition demonstrably happens now.

## The generalisation (five data points)

Mechanisms we built and measured, and what they did to the metrics:

| mechanism | verdict |
| --- | --- |
| knowledge pack injection | no gain (4/15 vs 3/15) |
| module importers in the write spec | no gain (10/15 vs 10/15) |
| forced file ordering | harmful (14/15 vs 7/15) |
| boundary completion on rule evidence | no gain (1/5 vs 1/5) |
| How-axis exploration | works, but 5x cost for fewer actual fixes |

What DID move the numbers was never more structure for the model to follow: it was giving
the model MORE SIGNAL - the forced red-then-green test loop, the deterministic diagnosis
rules, the report gate that stops a process from lying about its own tests, and the
coverage/discrimination checks. Structure that costs calls without adding information
consistently loses. That is the lesson to carry into the next mechanism we consider.
