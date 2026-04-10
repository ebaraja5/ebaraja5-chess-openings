# Master Prompt: Chess Opening Lines → TTS-Annotated MP3s

This document preserves the complete workflow for converting raw chess opening game text into fully TTS-annotated Python script entries that can be fed to the `generate_chess_mp3_final` script.

Copy-paste the relevant sections into **Copilot Chat** or **ChatGPT** when working on a new set of opening files.

---

## Overview

The workflow has three phases:

| Phase | Input | Output |
|-------|-------|--------|
| **1 – Capture & Clean** | Raw chess game text (DOCX / copy-paste) | Per-variation `.txt` files |
| **2 – Build Master** | All per-variation `.txt` files | Combined `files 1-N.txt` with deduplication |
| **3 – Generate TTS Segments** | `files 1-N.txt` or `new files` (with `===FILE N===` markers) | `FILES` entries (Python list) ready to paste into the script |

---

## Phase 1 — Interactive Raw Line Capture

### Purpose

Capture the main line of a chess opening variation and strip away everything that is not part of the main line or its accompanying commentary.

### What to remove

- Alternative move branches (lines in parentheses or indented after the main move)
- Chess.com metadata: video headers, chapter titles, section labels, "Main line…" tags
- Transition phrases between lines (e.g. "If White plays instead…", "Another option is…")
- Empty or redundant headers

### What to keep

- Every move in the main line, each on its own line
- Move numbers (e.g. `6.` or `6...`)
- Commentary sentences that directly follow a move and explain the plan or evaluation

### Output format

One file per variation, named `file-N.txt`. Each file follows this layout — every token on its own line, with a blank line between move number and the move itself where present in the source:

```text
1.

d4

Knight to f6

2.
c4

e6

3.
Knight to c3

Bishop to b4

4.
e3

4...

short castle

5.
Bishop to d2

b6

6.

a3

6...

Bishop takes c3

7.
Bishop takes c3

Knight to e4

We will get rid of White's bishop pair in the near future and have a fine game.
Our c8-bishop will have a fine spot on b7 and after a subsequent ...d6, the
b8-knight will likely go to f6 via d7. This is not a line we should worry about.
```

### Prompt to give the AI (Phase 1)

```
You are helping me prepare chess opening lines for text-to-speech (TTS) audio.

I will paste a raw chess game transcript. Please:
1. Extract only the MAIN LINE. Remove all alternative moves and branches.
2. Remove metadata: headers, chapter titles, "Main line" labels, Chess.com links.
3. Remove transition phrases between lines (e.g. "If White instead plays…").
4. Keep move numbers (e.g. "6." and "6...") each on their own line.
5. Keep every move on its own line.
6. Keep commentary sentences that explain the plan or evaluation immediately after
   the relevant move. One sentence per line is fine.
7. Output ONLY the cleaned text — no code fences, no extra headings.

Here is the raw text:
[PASTE RAW TEXT HERE]
```

---

## Phase 2 — Building the Combined Master File

### Purpose

Combine all per-variation `.txt` files into a single file (e.g. `files 1-19.txt`) that will be used as the source for Phase 3. Repeated commentary is removed so it is not voiced more than once.

### Rules

- Separate each variation with a header line: `===== FILE N =====`
- Copy **all** lines (moves + commentary) from FILE 1 (first file of a group) verbatim.
- For FILE 2 onwards:
  - Copy all move lines verbatim.
  - For commentary lines: **only include them if they do not appear in the immediately preceding file**. If a commentary sentence is identical to one in the prior file, omit it.
  - This way, repeated opening moves are still present (for context), but repeated explanations are not re-voiced.

### Example (files 1-19.txt excerpt)

```
===== FILE 1 =====
1.

d4

Knight to f6

2.
c4

e6

3.
Knight to c3

Bishop to b4

4.
e3

4...

short castle

5.
Bishop to d2

b6

6.

a3

6...

Bishop takes c3

7.
Bishop takes c3

Knight to e4

We will get rid of White's bishop pair in the near future and have a fine game.


===== FILE 2 =====
1.

d4

Knight to f6

2.
c4

e6

3.
Knight to c3

Bishop to b4

4.
e3

4...

short castle

5.
Bishop to d2

b6

6.

Bishop to d3

6...

d5

7.
c takes d5⚡

e takes d5⚡

8.
Rook to c1

8...

c5

9.
a3

This was played in Hammer-Kollars, San Francisco 2019. Black should have continued here with ...Bishop takes c3.

9...

Bishop takes c3

10.
b takes c3⚡

Bishop to a6

After the trade of the light-squared bishops, Black will have an excellent game.
```

