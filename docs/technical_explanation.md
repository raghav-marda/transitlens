# Technical explanation (Track 2: visual problem and model evaluation)

## Image family and problem
Synthetic schematic transit maps. Practical impact: navigation assistants and accessibility tools
for people who cannot see a map. A wrong answer sends someone to the wrong platform. The answer
needs visual structure (which line goes where, which circles are interchanges, which crossings
are not), not text recognition.

## Design decisions
* **Code decides, the model is only the subject under test.** Each map is drawn from a graph, so
  the reference answer is known by construction and never comes from a model.
* **Independent validation.** Two solvers must agree (and are cross-checked against brute force),
  the answer must be recoverable from the SVG alone, the PNG is pixel-checked, and every label
  must pair unambiguously with its marker. Candidates that fail are regenerated, never hand-edited.
* **The validator is tested.** `transitlens audit` corrupts drawings five ways; all 500 are caught.
* **Distractors by design.** Lines that cross with no station are not interchanges.
* **Difficulty is recorded** per task so results are broken down, not averaged away.

## Assumptions
* The convention "a crossing without a station is not an interchange" is stated in the prompt.
* Answers are scored by exact match after normalisation; raw replies are kept for inspection.
* Synthetic schematic maps do not transfer one-to-one to real, curved, cluttered maps.

## Task variation strategy
Structure (3 to 6 lines, grid size, interchanges, crossings), skill (six question kinds),
rendering (two palettes incl. colour-blind safe, line width, font size, background), names
(generated; Latin or Devanagari), and difficulty tier (standard, hard with 39 to 53 stations).

## Reused components
Pillow, lxml, requests, pytest, DejaVu Sans and Noto Sans Devanagari (SIL Open Font License).

## Models and tools
* Pipeline and tests were written with Claude (Sonnet 5.5) as a coding assistant.
* Evaluated so far: Claude Haiku 5.5 and Claude Sonnet 5.5, reading the PNGs in a chat session
  (scored through the replay adapter). These are not API runs. Gemini and OpenAI-compatible
  adapters exist for API runs.
* No manual fixes were made to any generated output.

## Findings so far
Clean images: standard tier (180 tasks) oracle 180, random 21, Haiku 180, Sonnet 179 and 179;
hard tier (120 tasks) Haiku 120, Sonnet 120. Both are ceilings for these models.

Degradation curve for Sonnet (share of original size, 100/70/55/40/25%): 100, 98.3, 93.3, 64.2, 20.8% (Latin 100, 97.4, 97.4, 84.6, 24.4; Devanagari 100, 100, 85.7, 26.2, 14.3). The 25% run was all placeholder guesses by the agent's own report.

Degraded images (hard tasks at 40% size, JPEG quality 25): Sonnet 77/120 (64%), Haiku 24/120
(20%), random 11/120. Sonnet reached 84.6% on Latin names but 26.2% on Devanagari. Counting and
line length survived (95%); legend matching and connecting-station fell to 45%. Both models
reported guessing on many answers instead of declining. These are chat-session runs, not API
runs, on 20 maps; the intervals are wide and the models are not the organisers' models.
