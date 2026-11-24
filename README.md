# TransitLens: a Visual Task Factory

A reusable pipeline that **generates synthetic transit-map images, questions about them, and
reference answers that are verified without using the model under test**, then measures where
multimodal models succeed and fail. Built for the Innodata AI Hackathon, Track 2.

## The problem it supports

Reading a transit map is a real job for AI assistants: navigation help, accessibility tools for
people who cannot see the map, and travel assistants. A wrong answer sends someone to the wrong
platform or makes them miss a connection. Maps are a good test because the answer needs *visual
structure*, not text recognition: which line goes where, which circles are real interchanges, and
which crossings are not.

## Why the tasks are valid

Every map is drawn from a graph the generator already knows, so the answer is known by
construction. Then four independent checks run on every task (`validate.py`):

1. **Two solvers must agree.** Solver A searches (station, line) states; solver B searches a graph
   of lines. Tests also compare both against a third, brute-force method on 600 random queries.
2. **The drawing alone must give the answer.** `parse_svg.py` rebuilds the network from shapes
   and text only (no hidden ids). The rebuilt network must equal the ground truth and give the
   same reference answer. If it does, the image carries enough evidence to answer the question.
3. **The PNG models see must match.** The checker samples pixels: every station marker is drawn
   and every line shows its colour.
4. **Every label is unambiguous.** A label is accepted only if its own marker is clearly the
   nearest one, in both directions. Maps that cannot be labelled legibly are rejected and
   regenerated.

**The validator is itself tested.** `transitlens audit` corrupts drawings five ways (remove a
marker, swap two names, recolour a line, delete a stop, move a label away) and checks each is
caught. See `docs/validator_audit.md`: every corruption is caught.

Reference answers never come from a model, and the `oracle` adapter (reads the SVG) scores 100%
on the dataset while the `random` baseline scores far below, so the tasks are solvable but not
guessable.

## Meaningful variation (not just new names)

| Axis | What changes |
|---|---|
| Network structure | 3 to 5 lines, 12x8 or 14x9 grid, 4 to 8 stations per line, random octilinear routes |
| Distractors | Lines that **cross without a station** (you cannot change lines there) vs real interchanges |
| Skill | Six question kinds: route planning, counterfactual rerouting (a line is closed), interchange identification, line tracing, legend matching, counting |
| Rendering | Two palettes (one colour-blind-safe), two line widths, two font sizes, two backgrounds |
| Names | Generated station names, so a model cannot answer from memory of a real network |
| Script | Station names in **Latin or Devanagari**, with the question in English (a mixed-script setting common in India) |

Every task records its difficulty (lines, stations, interchanges, crossings) so results can be
broken down instead of averaged away.

## Quick start

```bash
pip install -e ".[dev]"
transitlens generate --out out --maps 30 --questions 6 --seed 7   # tasks + images + manifest
transitlens generate --out hard --maps 20 --seed 33 --tier hard   # denser maps: 5-6 lines, 39-53 stations
transitlens validate --data out                                     # re-derive every answer from the drawings
transitlens audit --maps 20                                         # does the validator catch corrupted drawings?
transitlens evaluate --data out --adapter oracle                    # solvable? (should be 100%)
transitlens evaluate --data out --adapter random                    # guessable? (should be low)
GEMINI_API_KEY=... transitlens evaluate --data out --adapter gemini --model gemini-2.5-flash
LLM_API_KEY=...    transitlens evaluate --data out --adapter openai --base-url https://HOST/v1 --model NAME
transitlens evaluate --data out --adapter replay --answers replies.jsonl --name "my-model"  # score replies collected elsewhere
transitlens report --data out                                       # per-skill findings with 95% CIs
pytest                                                              # 155 tests
```

Evaluation is parallel and resumable; a failed API call is recorded as an error and never
counted as a wrong answer. Keys are read from environment variables and sent in headers only.

## Output

