# Speaker notes — thesis defense

The slides carry figures and key numbers only; the talk itself lives here.
One section per slide, in deck order. The `\note{}` blocks in `main.tex` keep
only presenter cues and examiner contingencies, not spoken text. Backup
slides are unscripted — they exist for Q&A.

Timing plan (~20 min): intro + motivation + idea ~5, approach ~6, results ~7,
limitations + conclusion ~2.

## Title

Good {morning/afternoon}. My thesis asks whether a fuzzer can *learn* the
program it is attacking — using model-based reinforcement learning on top of
an emulator. I'll motivate why, show how the system is built, and then spend
most of the time on what the experiments actually say.

*(Timing plan: motivation + idea 3 min, approach 6 min, results 8 min,
limitations + conclusion 3 min.)*

## 1988: a thunderstorm invents fuzzing

*(~1 min. Beats: storm garbles the session → tools crash on garbage → the
storm is mutating valid input → `fuzz` systematizes it → transition.)*

Fuzzing has an origin story, and it starts with the weather. In 1988, Bart
Miller was logged into a Unix machine over a dial-up line during a
thunderstorm. The storm put noise on the wire, the noise scrambled the
characters he typed — he'd type `cat notes.txt` and something like
`c^t n&es.t#t` would arrive — and the standard Unix tools receiving that
garbage kept *crashing*.

Most people would curse the weather and redial. Miller noticed the storm was
doing something systematic: taking *valid* input and corrupting it at
random — and mature, production software fell over on it. So he turned the
accident into a method. A class project: a little program called `fuzz` that
generated random byte streams and pointed them at about 90 standard
utilities across seven Unix systems. Result: 25 to 33 percent of them
crashed or hung. Fuzzing was born — from a storm distorting a signal on a
wire.

**Transition:** For about 25 years, fuzzing stayed essentially this simple:
throw corrupted input at a program and wait for a crash. What turned it into
today's industrial bug-finding machine is one added ingredient — *feedback*.

## Today: coverage-guided fuzzing

*(~1.5 min. Beats: feedback was the missing ingredient → walk the loop →
OSS-Fuzz numbers → still blind, redeemed by throughput → transition.)*

This is the modern form — the loop on the slide, made mainstream by AFL in
2013. Instrument the target cheaply, so every execution reports which code
it reached. Keep a corpus of interesting inputs — seeds. Pick one, mutate it
— bit flips, arithmetic on integers, splicing two seeds, the "havoc" stack
of random edits — and run the mutant. If it reaches code no earlier input
reached, it goes back into the corpus and becomes raw material for further
mutation; otherwise it's thrown away. Crashes fall out as bug reports. An
evolutionary search, with coverage as the fitness function — that is
coverage-guided fuzzing, CGF.

And it works spectacularly. AFL itself is no longer maintained — the
community fork AFL++ is today's de-facto standard, and it's what Google's
OSS-Fuzz runs as a service since 2016: more than 13,000 security
vulnerabilities and over 50,000 bugs across a thousand open-source
projects. (AFL++ is also the baseline this thesis would eventually have to
beat — that comes back in the limitations.)

But notice *why* it works. The mutation itself is still blind random
corruption — the storm, industrialized. It is redeemed entirely by
throughput: thousands to tens of thousands of executions per second on a
native target.

**Transition:** Look at the figure once more — there is no model of the
target anywhere in that loop. Nothing in it learns. That's where the thesis
starts.

## Motivation: two problems with the loop

*(~1 min. One message: the loop has information it never learns from.)*

Two problems with this loop, and both are visible in the figure we just saw.

First: every decision in the loop is a hand-tuned heuristic. Which seed to
schedule next, which mutation operators to apply, how much energy to spend
on a seed — those knobs were set by hand, once, and shipped for every
target. But the optimal schedule is target-dependent, so for any given
target the shipped settings are likely suboptimal. And Böhme and Falk
quantified where that leads: finding *new* bugs needs exponentially more
compute.

Second: the loop throws away almost everything it observes. Every execution
produces a rich behavioral signal — the full trace, hit counts, the states
and values the program moved through. All of that is funneled into a single
scalar — "did this input reach new coverage?" — and the rest is discarded.

**Transition:** Both problems point the same way: the information is there,
but nothing in the loop learns from it. So — what if the fuzzer could
learn?

## Idea: a fuzzer that plans with a learned model of the target

*(~1.5 min.)*

