# Fix wave 1 — head-to-head to N=17 (both arms, same revision 45ebb32, server :8834)

**Status: RUN IN PROGRESS.** This file is the authorized measurement output; checkpoint
lines are appended under *Status log* after every poll / completed seed round. The full
tables, verdict, exact commands and limitations are written here when the run stops
(rule resolves, or N=17/arm is reached, or BEHIND is established).

Pre-registered seed plan: reuse the frozen N=9 data (seeds 1..9, valid on `45ebb32` /
`:8834`) and add seeds 10..17 to BOTH arms, four disjoint lanes per arm per seed, the same
drivers (`bench/v2_measure.py` ours; `bench/pi_baseline.py --reasoning --thinking max` pi,
per-lane temp agent dir). Decision rule unchanged: `M = 3` tasks; `Lo95(Δ) ≥ −M` →
ACHIEVED, `Hi95(Δ) < −M` → BEHIND, else INCONCLUSIVE; task-clustered percentile bootstrap,
seed `20261013`, B=20000.

## Status log

* 2026-10-13T14:01:15+08:00 — no completed round yet; in-flight: seed10:ours2/40,pi3/40.
* 2026-10-13T14:04:13+08:00 — no completed round yet; in-flight: seed10:ours3/40,pi4/40.
* 2026-10-13T14:07:23+08:00 — no completed round yet; in-flight: seed10:ours7/40,pi12/40.
* 2026-10-13T14:10:22+08:00 — no completed round yet; in-flight: seed10:ours10/40,pi15/40.
* 2026-10-13T14:13:20+08:00 — no completed round yet; in-flight: seed10:ours14/40,pi19/40.
* 2026-10-13T14:16:17+08:00 — no completed round yet; in-flight: seed10:ours17/40,pi23/40.
* 2026-10-13T14:19:13+08:00 — no completed round yet; in-flight: seed10:ours19/40,pi25/40.
* 2026-10-13T14:22:10+08:00 — no completed round yet; in-flight: seed10:ours22/40,pi28/40.
* 2026-10-13T14:25:07+08:00 — no completed round yet; in-flight: seed10:ours26/40,pi29/40.
* 2026-10-13T14:28:05+08:00 — no completed round yet; in-flight: seed10:ours26/40,pi31/40.
* 2026-10-13T14:30:37+08:00 — no completed round yet; in-flight: seed10:ours28/40,pi34/40.
* 2026-10-13T14:33:34+08:00 — no completed round yet; in-flight: seed10:ours30/40,pi35/40.
* 2026-10-13T14:36:31+08:00 — no completed round yet; in-flight: seed10:ours32/40,pi39/40.
* 2026-10-13T14:39:27+08:00 — no completed round yet; in-flight: seed10:ours37/40,pi40/40.
* 2026-10-13T14:41:52+08:00 — N=10/arm; ours 250/400 (25.000/40); pi 249/400 (24.900/40); Δ=+0.100; task-clustered 95% CI [-3.500, +3.800]; rule=INCONCLUSIVE (M=3). [Corrected from an earlier line that read "ours 226/360, Δ=+0.211, CI [-3.311,+3.867]": the analyzer's our-seed≥10 path omitted the `/none/` subdir. Fixed at 14:44; seed-10 data itself is intact (ours 40/40, pi 40/40).]
* 2026-10-13T14:42:23+08:00 — seed-10 round clean: ours 40/40 rows, pi 40/40 rows, 0 crashes/timeouts.
* 2026-10-13T14:45:40+08:00 — N=10/arm ours 25.000/40 pi 24.900/40 delta +0.100 CI [-3.500,+3.800] rule=INCONCLUSIVE; in-flight: seed11:ours1/40,pi1/40.
* 2026-10-13T14:48:42+08:00 — N=10/arm ours 25.000/40 pi 24.900/40 delta +0.100 CI [-3.500,+3.800] rule=INCONCLUSIVE; in-flight: seed10:ours40/40,pi40/40 seed11:ours3/40,pi5/40.
* 2026-10-13T14:51:38+08:00 — N=10/arm ours 25.000/40 pi 24.900/40 delta +0.100 CI [-3.500,+3.800] rule=INCONCLUSIVE; in-flight: seed10:ours40/40,pi40/40 seed11:ours4/40,pi6/40.
* 2026-10-13T14:54:53+08:00 — N=10/arm ours 25.000/40 pi 24.900/40 delta +0.100 CI [-3.500,+3.800] rule=INCONCLUSIVE; in-flight: seed10:ours40/40,pi40/40 seed11:ours8/40,pi10/40.
* 2026-10-13T14:58:16+08:00 — N=10/arm ours 25.000/40 pi 24.900/40 delta +0.100 CI [-3.500,+3.800] rule=INCONCLUSIVE; in-flight: seed10:ours40/40,pi40/40 seed11:ours10/40,pi13/40.
* 2026-10-13T15:01:27+08:00 — N=10/arm ours 25.000/40 pi 24.900/40 delta +0.100 CI [-3.500,+3.800] rule=INCONCLUSIVE; in-flight: seed10:ours40/40,pi40/40 seed11:ours14/40,pi15/40.
* 2026-10-13T15:04:24+08:00 — N=10/arm ours 25.000/40 pi 24.900/40 delta +0.100 CI [-3.500,+3.800] rule=INCONCLUSIVE; in-flight: seed10:ours40/40,pi40/40 seed11:ours15/40,pi15/40.
* 2026-10-13T15:08:07+08:00 — N=10/arm ours 25.000/40 pi 24.900/40 delta +0.100 CI [-3.500,+3.800] rule=INCONCLUSIVE; in-flight: seed10:ours40/40,pi40/40 seed11:ours18/40,pi19/40.
* 2026-10-13T15:11:04+08:00 — N=10/arm ours 25.000/40 pi 24.900/40 delta +0.100 CI [-3.500,+3.800] rule=INCONCLUSIVE; in-flight: seed10:ours40/40,pi40/40 seed11:ours20/40,pi22/40.
* 2026-10-13T15:14:00+08:00 — N=10/arm ours 25.000/40 pi 24.900/40 delta +0.100 CI [-3.500,+3.800] rule=INCONCLUSIVE; in-flight: seed10:ours40/40,pi40/40 seed11:ours22/40,pi23/40.
* 2026-10-13T15:38:51+0800 — N=11/arm; ours 274/440 (24.909/40); pi 276/440 (25.091/40); Δ=-0.182; task-clustered 95% CI [-3.636, +3.364]; rule=INCONCLUSIVE (M=3).
* 2026-10-13T16:18:27+0800 — N=12/arm; ours 298/480 (24.833/40); pi 302/480 (25.167/40); Δ=-0.333; task-clustered 95% CI [-3.833, +3.333]; rule=INCONCLUSIVE (M=3).
* 2026-10-13T16:24:32+08:00 — N=12/arm ours 24.833/40 pi 25.167/40 delta -0.333 CI [-3.833,+3.333] rule=INCONCLUSIVE; in-flight: seed10:ours40/40,pi40/40 seed11:ours40/40,pi40/40 seed12:ours40/40,pi40/40 seed13:ours12/40,pi0/40.
* 2026-10-13T16:27:32+08:00 — N=12/arm ours 24.833/40 pi 25.167/40 delta -0.333 CI [-3.833,+3.333] rule=INCONCLUSIVE; in-flight: seed10:ours40/40,pi40/40 seed11:ours40/40,pi40/40 seed12:ours40/40,pi40/40 seed13:ours20/40,pi0/40.
* 2026-10-13T16:56:13+0800 — N=13/arm; ours 325/520 (25.000/40); pi 327/520 (25.154/40); Δ=-0.154; task-clustered 95% CI [-3.462, +3.308]; rule=INCONCLUSIVE (M=3).
* 2026-10-13T17:34:35+0800 — N=14/arm; ours 349/560 (24.929/40); pi 349/560 (24.929/40); Δ=+0.000; task-clustered 95% CI [-3.214, +3.429]; rule=INCONCLUSIVE (M=3).
* 2026-10-13T18:16:07+0800 — N=15/arm; ours 373/600 (24.867/40); pi 376/600 (25.067/40); Δ=-0.200; task-clustered 95% CI [-3.467, +3.267]; rule=INCONCLUSIVE (M=3).
* 2026-10-13T19:07:16+0800 — N=16/arm; ours 399/640 (24.938/40); pi 402/640 (25.125/40); Δ=-0.188; task-clustered 95% CI [-3.312, +3.125]; rule=INCONCLUSIVE (M=3).
* 2026-10-13T19:52:21+0800 — N=17/arm; ours 423/680 (24.882/40); pi 428/680 (25.176/40); Δ=-0.294; task-clustered 95% CI [-3.471, +3.059]; rule=INCONCLUSIVE (M=3).
