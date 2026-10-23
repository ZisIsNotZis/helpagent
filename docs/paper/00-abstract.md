# Abstract

A coding harness is a bet that a program wrapped around a language model buys capability the same model driving a free-form CLI does not have, and this paper reports one campaign that tried to settle the bet and could not.
The conditions are fixed and narrow: one quantised `4B` model on llama.cpp, one corpus of `40` seeded tasks, one blind external grader that never enters the run loop, and a decision rule written down before the data were read.
The result is three verdicts and no victory.
Capability parity against a mature agent CLI is **INCONCLUSIVE** at the pre-registered margin — a paired difference of `-0.320` tasks with a `95`% task-clustered interval of `[-3.520, +3.080]` — and the interval's width is set by task heterogeneity, so more seeds would not have resolved it.
The verification ladder is **partly** informative and costs about twice the baseline's tokens: a claim gate buys honesty, and the correctness contrasts are mostly unresolved.
The harness's tree-of-children bundle is **NEGATIVE** on this corpus, fixing `47/70` runs as a monolithic leaf against `14/70` as a tree, while costing `2.2` to `2.4` times the calls.
The methodological contribution is the protocol plus the losing half of the record: nine plausible designs that measured worse, three claims withdrawn with the reason each died, and the boundary inside which every number holds.
Every decisive number re-derives from the repository alone with one command, `python3 reproduce.py`, from committed rows, with no model, no network and no campaign archive; §8 states how that path fails loudly when its input is starved, because a reproduction that reports parity after reading an empty directory is worse than none.
Nothing here describes a tool anyone can run: the product CLI the research was for was never built.
