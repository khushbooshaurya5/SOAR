# Production rules — every rule explained

The agent's knowledge is 52 hand-written Soar productions in four files
(`soar/*.soar`), plus the chunks Soar learns for itself at run time.
Naming convention: `problem-space*function*operator*detail`, where the
function is one of

| function | PSCM role | support |
|---|---|---|
| `elaborate` | state elaboration: derive facts from what is in working memory | i-support (retracts when its conditions stop matching) |
| `propose` | operator proposal: create an *acceptable* preference (`+`) | i-support |
| `compare` | operator selection: create better/indifferent preferences | i-support |
| `apply` | operator application: change working memory / issue commands | o-support (persists) |

Reading a rule: everything before `-->` must match working memory;
`<x>` is a variable; `-` in front of a condition means "must be absent".

---

## 1. `cost-model.soar` — what "effort" means for this user (17 rules)

All elaborations. Together they turn perception (`terrain`, `crowd`,
`profile`) into one number per cell, `^enter-cost`, or into
`^impassable`. Because they are i-supported, a change on the input-link
re-derives the affected costs with no extra code.

| # | rule | what it does | why |
|---|---|---|---|
| 1 | `cost*elaborate*profile` | copies `io.input-link.user.profile` to `(<s> ^profile …)` | short handle for the other rules |
| 2 | `cost*elaborate*crowd-weight*standard` | `^crowd-weight 1` | a walking adult is slowed a little by a crowd |
| 3 | `cost*elaborate*crowd-weight*wheelchair` | `^crowd-weight 2` | needs clear floor width to manoeuvre |
| 4 | `cost*elaborate*crowd-weight*low-vision` | `^crowd-weight 2` | dense crowds remove orientation cues |
| 5 | `cost*elaborate*cell-model` | gives every perceived cell `<c>` a private `^model <k>` object | keeps the agent's interpretation separate from raw perception, and lets rules reach a cell's cost in one hop (see "rete lesson" in the README) |
| 6 | `cost*elaborate*base-cost*level` | floor, tactile, open, autodoor, narrow → `^base-cost 1` | level ground costs one unit |
| 7 | `cost*elaborate*base-cost*effortful` | door, ramp, stairs → `^base-cost 2` | physically harder for everybody |
| 8 | `cost*elaborate*crowd-cost` | `^crowd-cost = crowd-weight × crowd level` | crowd avoidance as a graded cost |
| 9 | `access*wheelchair*stairs-impassable` | stairs → `^impassable stairs` | hard constraint, not a preference |
| 10 | `access*wheelchair*narrow-impassable` | narrow passage → `^impassable too-narrow` | chair does not fit |
| 11 | `access*wheelchair*manual-door-penalty` | manual door → `^access-penalty 3` | possible but awkward; take an automatic door if the detour is short |
| 12 | `access*low-vision*open-space-penalty` | open atrium → `^access-penalty 4` | no walls to follow |
| 13 | `access*low-vision*stairs-penalty` | stairs → `^access-penalty 2` | fall hazard |
| 14 | `access*low-vision*unguided-floor-penalty` | plain floor → `^access-penalty 1` | makes tactile paving the preferred surface |
| 15 | `obstacle*elaborate*remembered-obstacle-impassable` | a cell in `^memory.blocked` → `^impassable obstacle` | connects the agent's obstacle *beliefs* to the cost model |
| 16 | `cost*elaborate*enter-cost*no-penalty` | `enter-cost = base + crowd` when there is no penalty and the cell is not impassable | total cost |
| 17 | `cost*elaborate*enter-cost*with-penalty` | `enter-cost = base + crowd + penalty` when not impassable | Soar has no default values, hence two variants |

An impassable cell has **no** `^enter-cost`, so the planner and the move
proposal — which both require one — simply never consider it.

## 2. `navigate.soar` — top-level problem space (19 rules)

| # | rule | what it does | why |
|---|---|---|---|
| 18 | `navigate*propose*init-navigate` | proposes `init-navigate` on the unnamed top state | first decision of every episode |
| 19 | `navigate*apply*init-navigate` | adds `^name navigate ^heading none ^memory <m>` | sets up the persistent (o-supported) state structures |
| 20 | `navigate*elaborate*at-goal` | `^at-goal true` when agent cell = goal cell | goal test |
| 21 | `navigate*compare*priority` | for two proposed operators with different `^priority`, prefers the higher (`>`) | one generic rule orders the operator *types*: finish 6 > report 5 > record-obstacle 4 > replan 3 > plan-route 2 > move 1 |
| 22 | `navigate*propose*finish` | proposes `finish` when at the goal | |
| 23 | `navigate*apply*finish` | puts `^arrived` on the output-link | tells the environment the task is done |
| 24 | `navigate*propose*report-unreachable` | proposes it when the plan's status is `unreachable` | honesty: say that no accessible route exists |
| 25 | `navigate*apply*report-unreachable` | output `^stop.reason no-accessible-route` | |
| 26 | `navigate*propose*record-obstacle` | for a perceived obstacle not yet in memory; `+ =` (several are indifferent) | obstacle avoidance step 1: notice |
| 27 | `navigate*apply*record-obstacle` | adds `(<m> ^blocked <cell>)` | o-supported belief: survives after the percept is gone |
| 28 | `navigate*apply*record-obstacle*invalidate-plan` | removes `^plan` | the plan was made without this knowledge |
| 29 | `navigate*propose*replan` | when the finished plan's `^epoch` ≠ current `^crowd-epoch` | crowd picture changed → costs are stale |
| 30 | `navigate*apply*replan` | removes `^plan` | |
| 31 | `navigate*propose*plan-route` | when not at goal and there is no finished (`complete`/`unreachable`) plan | **abstract operator**: nothing applies it here → operator no-change impasse → substate |
| 32 | `navigate*propose*move` | one `move` per adjacent cell that is labelled by the plan and has an `^enter-cost`; computes `^value = enter-cost + dist` | obstacle avoidance step 2: walls, blocked and inaccessible cells are never proposed |
| 33 | `navigate*compare*move*cheaper-route` | lower `^value` is better (`>`) | **route selection**; equal values produce *no* preference → tie impasse |
| 34 | `navigate*apply*move` | output `^move.dir <d>` | motor command |
| 35 | `navigate*apply*move*update-heading` | replaces `^heading` with the move direction | remembered for the keep-heading criterion |
| 36 | `navigate*apply*remove-completed-command` | removes output commands marked `^status complete` | output-link housekeeping |

