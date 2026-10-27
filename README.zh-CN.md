[English](README.md) | **简体中文**

<img src="assets/logo.svg" alt="helpagent" width="200">

# helpagent

### 一个包在小模型（4B，本地运行）外面的编码 harness，被一路测到预注册的终点 —— 连失败的那一半记录也留着。

**它用一个问题替代了一场演示：把模型套进一个程序里，得到的编码能力，真的比让同一个模型漫无目的地驱动 CLI 更强吗？这里测出的答案是「没有确立，而且按现在这种做法大概不成立」—— 并且每一个决定性数字，至今仍能用仓库里的一条命令离线复算出来。**

> **状态：已归档的研究。** 这场实验按预注册的终点跑完了。三个目标既没有被证实，也没有被证伪；
> 它本来要指向的产品并不存在。它真正的产出是一套测量协议、三个结论，以及一批被撤回的说法 ——
> 如今写成了一篇论文，一个人不跑模型也能读懂、能核对。

## 1. 结果在这里

| 内容 | 位置 |
| --- | --- |
| 整场实验作为一篇论文：摘要、协议、三个结论、负面结果、边界、数字附录 | [`docs/paper/preprint.md`](docs/paper/preprint.md) |
| 每一个决定性数字、它的出处，以及重新推出它的那条命令 | `python3 reproduce.py`，再看 [`docs/paper/numbers.md`](docs/paper/numbers.md) |
| 三个结论，以及它们承载不了的东西 | [`docs/2_GOAL.md`](docs/2_GOAL.md) |
| harness 的设计与它唯一的那条流程 | [`docs/6_ARCHITECTURE.md`](docs/6_ARCHITECTURE.md) |
| 试过什么、输在哪里，都带数字 | [`docs/8_DETAIL.md`](docs/8_DETAIL.md) |
| 工作顺序，以及什么被刻意排除在顺序之外 | [`docs/0_ROADMAP.md`](docs/0_ROADMAP.md) |

三个结论，各用一句话说完：与成熟 CLI 的能力对等是 **INCONCLUSIVE**（在预注册的判决边界下）——
双方分别是 `24.640/40` 与 `24.960/40` 个任务，配对差 `−0.320`，按任务聚类的 95% 区间
`[−3.520, +3.080]`；验证环节 **只有部分信息量，且与原本的说法不符**，代价约为基线的两倍 token；
树状分解（一个父节点带若干子节点）是 **NEGATIVE** —— 修复 `14/70` 次运行，而单纯的 leaf 是 `47/70`。

## 2. 快速开始

```sh
git clone https://github.com/ZisIsNotZis/helpagent && cd helpagent
python3 reproduce.py                    # 每个决定性数字，只读已提交的数据行
python3 docs/paper/check_citations.py   # 论文引用的还是这些数字：0 处未解析
```

不用安装、不用模型、不联网、也不需要那 2 GB 的 campaign 归档 —— 入口读取的是
`bench/projection/`（约半兆，已入库），输入缺失或一行数据都没有时会直接报错停下。
只想读论文的话什么依赖都不用：[`docs/paper/preprint.md`](docs/paper/preprint.md)。

## 3. 它做什么

harness 本身是一个确定性程序；模型只是一个受契约约束的兜底节点。每一次模型调用都是带类型输入、
带类型输出的一步，只用在确定性代码确实做不了的地方。它周围那条流程 —— 计划、实现、测试、评审、
声明 —— 是带预算的普通代码，凡是能算出来的事实都由确定性检查负责
（[`docs/1_PROBLEM.md`](docs/1_PROBLEM.md)）。

一次运行从一个任务（一个 `request.md` 和一个坏掉的 `repo/`）开始：先做计划，长成一个带排序方案
的小节点结构，再是实现，以及一个必须先失败的测试；然后是独立编写的测试和被评分的评审；最后是唯一
的声明闸门，它决定这次运行能不能宣称任务已修好，并记录是哪条证据支撑了这次声明。

盲评协议才是重点，也正是这些数字值得一读的原因：

- **评分方的测试永远不进运行。** 每个任务自带的隐藏测试在运行结束后，在一份干净的副本上给结果
  打分（[`bench/external_score.py`](bench/external_score.py)）。
- **运行方对自己成绩单能做的一切，要么被拒绝、要么被还原**，并且这次尝试会被记录下来：评分方
  拥有的路径会被重置，靠 `sys.path` 遮蔽模块的文件永远不会被应用。
- **证据是一份机器可读的 pytest 报告**，放在私有路径上，带每次运行独有的 canary 和预期的测试
  id。退出码从不作为证据。
- **只有一个声明闸门。** 有且只有一个函数能授予声明（`harness/leaf.py::claim_decision`），
  一旦存在别的路径能产出声明，一条结构性测试就会让测试套失败。

## 4. 现在已经能跑的部分

- **闸门** —— 单元、契约、语料完整性、防篡改四类测试；不需要模型。
- **单个任务端到端** —— leaf 流程，证据链落盘（`bench/v2_leaf.py`）。
- **盲扫** —— 运行自称的结果 vs 外部评分方实际给出的结果，带表格与轨迹
  （`bench/v2_sweep.py`、`bench/external_score.py`）。
