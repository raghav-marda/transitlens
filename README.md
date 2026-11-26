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
transitlens generate --out hard --maps 20 --seed 33 --tier hard
transitlens degrade --data hard --out hard_low --scale 0.4 --quality 25   # robustness stress test   # denser maps: 5-6 lines, 39-53 stations
transitlens validate --data out                                     # re-derive every answer from the drawings
transitlens audit --maps 20                                         # does the validator catch corrupted drawings?
transitlens evaluate --data out --adapter oracle                    # solvable? (should be 100%)
transitlens evaluate --data out --adapter random                    # guessable? (should be low)
GEMINI_API_KEY=... transitlens evaluate --data out --adapter gemini --model gemini-2.5-flash
LLM_API_KEY=...    transitlens evaluate --data out --adapter openai --base-url https://HOST/v1 --model NAME
transitlens evaluate --data out --adapter replay --answers replies.jsonl --name "my-model"  # score replies collected elsewhere
transitlens report --data out                                       # per-skill findings with 95% CIs
pytest                                                              # 157 tests
docker build -t transitlens . && docker run --rm transitlens      # full reproduction in a container
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

Hard tier (same method, 120 tasks, seed 33): oracle 120, random 5 (4.2%), Claude Haiku 120,
Claude Sonnet 120. Clean images at full resolution are not hard enough for these models.

**Degraded-image stress test** (`transitlens degrade --scale 0.4 --quality 25`, same hard tasks,
images shrunk to 40% and JPEG-compressed). This is where the tasks separate:

| Run | Correct / 120 | Latin names | Devanagari names |
|---|---|---|---|
| oracle | 120 | 78/78 | 42/42 |
| Claude Sonnet 5.5 | 77 (64.2%, CI 55 to 72%) | 66/78 (84.6%) | 11/42 (26.2%) |
| Claude Haiku 5.5 | 24 (20.0%, CI 14 to 28%) | 17/78 (21.8%) | 7/42 (16.7%) |
| random guess | 11 (9.2%) | 9/78 | 2/42 |

What failed, for Sonnet: skills that need to read labels or follow a thin line collapsed
(legend matching 45%, connecting station 45%, lines at a station 60%), while pure structure
survived (counting 95%, line length 95%). Devanagari labels were close to illegible at this
resolution. Both agents reported that many answers were guesses (Haiku said most; Sonnet about
50 of 120), which is the finding: the models guess instead of declining when the image is
unreadable.

Examples of the wrong answers, with the exact image the model saw, are in
[docs/failure_gallery.md](docs/failure_gallery.md) (`transitlens gallery`).

Caveats: these are chat-session runs, not API runs, on 20 maps, so the intervals are wide; the
image pipeline of the chat session may itself downscale images; resolution loss is an artificial
stress, not a natural one; Haiku and Sonnet are not the organisers' models.

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
tests/          157 tests, 94% line coverage
```

## Reused components

Pillow (raster drawing), lxml (SVG parsing), requests (model APIs), pytest, and two fonts: DejaVu
Sans and Noto Sans Devanagari (SIL Open Font License). Everything else is original to this project.
