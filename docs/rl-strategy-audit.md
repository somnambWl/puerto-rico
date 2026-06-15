# RL Strategy Audit — Puerto Rico

Games per line-up: **200** (seed 0). RL checkpoint: `runs/release/final.pt` (loaded).

Each agent type is audited in an all-same-type 4-player line-up (4xRL self-play / 4xHeuristic / 4xRandom), seats rotated so seat asymmetry averages out. Metrics for an agent are computed over the seats *it* drives, with extra focus on WINNERS.

## 1. Outcome (winners)

| agent | winner mean VP | winner shipping VP (chips) | winner goods shipped |
| --- | --- | --- | --- |
| RL | 42.6 | 29.5 | 24.0 |
| Heuristic | 43.9 | 30.8 | 29.4 |
| Random | 35.8 | 20.4 | 17.9 |

- RL winner VP distribution: min 34, median 42, max 53 (n=200).
- Heuristic winner VP distribution: min 35, median 43, max 68 (n=200).
- Random winner VP distribution: min 16, median 35, max 58 (n=200).

## 2. Win rate by seat (first-player disadvantage check)

Puerto Rico has a known FIRST-PLAYER DISADVANTAGE (seat 0 starts with indigo, the last seat with corn). In an all-same-type line-up every seat is played by the same policy, so a large seat-0 skew points at the engine/strategy, not at a stronger opponent.

| agent | seat 0 | seat 1 | seat 2 | seat 3 |
| --- | --- | --- | --- | --- |
| RL | 20.0% | 22.5% | 28.0% | 29.5% |
| Heuristic | 26.5% | 19.0% | 32.0% | 22.5% |
| Random | 13.5% | 20.0% | 34.0% | 32.5% |

## 3. Role-pick distribution by game-third

Strong play: Trader/Prospector early, Builder when cash-rich, Captain when holding goods, Craftsman mostly by the dominant producer.

### RL

| third | SETTLER | MAYOR | BUILDER | CRAFTSMAN | TRADER | CAPTAIN | PROSPECTOR |
| --- | --- | --- | --- | --- | --- | --- | --- |
| early | 17.9% | 15.3% | 16.2% | 12.4% | 9.9% | 12.8% | 15.6% |
| mid | 19.9% | 14.4% | 11.3% | 12.8% | 10.2% | 16.1% | 15.2% |
| late | 13.1% | 14.4% | 10.7% | 13.0% | 11.8% | 20.4% | 16.5% |

### Heuristic

| third | SETTLER | MAYOR | BUILDER | CRAFTSMAN | TRADER | CAPTAIN | PROSPECTOR |
| --- | --- | --- | --- | --- | --- | --- | --- |
| early | 23.9% | 19.9% | 15.0% | 14.5% | 7.4% | 9.8% | 9.6% |
| mid | 15.3% | 17.7% | 12.3% | 22.3% | 10.0% | 14.7% | 7.7% |
| late | 10.8% | 14.1% | 13.8% | 25.0% | 10.3% | 19.0% | 7.0% |

### Random

| third | SETTLER | MAYOR | BUILDER | CRAFTSMAN | TRADER | CAPTAIN | PROSPECTOR |
| --- | --- | --- | --- | --- | --- | --- | --- |
| early | 14.3% | 13.8% | 14.8% | 14.2% | 14.3% | 14.5% | 14.1% |
| mid | 14.3% | 14.2% | 14.2% | 14.3% | 14.1% | 14.3% | 14.6% |
| late | 14.1% | 14.9% | 13.8% | 14.0% | 14.4% | 14.3% | 14.6% |

## 4. Large-building ownership of WINNERS

Guild Hall is generally rated the best large building. Strong play tends to land at least one large building.

| agent | winners w/ >=1 large | winners w/ Guild Hall |
| --- | --- | --- |
| RL | 77.5% | 0.0% |
| Heuristic | 26.0% | 5.5% |
| Random | 45.5% | 14.5% |

## 5. Key building build-rates (per seat played)