### Prompt to give the AI (Phase 2)

```
I have [N] cleaned chess opening files (file-1.txt through file-N.txt). I will
paste them one at a time. After receiving all of them, combine them into a
single file where:

- Each file's content is preceded by a header: ===== FILE 1 =====
- FILE 1 is included entirely as-is.
- For FILE 2 onwards: include ALL move lines, but OMIT any commentary sentence
  that is IDENTICAL to one that appeared in the immediately prior file.

Output only the combined text with no extra formatting.

Here is file-1.txt:
[PASTE FILE 1 CONTENT]

Here is file-2.txt:
[PASTE FILE 2 CONTENT]

[… continue for all files …]
```

---

## Phase 3 — Building RAW_FILES and TTS Segments

### Purpose

Parse the combined file (or a `new files` source with `===FILE N===` markers) into a Python `FILES` list where each entry is:

```python
("OutputName.mp3", [(text, speed), (text, speed), ...])
```

### Speed rules

| Condition | Speed |
|-----------|-------|
| FILE 1 and FILE 6 (first file of each group) — all lines | `1.12` |
| FILE 2–5 and FILE 7–19 — lines **identical** to the prior file (common prefix) | `1.45` |
| FILE 2–5 and FILE 7–19 — new move lines (from the first difference onward) | `1.12` |
| FILE 2–5 and FILE 7–19 — new commentary / explanation lines | `1.05` |

A **commentary line** is any line that:
- Is longer than 25 characters, **or**
- Contains a period (`.`) or comma (`,`)

A **move line** is any short token (piece name + square, or move number) that does not meet the commentary criteria.

### Python helper functions

Paste these helpers into your script just above the `FILES` definition:

```python
def is_commentary(line: str) -> bool:
    """
    Returns True if the line looks like a commentary/explanation sentence
    rather than a bare chess move.
    """
    s = line.strip()
    if not s:
        return False
    return len(s) > 25 or "." in s or "," in s


def find_prefix_length(prev_lines: list[str], curr_lines: list[str]) -> int:
    """
    Return the length of the common ordered prefix between two line lists.
    Comparison is done after stripping whitespace.
    """
    n = min(len(prev_lines), len(curr_lines))
    for i in range(n):
        if prev_lines[i].strip() != curr_lines[i].strip():
            return i
    return n


def build_segments_for_file(
    file_number: int, raw_files: dict[int, list[str]]
) -> list[tuple[str, float]]:
    """
    Build a list of (text, speed) segments for the given file number.

    Speed rules:
    - FILE 1 and FILE 6 (first of each group): all lines at 1.12.
    - All other files:
        * Lines that match the common prefix with the prior file → 1.45
        * New lines (moves) after the first difference → 1.12
        * New lines (commentary) after the first difference → 1.05
    """
    lines = [ln.strip() for ln in raw_files[file_number] if ln.strip()]

    # First file of each group: everything at 1.12
    if file_number in (1, 6):
        return [(ln, 1.12) for ln in lines]

    prev_lines = [ln.strip() for ln in raw_files.get(file_number - 1, []) if ln.strip()]
    diff_idx = find_prefix_length(prev_lines, lines)

    segments: list[tuple[str, float]] = []

    # Common prefix → read fast (1.45)
    for i in range(diff_idx):
        segments.append((lines[i], 1.45))

    # New tail → 1.12 for moves, 1.05 for commentary
    for i in range(diff_idx, len(lines)):
        ln = lines[i]
        speed = 1.05 if is_commentary(ln) else 1.12
        segments.append((ln, speed))

    return segments
```

### Populating RAW_FILES

`RAW_FILES` is a plain dict mapping file number → list of text lines. You do **not** add speeds here — just the raw text in order:

```python
RAW_FILES: dict[int, list[str]] = {
    # ── Bd2 group (FILES 1–5) ───────────────────────────────────────────────
    1: [
        "1. d4",
        "Knight to f6",
        "2. c4",
        "e6",
        "3. Knight to c3",
        "Bishop to b4",
        "4. e3",
        "4... short castle",
        "5. Bishop to d2",
        "b6",
        "6. a3",
        "6... Bishop takes c3",
        "7. Bishop takes c3",
        "Knight to e4",
        "We will get rid of White's bishop pair in the near future and have a fine game. "
        "Our c8-bishop will have a fine spot on b7 and after a subsequent ...d6, the "
        "b8-knight will likely go to f6 via d7. This is not a line we should worry about.",
    ],
    2: [
        "1. d4",
        "Knight to f6",
        # … (lines up to first difference are the same as FILE 1)
        "6. Bishop to d3",
        "6... d5",
        # … new lines continue here
    ],
    # … entries 3, 4, 5 …

    # ── Nf3 group (FILES 6–19) ──────────────────────────────────────────────
    6: [
        "1. d4",
        "Knight to f6",
        "2. c4",
        "e6",
        "3. Knight to c3",
        "Bishop to b4",
        "4. e3",
        "4... short castle",
        "5. Knight to f3",
        "d5",
        # … all lines for FILE 6 …
    ],
    7: [
        # … lines for FILE 7 …
    ],
    # … entries 8–19 …
}
```