Step back and look at what fuzzing *is*: sequential decision making under
uncertainty, with a scalar progress signal. That is a Markov decision
process — reinforcement learning's home turf.

We use *model-based* RL: EfficientZero, from the MuZero lineage. It learns a
latent model of its environment and plans in that model with Monte-Carlo
tree search. And it is sample-efficient by construction — superhuman Atari
play from about two hours of experience. That's exactly the trade we want:
conventional fuzzing spends executions freely because they are cheap;
under emulation they are not. We buy information per execution at the cost
of compute per execution.

The environment side runs under emulation, and that choice is deliberate:
an emulator instruments unmodified binaries on any architecture, and its
lightweight snapshots give exact, cheap resets — which is what makes
episodic RL work, and what makes *stateful* targets (protocol servers, ICS,
embedded stacks, where coverage depends on the input history) tractable at
all. That's the "emulator-based stateful" part of the title.

To the best of our knowledge, this is the first fuzzer that plans with a
*learned* model of the target's behavior. Prior RL fuzzers are model-free —
Q-learning variants choosing among fixed mutators. Prior planning fuzzers
search an explicitly constructed model, like a recovered protocol state
machine. Nobody has let the fuzzer learn the model itself.

## Research questions

*(~0.5 min.)*

Three questions structure the rest of the talk. RQ1, learnability: coverage
rewards are sparse and observations alias program states — can EfficientZero
learn a useful policy at all? RQ2, action space: what *is* an action for a
fuzzing agent — the program input itself, or a mutation on a corpus? RQ3,
planning: does planning with the learned model actually help — can the agent
usefully imagine how the target reacts? The conclusion answers them in
order.

## EfficientZero (1): a learned model of the target

*(~1.5 min. The algorithm has two halves: a learned model, and search inside
it. This slide: the model.)*

EfficientZero is worth understanding at least at this level, because
everything in the results depends on it. Everything you see here is a
learned network — no hand-designed features anywhere.

The representation network *h* encodes an observation — coverage state plus
the current seed — into a latent state s⁰. What that latent contains is up
to the network; nobody tells it what matters about the target.

