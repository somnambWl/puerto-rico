# RL Strategy Audit — Puerto Rico

Games per line-up: **200** (seed 0). RL checkpoint: `runs/release/final.pt` (loaded).

Each agent type is audited in an all-same-type 4-player line-up (4xRL self-play / 4xHeuristic / 4xRandom), seats rotated so seat asymmetry averages out. Metrics for an agent are computed over the seats *it* drives, with extra focus on WINNERS.

## 1. Outcome (winners)

| agent | winner mean VP | winner shipping VP (chips) | winner goods shipped |
| --- | --- | --- | --- |
| RL | 53.9 | 23.8 | 21.9 |
| Heuristic | 38.5 | 26.9 | 24.5 |
| Random | 33.5 | 19.6 | 17.3 |

- RL winner VP distribution: min 36, median 53, max 79 (n=200).
- Heuristic winner VP distribution: min 23, median 39, max 50 (n=200).
- Random winner VP distribution: min 16, median 33, max 60 (n=200).

## 2. Win rate by seat (first-player disadvantage check)

Puerto Rico has a known FIRST-PLAYER DISADVANTAGE (seat 0 starts with indigo, the last seat with corn). In an all-same-type line-up every seat is played by the same policy, so a large seat-0 skew points at the engine/strategy, not at a stronger opponent.

| agent | seat 0 | seat 1 | seat 2 | seat 3 |
| --- | --- | --- | --- | --- |
| RL | 45.5% | 40.0% | 13.0% | 1.5% |
| Heuristic | 23.0% | 8.0% | 42.0% | 27.0% |
| Random | 19.0% | 18.0% | 29.0% | 34.0% |

## 3. Role-pick distribution by game-third

Strong play: Trader/Prospector early, Builder when cash-rich, Captain when holding goods, Craftsman mostly by the dominant producer.

### RL

| third | SETTLER | MAYOR | BUILDER | CRAFTSMAN | TRADER | CAPTAIN | PROSPECTOR |
| --- | --- | --- | --- | --- | --- | --- | --- |
| early | 20.1% | 16.4% | 16.4% | 12.0% | 9.3% | 9.2% | 16.5% |
| mid | 12.3% | 15.8% | 13.4% | 11.8% | 16.3% | 14.3% | 16.0% |
| late | 8.8% | 12.7% | 15.5% | 13.0% | 10.9% | 19.7% | 19.3% |

### Heuristic

| third | SETTLER | MAYOR | BUILDER | CRAFTSMAN | TRADER | CAPTAIN | PROSPECTOR |
| --- | --- | --- | --- | --- | --- | --- | --- |
| early | 24.9% | 19.8% | 15.3% | 14.4% | 6.7% | 9.4% | 9.6% |
| mid | 14.2% | 18.1% | 14.1% | 21.7% | 10.6% | 13.6% | 7.8% |
| late | 11.9% | 16.6% | 12.3% | 25.0% | 10.0% | 16.5% | 7.8% |

### Random

| third | SETTLER | MAYOR | BUILDER | CRAFTSMAN | TRADER | CAPTAIN | PROSPECTOR |
| --- | --- | --- | --- | --- | --- | --- | --- |
| early | 14.5% | 13.4% | 14.3% | 14.3% | 14.7% | 14.4% | 14.3% |
| mid | 14.1% | 15.0% | 14.2% | 14.2% | 14.3% | 14.1% | 14.1% |
| late | 13.8% | 14.6% | 14.2% | 14.1% | 13.9% | 14.4% | 14.9% |

## 4. Large-building ownership of WINNERS

Guild Hall is generally rated the best large building. Strong play tends to land at least one large building.

| agent | winners w/ >=1 large | winners w/ Guild Hall |
| --- | --- | --- |
| RL | 99.5% | 41.0% |
| Heuristic | 0.0% | 0.0% |
| Random | 20.0% | 3.5% |

## 5. Key building build-rates (per seat played)

Each building has supply **1** in the 4-player base game, so the rate is computed per seat-occurrence and **ceils at 25%** (= built by exactly one of the four players every game). Read ~25% as *always built (by someone)* and ~0% as *almost never built*.