### Building all FILES entries automatically

```python
def build_all_rubinstein_files(
    raw_files: dict[int, list[str]]
) -> list[tuple[str, list[tuple[str, float]]]]:
    """
    Build FILES-compatible entries for all 19 logical files:
      FILE  1–5  →  "Rubinstein System 4.e3 O-O 5.Bd2 #1.mp3" … #5.mp3
      FILE  6–19 →  "Rubinstein System 4.e3 O-O 5.Nf3 #1.mp3" … #14.mp3
    """
    mapping: dict[int, str] = {}
    for n in range(1, 6):
        mapping[n] = f"Rubinstein System 4.e3 O-O 5.Bd2 #{n}.mp3"
    for idx, n in enumerate(range(6, 20), start=1):
        mapping[n] = f"Rubinstein System 4.e3 O-O 5.Nf3 #{idx}.mp3"

    entries = []
    for file_no, mp3_name in mapping.items():
        if file_no not in raw_files:
            continue
        segments = build_segments_for_file(file_no, raw_files)
        entries.append((mp3_name, segments))
    return entries


# Extend your existing FILES list:
FILES.extend(build_all_rubinstein_files(RAW_FILES))
```

### Prompt to give the AI (Phase 3)

````
I have a chess opening file that contains 19 variations separated by markers like:

  ===FILE 1=== Rubinstein System 4.e3 O-O 5.Bd2 #1
  …
  ===FILE 19=== Rubinstein System 4.e3 O-O 5.Nf3 #14

Please parse it and produce a Python `RAW_FILES` dict (file number → list of
text lines) using the following rules:

- Strip blank lines between entries; each move or commentary text is one list item.
- Do NOT add speeds — just the raw text strings.
- FILE 1 and FILE 6 are the first files of their respective groups and need no
  comparison.

Here is the source text:
[PASTE YOUR COMBINED FILE CONTENT HERE]
````

---

## `new files` Source Format

The `new files` document in the repository uses a compact format without blank lines between entries:

```
===FILE 1=== Rubinstein System 4.e3 O-O 5.Bd2 #1
1.
d4
Knight to f6
2.
c4
e6
…
===FILE 2=== Rubinstein System 4.e3 O-O 5.Bd2 #2
1.
d4
…
```

**Key differences from `files 1-19.txt`:**

| Feature | `files 1-19.txt` | `new files` |
|---------|-----------------|-------------|
| Separator | `===== FILE N =====` | `===FILE N=== Name` |
| Blank lines between tokens | Yes | No |
| Commentary deduplication | Applied (Phase 2 output) | Not applied (raw Phase 1 output) |

When parsing `new files`, treat consecutive non-separator lines as a flat list of tokens. Blank-line collapsing is not needed.

---

## General Interaction Rules

When working with an AI assistant (Copilot Chat or ChatGPT) using this workflow:

1. **One file at a time (Phase 1).** Paste a single raw game transcript and ask for the cleaned output. Review it before moving on.
2. **Confirm the file number.** Always tell the AI which `FILE N` the transcript corresponds to so the prefix comparison is accurate.
3. **Keep commentary rules consistent.** Commentary is preserved only from the move where it first differs from the prior file. If you want commentary to start from a specific move number (e.g. "keep commentary from move 27 onward"), state that explicitly.
4. **Review generated speeds.** After Phase 3, scan the generated `FILES` entry and verify the 1.45 / 1.12 / 1.05 assignments look right, especially around the transition point.
5. **Don't modify existing `FILES` entries.** The script processes the `FILES` list in order and skips already-generated MP3s. Appending new entries is always safe.
6. **Extend, don't replace.** Use `FILES.extend(build_all_rubinstein_files(RAW_FILES))` to add new entries rather than manually editing the hardcoded list.

---

## Quick Reference: Speed Summary

```
Speed 1.45 — Repeated opening moves (listener already knows them; play fast)
Speed 1.12 — New main-line moves (normal narration pace)
Speed 1.05 — Commentary / explanation sentences (slightly slower for clarity)
```