`out/tasks.jsonl` has one task per line: image path, question, reference answer, answer type,
skill, difficulty, and the validation record. `images/` holds the PNGs the model sees and
`maps/` the matching SVGs. A small committed example is in `samples/`.

## Findings

The report gives accuracy overall and by skill, question kind, number of lines, presence of
station-less crossings, and palette, each with a Wilson 95% confidence interval. Buckets with
fewer than 20 tasks are flagged and not ranked.

**Results for the organisers' target models are not in this repository yet.** Numbers for any
model are only reported from `transitlens evaluate` output, never written by hand.

What has been run so far (standard tier, seed 21, 30 maps, 180 tasks), with replies collected by
having Claude models read the PNGs in a chat session and scored through the `replay` adapter.
These are **not API runs** and they are not the organisers' models:

| Run | Correct / 180 |
|---|---|
| oracle (reads the SVG) | 180 |
| random-guess baseline | 21 (11.7%) |
| Claude Haiku 5.5 (chat-session image reading) | 180 |
| Claude Sonnet 5.5, run 1 | 179 |
| Claude Sonnet 5.5, run 2 (a request for Opus fell back to Sonnet) | 179 |

Finding: the standard tier is a ceiling for current Claude models, so it separates nothing. The
two Sonnet misses were one line-length count each. This is why the `hard` tier exists (5-6 lines,
39-53 stations, always with station-less crossings). It passes the same validator (120/120 tasks)
and the oracle (120/120). Model results on the hard tier have not been collected yet.

## Running it on a real model

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e .
transitlens generate --out out --maps 30 --questions 6 --seed 7
export GEMINI_API_KEY=...                              # Windows: set GEMINI_API_KEY=...
transitlens evaluate --data out --adapter gemini --model gemini-2.5-flash --workers 2 --delay 6
transitlens report --data out
```

`--delay` spaces calls apart for free-tier rate limits. Runs are resumable: rerun the same
command and only tasks that failed are retried. Never commit your key; it is only read from the
environment and sent in a request header.

## Honest limitations

* Maps are synthetic and schematic. Real maps have curves, geography, and more clutter, so a
  model's score here does not transfer one-to-one.
* The task convention that a crossing with no station is not an interchange is stated in the
  prompt (`adapters.PROMPT`); a model that ignores it will be marked wrong by design.
* Parsing the SVG proves the *drawing* contains the evidence. It does not prove a particular
  rasteriser or image resolution preserves it, which is why the PNG pixel check exists.
* Answers are scored by exact match after normalisation (`scoring.py`); a correct answer in an
  unexpected format could be marked wrong. Raw replies are kept in `results.jsonl` to inspect.
* No manual edits are made to generated outputs.
* Devanagari rendering needs Pillow with raqm (HarfBuzz) text shaping, which current Pillow
  wheels include. Both fonts used (DejaVu Sans, Noto Sans Devanagari) ship in the package, with
  their licences, so images are identical on every machine.

## Layout

```
src/transitlens/
  layout.py     random octilinear network with interchanges and station-less crossings
  render.py     primitives -> SVG and PNG, label placement with an ambiguity rule
  solve.py      two independent solvers for fewest interchanges
  questions.py  six question kinds with skill tags and answer_for()
  parse_svg.py  rebuilds the network from the drawing alone
  validate.py   solver agreement, SVG evidence, PNG pixel check
  mutate.py     corrupts drawings to test the validator
  tasks.py      dataset builder, variation recipes, difficulty metadata
  adapters.py   oracle, random, Gemini, OpenAI-compatible
  evaluate.py   parallel, resumable runner
  scoring.py    answer normalisation, Wilson interval
  report.py     per-skill findings
tests/          155 tests, 94% line coverage
```

## Reused components

Pillow (raster drawing), lxml (SVG parsing), requests (model APIs), pytest, and two fonts: DejaVu
Sans and Noto Sans Devanagari (SIL Open Font License). Everything else is original to this project.