**Strong / most-built buildings:**

| agent | harbor | wharf | factory | small market |
| --- | --- | --- | --- | --- |
| RL | 18.0% | 0.0% | 50.0% | 50.0% |
| Heuristic | 6.4% | 0.0% | 23.6% | 50.0% |
| Random | 8.2% | 5.5% | 13.2% | 49.9% |

**Trap / weak buildings (high rate is a bad sign):**

| agent | large warehouse | hospice | university | office |
| --- | --- | --- | --- | --- |
| RL | 0.4% | 50.0% | 1.5% | 0.0% |
| Heuristic | 0.0% | 27.4% | 0.0% | 34.5% |
| Random | 17.8% | 39.6% | 9.4% | 29.6% |

## 6. Unmanned-building rounds (wasted manning)

Mean free colonist circles across owned production+large buildings (measured at each Mayor-phase end). Strong play -> near zero.

| agent | mean unmanned circles |
| --- | --- |
| RL | 0.68 |
| Heuristic | 0.99 |
| Random | 0.89 |

## 7. Production-chain mismatches

Mean count (at game end) of manned production buildings with no manned matching plantation, plus manned plantations with no matching building (corn excluded). Strong play -> low.

| agent | mean chain mismatch |
| --- | --- |
| RL | 1.43 |
| Heuristic | 0.19 |
| Random | 1.70 |

## 8. Corn timing

Mean game-fraction at which corn plantations are acquired, and the all-corn-no-engine rate (ships corn but never builds Harbor/Wharf/large).

| agent | mean corn-acquire frac | all-corn-no-engine rate |
| --- | --- | --- |
| RL | 0.30 | 9.0% |
| Heuristic | 0.26 | 66.1% |
| Random | 0.35 | 65.0% |

## 9. Empty build phases

Rate at which the agent PASSes on its builder turn while it could afford >=1 building. Strong play -> low.

| agent | empty-build pass rate |
| --- | --- |
| RL | 22.0% |
| Heuristic | 0.0% |
| Random | 21.6% |

## 10. Shipping behavior

| agent | ships at all | mean first-ship decision idx (lower=earlier) |
| --- | --- | --- |
| RL | 100.0% | 89 |
| Heuristic | 100.0% | 77 |
| Random | 99.1% | 146 |

## RL vs 3x Heuristic (head-to-head)

- RL win rate vs 3 Heuristic: **98.5%** (chance = 25%).
- RL winner mean VP: 49.3; mean unmanned: 0.19; empty-build pass rate: 8.5%.

## VERDICT — strong-play signatures

| strong-play signature | verdict | evidence |
| --- | --- | --- |
| No first-player over-win | ❌ | seat0 45.5% vs others ~18.2% — seat-0 OVER-WINS |
| Winners build large buildings | ✅ | 99.5% of winners |
| Uses Guild Hall (best large) | ✅ | 41.0% of winners |
| Builds shipping engine (Harbor/Wharf) | ✅ | Harbor 18.0%, Wharf 0.0% (max=25%) |
| Avoids trap buildings | ❌ | vs Random, worst excess 10.4% (hospice) |
| Mans its buildings | ⚠️ | 0.68 mean free circles |
| Coherent production chains | ⚠️ | 1.43 mean mismatch |
| Not all-corn-no-engine | ✅ | 9.0% |
| Builds when affordable | ⚠️ | 22.0% pass rate |
| Ships goods for VP | ✅ | 100.0% ship at all |

### Apparent RL strategy

Most-picked roles overall: PROSPECTOR (2446), BUILDER (2150), MAYOR (2135), CAPTAIN (2014). Winner mean VP 53.9 (shipping-VP component 23.8). Heuristic winner mean VP for reference: 38.5.

### Concrete weaknesses + improvement levers

- Over-wins from seat 0 (45.5% vs ~18.2%): the policy exploits seat asymmetry. Lever: stronger seat balancing / seat-aware reward normalization in self-play.
- Builds trap building 'hospice' 50.0% vs Random 39.6%. Lever: these add little; better lines exist.