Each building has supply **1** in the 4-player base game, so the rate is computed per seat-occurrence and **ceils at 25%** (= built by exactly one of the four players every game). Read ~25% as *always built (by someone)* and ~0% as *almost never built*.

**Strong / most-built buildings:**

| agent | harbor | wharf | factory | small market |
| --- | --- | --- | --- | --- |
| RL | 25.0% | 0.4% | 4.1% | 16.5% |
| Heuristic | 22.5% | 2.0% | 24.9% | 25.0% |
| Random | 12.6% | 7.5% | 18.1% | 25.0% |

**Trap / weak buildings (high rate is a bad sign):**

| agent | large warehouse | hospice | university | office |
| --- | --- | --- | --- | --- |
| RL | 0.6% | 25.0% | 3.9% | 0.1% |
| Heuristic | 17.8% | 25.0% | 11.8% | 24.9% |
| Random | 21.1% | 24.5% | 13.9% | 23.1% |

## 6. Unmanned-building rounds (wasted manning)

Mean free colonist circles across owned production+large buildings (measured at each Mayor-phase end). Strong play -> near zero.

| agent | mean unmanned circles |
| --- | --- |
| RL | 0.49 |
| Heuristic | 0.73 |
| Random | 0.85 |

## 7. Production-chain mismatches

Mean count (at game end) of manned production buildings with no manned matching plantation, plus manned plantations with no matching building (corn excluded). Strong play -> low.

| agent | mean chain mismatch |
| --- | --- |
| RL | 0.66 |
| Heuristic | 0.48 |
| Random | 1.81 |

## 8. Corn timing

Mean game-fraction at which corn plantations are acquired, and the all-corn-no-engine rate (ships corn but never builds Harbor/Wharf/large).

| agent | mean corn-acquire frac | all-corn-no-engine rate |
| --- | --- | --- |
| RL | 0.30 | 14.1% |
| Heuristic | 0.31 | 46.2% |
| Random | 0.35 | 49.1% |

## 9. Empty build phases

Rate at which the agent PASSes on its builder turn while it could afford >=1 building. Strong play -> low.

| agent | empty-build pass rate |
| --- | --- |
| RL | 55.3% |
| Heuristic | 0.0% |
| Random | 24.6% |

## 10. Shipping behavior

| agent | ships at all | mean first-ship decision idx (lower=earlier) |
| --- | --- | --- |
| RL | 100.0% | 38 |
| Heuristic | 100.0% | 83 |
| Random | 99.2% | 149 |

## RL vs 3x Heuristic (head-to-head)

- RL win rate vs 3 Heuristic: **90.5%** (chance = 25%).
- RL winner mean VP: 49.7; mean unmanned: 1.01; empty-build pass rate: 34.1%.

## VERDICT — strong-play signatures

| strong-play signature | verdict | evidence |
| --- | --- | --- |
| No first-player over-win | ✅ | seat0 20.0% vs others ~26.7% |
| Winners build large buildings | ✅ | 77.5% of winners |
| Uses Guild Hall (best large) | ❌ | 0.0% of winners |
| Builds shipping engine (Harbor/Wharf) | ✅ | Harbor 25.0%, Wharf 0.4% (max=25%) |
| Avoids trap buildings | ✅ | vs Random, worst excess 0.5% (hospice) |
| Mans its buildings | ✅ | 0.49 mean free circles |
| Coherent production chains | ⚠️ | 0.66 mean mismatch |
| Not all-corn-no-engine | ⚠️ | 14.1% |
| Builds when affordable | ❌ | 55.3% pass rate |
| Ships goods for VP | ✅ | 100.0% ship at all |

### Apparent RL strategy

Most-picked roles overall: SETTLER (2342), CAPTAIN (2231), PROSPECTOR (2162), MAYOR (2020). Winner mean VP 42.6 (shipping-VP component 29.5). Heuristic winner mean VP for reference: 43.9.

### Concrete weaknesses + improvement levers

- Almost never builds Guild Hall (0.0% of winners). Lever: encourage big-building lines via reward shaping or opponent curricula.
- Passes on affordable builds 55.3% of the time. Lever: tempo/build-progress reward.