- **树状驱动** —— 那个被实验测出来、并被否掉的父子节点方案（`bench/v2_tree.py`）。
- **`pi` 基线臂** —— 同一个模型上跑成熟 CLI，用于正面对比（`bench/pi_baseline.py`）。
- **离线复现** —— `reproduce.py` 重算论文里的数字，遇到它不会打印的键就直接拒绝；
  `bench/checks/m1_acceptance.py` 把验收写成退出码；`bench/checks/docs_layout.py` 保证 `docs/`
  仍然按层级归档。

## 5. 架构

两半，从不共用同一个进程：干活的 harness，和打分的外部评分器。harness（`harness/`）是内核和流程
—— envelope、leaf 循环、声明闸门、节点树、预算、账本与验证记录。驱动（`bench/`）负责运行 harness、
给结果打分并把数字压缩成表格：单任务、盲扫、树、基线、外部评分器，以及复现入口读取的那份 projection。
模型只能通过一个由 envelope 约束的接口说话（`harness/model.py`），而让两个实验臂具备可比性的那
条公平前提写在 [`docs/6_ARCHITECTURE.md#fair-comparison-precondition`](docs/6_ARCHITECTURE.md#fair-comparison-precondition)。

```
.
├── harness/          内核与流程：envelope、leaf 循环、声明闸门、树、预算、账本
├── bench/
│   ├── corpus/       T-01..T-35：request.md、坏掉的 repo/、checks.py、solution.md
│   ├── anchor/       A-01..A-05，五个锚点任务
│   ├── v2_*.py       驱动：leaf、tree、sweep、measure
│   ├── external_score.py, pi_baseline.py   盲评分器与基线臂
│   ├── projection/   reproduce.py 读取的、已入库的数据行
│   └── runs/evidence/  挑选并入库的证据；bench/runs/wave1/（2.0 GB）不入库，按哈希校验
├── tests/            闸门：内核不变量、流程规则、语料完整性、防篡改
├── docs/             当前事实：第 1..9 层，外加 docs/paper/ 里的预印本
├── .scratch/         背后的工作记录 —— 是叙述，不是事实
└── reproduce.py      每个决定性数字，离线复算
```

`docs/` 是当前事实；`.scratch/` 是产出它的过程；两者冲突时以 `docs/` 为准。

## 6. 开发

需要 Python 3.12+ 和 [`uv`](https://docs.astral.sh/uv/)；依赖全部来自 PyPI。

```sh
uv sync                              # 安装开发依赖，依据 uv.lock
uv run pytest -q -p no:warnings      # 闸门：单元 + 契约，不需要模型，<10 秒
python3 reproduce.py                 # 数字仍然复算得出
python3 docs/paper/check_citations.py
```

真正跑一个任务需要一个本地 llama.cpp 服务；先启动它、确认 `/health`，再驱动单个任务：

```sh
uv run python bench/v2_leaf.py --task bench/corpus/T-02-off-by-one \
  --server http://127.0.0.1:8834 --calls 24 --deadline-hours 0.25
```

服务端参数、盲扫驱动、语料契约，以及如何新增一个任务，都在
[`docs/9_IMPLEMENTATION.md`](docs/9_IMPLEMENTATION.md)。

## 7. 参与

见 [`CONTRIBUTING.md`](CONTRIBUTING.md)：这是一个已归档的 harness，因此只有「让已经发表的结果仍然
可核对」的改动才值得做 —— 闸门保持绿的，论文的数字保持可复算。任何改动都必须守住的那几条规则在
[`docs/3_REQUIREMENT.md`](docs/3_REQUIREMENT.md)。

## 8. 路线图

**已完成** —— M0：campaign 的原始数据被安置在一个声明过的位置并按哈希校验（`53 270` 个文件、
`1 996 009 173` 字节，`bench/manifests/wave1.sha256`）。M1：一篇可引用的预印本，其中每个决定性
数字都能只靠本仓库复算，验收本身就是退出码。V1：一个任务、确实修好，并带着它的证据。V2：诚实的
成绩单。

**没做，也不在这里计划** —— V3（零虚假成功）最终停在 `2.20%`，不是零。V4（以更低成本打赢成熟
CLI）得到了一个不利的答案：对等结论是 INCONCLUSIVE，token 约为对方的 `2x`。V5 和 V6 —— 那个能
指向你自己仓库的产品命令 —— 从未尝试。harness 的修复工作和受控的 M2 评估，仍冻结在上一轮留下的
位置，没有授权给 root 以下的任何节点（[`docs/0_ROADMAP.md`](docs/0_ROADMAP.md)）。

未来的研究计划需要什么，这里只陈述、不承诺：一个在统计上有能力判定对等的语料；一个配对的任务内
设计；一条改进提示词的基线臂；以及一次干净的单通道墙钟时间对比。这个仓库里没有任何东西在等一个
工作者。

## 9. 许可证

[`LICENSE.md`](LICENSE.md) —— GNU AGPL-3.0。Copyright (C) ZisIsNotZis。