The dynamics network *g* is the actual *model*: given a latent state and an
action, it predicts the next latent state. Stepping *g* is an imagined
execution of the target — no emulator involved. Out of every latent, two
prediction heads read: *p*, a prior over actions, and *v*, the expected
return from that state. (There is also a reward-prediction head I'll skip
here — it doesn't change the picture.)

Training, bottom row: 128 self-play environments generate trajectories into
a prioritized replay buffer, and a GPU learner trains all the networks
jointly. The targets: search visit counts train *p*, n-step returns train
*v* — and a consistency loss keeps the imagined latent s¹ close to what *h*
produces from the real next observation, which keeps the model honest.

**Transition:** So we have a model of the target. What do we do with it? We
search in it.

## EfficientZero (2): planning = search inside the model

*(~1.5 min. Four builds — advance the slide as each step is narrated:
select → expand → evaluate → back up. The payoff text appears with the
last build. All four networks appear on the figure: h at the root, p in
the priors, g on the expand edge, v at the leaf.)*

With the model in hand, choosing an action is a Monte-Carlo tree search —
run entirely inside that model. The root is the current situation: the
representation network *h* encodes the observation into the latent state
s⁰, and the policy network *p* provides priors over the actions, perturbed
at the root by Dirichlet noise. Each of the N simulations then does four
things.

Select: walk down the existing tree by the pUCT rule — the formula on the
slide. At every node, pick the action maximizing Q plus an exploration
bonus: Q(s,a) is the current value estimate from earlier back-ups; P(s,a)
is the prior from the policy network — this is where the network steers the
search; and the last factor grows with the parent's total visits N(s) but
fades as this particular action's count N(s,a) climbs. So promising *and*
untried actions both get visits, and an action the prior likes gets
explored earlier. Expand — [advance]: the
new node comes from the dynamics network, *g* of state and action. This is
an *imagined* step; the real target is never executed during search.
Evaluate — [advance]: the leaf is scored by the value network *v* directly,
no rollouts. Back up — [advance]: that value propagates to the root,
updating the statistics along the path.

After 200 simulations — the baseline setting — the visit counts at the root
are a *search-improved* policy: better than the raw prior *p*, because the
search has looked ahead. The action is sampled from those counts with a
temperature *T*.

Two things to hold on to. First, the key sentence of the whole approach:
the real program is never run during planning — that is "planning with a
learned model", and every network took part: *h* at the root, *p* and *v*
inside the search, *g* for each imagined step. Second: the exploration
knobs — temperature *T*, Dirichlet *α* — live right here at the root.
Remember them; the ablation will turn exactly these, and the simulation
count comes back as RQ3.

## Fuzzing as an MDP: observations and reward

*(~1.5 min.)*

How does fuzzing become an MDP? Observations, top row: the emulator reports
basic-block hit counts; they are FNV-hashed into a fixed array — 4096
buckets for cJSON — and compressed into AFL-style logarithmic hit-count
levels. In the corpus setting, the current seed bytes are part of the
observation too.

The reward has two terms — breadth plus depth. Breadth: marginal novelty
against the union of everything already seen this episode. That means
repeating a good seed earns *nothing* — built-in exploration pressure.
Depth: a bonus for beating the deepest single execution so far, weighted by
ω. Everything is episodic: at episode end the emulator snapshot is restored,
so every episode starts from the identical state.

## Two action-space formulations

*(~1 min.)*

RQ2 gets two answers, and we built both. Input-level, left: an action *is*
the next piece of input — one byte, or one protocol message. The policy
literally becomes a generative model of the target's input language. Natural
for stateful, byte-by-byte consumers.

Corpus-level, right: the classical CGF shape — evolve a seed; here a single
fixed-length seed. An action picks a position and the byte value to write
there, plus a retain-or-discard decision. Note what's missing: probabilistic
mutation operators. MuZero-style planning cannot absorb operator randomness,
so we replace the operator catalogue with deterministic byte writes — and
the agent learns its own mutation strategy.

Both give what EfficientZero needs: a discrete, deterministic action space
of tractable size.

## System: three layers, two seams

*(~1 min.)*

The implementation is three layers, all Rust. On top, `efficientzero` — the
RL agent, fully generic; it knows nothing about fuzzing. In the middle,
`mugiwara` — the fuzzing environment: targets, corpus handling,
instrumentation, probes. At the bottom, MOGI — user-space emulation on
Unicorn/QEMU: block hooks, snapshots, unmodified x86-64 guests. Both seams
are plain Rust traits: the generic RL environment interface on top, the
emulator contract below. Networks run on the `burn` framework with a CUDA
backend; 128 environments step in parallel, one emulator and guest each,
reset by snapshot restore.

## Evaluation: six targets, one ablation campaign

*(~1 min.)*

Six targets in two groups. The three input-level targets are correctness
tests for the learner — single seed, single run each: high-and-low is a
bandit sanity check, sequence a 16-byte passcode with partial observability,
open62541 a real OPC UA server where the goal is an activated session.

The corpus-level group carries the quantitative weight: on cJSON we ran a
15-arm ablation, 4 PRG seeds each, which fixes the configuration; libxml2
and picohttpparser then test *transfer* of that configuration unchanged at
400 iterations. All corpus runs: 128 parallel environments on one L40S —
1.66 million guest executions in about 21 hours for cJSON, 3.33 million in
about 42 for the transfer targets. And crucially, cJSON includes CTRL-RAND,
a random-search control at an *identical* execution budget.

## RQ1: the learner solves all three input-level targets

*(~1 min.)*

All three input-level targets are solved. High-and-low plays
coverage-paying bytes at a rate above 0.99 against a random baseline of
0.016 — interestingly, after first trending *below* random. Sequence
recovers the full 16-byte passcode, one position at a time. And open62541:
the agent learns the full protocol sequence — hello, open channel, create
session, activate — and it learns to *postpone* the activating message to
the episode cap, because activation ends the episode. The optimal policy is
to loiter, and the agent finds that: return 21 of a possible 22. Credit
assignment works on a real server.

## RQ1: corpus actions — planning beats random search

*(~1.5 min.)*

The headline result. cJSON, identical execution budget, medians over 4
seeds times 128 environments. The bootstrap corpus starts at 240 blocks.
Random search reaches 542. The baseline configuration reaches 645, and the
best arm, T25, reaches 958 — 1.77 times the random control at the same
budget.

The distributional view is even sharper: the fraction of episodes whose best
seed beats the random control's 99th percentile is 76.7 percent for the
baseline versus 1.1 percent for random — about 71 times as often. This is a
fair comparison against undirected mutation — not against AFL++; no
conventional fuzzer was run, that's on the limitations slide.

## Ablation: exploration is the knob that matters

*(~1.5 min.)*

Fifteen arms, four seeds each; dots are seeds, red bars medians. The
pattern: exploration dominates. Constant high search temperature wins —
T25 at 958 and T15 at 936 versus the scheduled baseline at 645. In other
words, EfficientZero's default temperature schedule — tuned for Atari — is
wrong for fuzzing. Scaling down Dirichlet noise to match the action space,
ALPHA004, also helps: 876. Most other knobs — model capacity, the depth
term, seed reuse — move the result less than the seed spread within a
single arm. And every trained arm beats random.

## RQ3: planning helps early, then fades

*(~1.5 min.)*

Does planning actually contribute? The plot shows the KL divergence between
the search-improved policy and the raw network prior — how much the tree
search changes the policy. It falls near-monotonically on all three
targets, cJSON from 0.99 to 0.28 nats: planning contributes most in the
first iterations and little at the end.

The simulation-count arms say the same thing: 50, 100, 200 simulations give
687, 640, 645 blocks — flat — while wall-clock scales linearly, 7.6 versus
21.3 hours. So the honest RQ3 answer: yes, the learned model is good enough
to plan in, but on targets this small, cheap planning is enough.

## The agent discovers input structure on its own

*(~1 min.)*

My favorite result. Look at the highest-coverage inputs: all four cJSON
seeds, from three *different* arms, converge on the same motif — nested
arrays — purely by optimizing coverage reward. Nesting was never described
to the agent. A recursive-descent parser pays coverage for nesting; the
agent found that property of the target, not us. Same story on libxml2:
nested tags, coverage from 1416 to 5281 blocks. The structural byte rate
climbs from chance to 0.90 on cJSON, 0.73 on the others. And
picohttpparser is the honest negative case: it saturates at 81 blocks —
the target simply has little coverage to give for structure.

## But: structure decays and the policy narrows

*(~1 min.)*

The same metric over training time shows the failure mode: the structural
rate peaks at a quarter to a third of the budget, and every target *ends
below its peak*. Under the hood, the per-position MCTS visit entropy
collapses — earliest seed positions first — from about 2.4 nats to as low
as 0.08. This is classic policy collapse: overrepresented actions get
overtrained. Prioritized replay, high temperature, and Dirichlet noise are
what keep it alive — which connects straight back to the ablation: the
winning arms are exactly the ones injecting more exploration.

## Limitations and threats to validity

*(~1.5 min. Bring NOCOV up yourself.)*

Honest accounting, biggest first. Throughput: the chart is log-scale. We
measure 22 guest executions per second under 8-way GPU contention — roughly
three times that solo — and dropping MCTS entirely only reaches about 41:
emulator and learner are the bottleneck, and a native persistent harness
does ten *thousand*. Competitiveness would need three orders of magnitude
more coverage per execution.

Second: no conventional-fuzzer baseline — no AFL++ or libFuzzer run — so
the results show feasibility, not competitiveness. Third: four seeds per
arm are thin; only 5 of 13 trained arms have a seed range disjoint from the
baseline's. Fourth — and I want to flag this myself — the NOCOV surprise:
zeroing out the coverage observation *beats* the baseline, 755 versus 645.
On a target this small, the seed bytes alone may carry enough signal. And
fifth: everything corpus-level ran on a single fixed-length seed; the full
corpus formulation is designed but not evaluated.

## Conclusions

*(~1 min.)*

The three answers. RQ1: yes — EfficientZero learns useful policies from
coverage-shaped rewards on all six targets, up to activating an OPC UA
session and inventing nested JSON and XML. RQ2: both formulations work;
corpus-level is the way forward — it matches the classical CGF shape and
needs no hand-crafted operators. RQ3: planning works — the search
demonstrably improves the policy early — but its marginal value fades at
this target size.

The takeaway: model-based deep RL can drive a fuzzer end-to-end. The
obstacle is not learnability — it is the three-orders-of-magnitude
throughput gap. This thesis moves the question from "can RL fuzz?" to "can
it become cheap enough?" — and that points at the future work: the full
seed-corpus formulation via Sampled or Gumbel MuZero, hybrid CGF-plus-RL
loops, larger targets, and throughput engineering.

## Questions?

Thank the audience; keep the three anchors on screen: 1.77× random at equal
budget, the invented nested-array input, first fuzzer planning with a
learned model.