## 3. `plan-route.soar` — substate for the operator no-change impasse (10 rules)

Uniform-cost search backwards from the goal. The frontier is the set of
proposed `label` operators; Soar's decision procedure is the priority
queue.

| # | rule | what it does | why |
|---|---|---|---|
| 37 | `plan-route*elaborate*substate` | names the substate `plan-route`; `(dont-learn <s>)` | recognise *why* the impasse happened; switch chunking off here (see below) |
| 38 | `plan-route*propose*init-plan` | when the superstate has no `^plan` | |
| 39 | `plan-route*apply*init-plan` | creates `^plan` on the **superstate** with `^status building`, the current `^epoch` and the goal label `^dist 0` | results live in the superstate so they survive the substate |
| 40 | `plan-route*propose*label` | for an unlabelled enterable cell `c` beside a labelled cell `n`: `label c` with `^dist = dist(n) + enter-cost(n)`; `+ =` | frontier expansion |
| 41 | `plan-route*compare*label*cheapest-first` | smaller `^dist` is better | makes it Dijkstra |
| 42 | `plan-route*apply*label` | adds `(<p> ^label <l>)(<l> ^cell ^dist ^via)` | the label becomes permanent |
| 43 | `plan-route*propose*complete-plan` | when the agent's own cell is labelled; best (`>`) | early stop: every cell on a cheapest route is already labelled |
| 44 | `plan-route*apply*complete-plan` | status `building` → `complete` | retracts `plan-route` in the superstate → impasse resolved → substate removed |
| 45 | `plan-route*propose*fail-plan` | always while building, with a **worst** preference (`<`) | only selected when no label can be proposed: frontier exhausted |
| 46 | `plan-route*apply*fail-plan` | status → `unreachable` | |

**Why no chunking here.** Chunking backtraces through the rules that
*created* a result, not through the better-preferences that decided which
operator was selected. A chunk from this substate would read "label any
frontier cell from any labelled neighbour" without "…if it is the
cheapest", and would write wrong distances. This is the textbook
over-general-chunk problem, so learning is disabled for this substate
(`chunk except` + `dont-learn`).

## 4. `tie-break.soar` — substate for the operator tie impasse (6 rules)

| # | rule | what it does | why |
|---|---|---|---|
| 47 | `tie-break*elaborate*substate` | names the substate when the impasse is a tie in `navigate` | fires once per impasse → its firing count *is* the impasse count |
| 48 | `tie-break*propose*prefer*less-crowded` | items `a`,`b` with equal `^value`; `a`'s cell is less crowded | criterion 1: comfort/safety |
| 49 | `tie-break*propose*prefer*keep-heading` | equal crowd; only `a` continues the current heading | criterion 2: fewer turns are easier to follow |
| 50 | `tie-break*propose*no-difference` | equal crowd; neither continues the heading | criterion 3: truly equivalent |
| 51 | `tie-break*apply*prefer` | returns `(<ss> ^operator <a> > <b>)` | the result that resolves the impasse |
| 52 | `tie-break*apply*no-difference` | returns `(<ss> ^operator <a> = <b>)` | lets Soar choose at random (seeded) |

Every proposal tests that both items have the **same `^value`**. That
condition is carried into the chunk and is what keeps the learned rules
from ever overriding rule 33.

## 5. Learned rules (chunks)

Written by Soar, saved verbatim in
[`results/learned_chunks.soar`](../results/learned_chunks.soar). Example
(keep-heading):

```soar
sp {chunk*tie-break*apply*prefer*t2-93-1
    :chunk
    (state <s1> ^name navigate ^operator <o1> + ^heading <d1>
          ^operator { <o2> <> <o1> } +)
    (<o1> ^name move ^dir <d1> ^value <v1> ^to <t2>)
    (<o2> ^name move ^value <v1> ^to <t1> ^dir { <d2> <> <d1> })
    (<t1> ^crowd <c1>)
    (<t2> ^crowd <c1>)
    -->
    (<s1> ^operator <o1> > <o2>)}
```

It is the substate's reasoning (rules 47, 49, 51) compiled into a single
selection rule in the top state: same cost (`<v1>` twice), same crowd
(`<c1>` twice), `<o1>` keeps the heading and `<o2>` does not → prefer
`<o1>`. Identifiers and constants were variablised by Soar, so it applies
to any cells, any direction and any cost. Once it exists the tie never
reaches an impasse again.
