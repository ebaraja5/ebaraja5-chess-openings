"""
tools/build_master_and_tts.py
─────────────────────────────
Helper module for the Chess Opening Line Capture & TTS Builder workflow.

This module connects to the three-phase workflow described in
``docs/master-prompt-template.md`` and provides reusable Python functions
for:

  Phase 2 — Analysis
    • ``load_folder``          – load and sort .txt files from a folder
    • ``strip_alternatives``   – remove "alternative" blocks from raw lines
    • ``build_master_txt``     – merge all files into ``master.txt``, stripping
                                 repeated commentary vs the previous file

  Phase 3 — TTS Configuration
    • ``parse_master_txt``     – split ``master.txt`` back into per-file line lists
    • ``is_commentary``        – decide whether a line is explanatory prose
    • ``find_prefix_length``   – count how many leading lines two files share
    • ``build_segments_for_file`` – assign (text, speed) to each line
    • ``build_all_files``      – yield (mp3_name, segments) for every file

Usage example (replaces the hand-crafted FILES list in generate_chess_mp3_final.py)
─────────────────────────────────────────────────────────────────────────────────────
    from tools.build_master_and_tts import (
        load_folder,
        build_master_txt,
        parse_master_txt,
        build_all_files,
    )
    from pathlib import Path

    folder = Path("Rubinstein System 4.e3 O-O 5.Bd2 & Nf3/new files folder")
    master_path = folder / "master.txt"

    # Phase 2 – build master.txt (run once)
    raw_files = load_folder(folder)
    build_master_txt(raw_files, master_path)

    # Phase 3 – generate FILES list
    parsed = parse_master_txt(master_path)
    # first file in each group is a main-line file (index 0 for Bd2, index 5 for Nf3)
    main_line_indices = {0, 5}

    def naming_fn(index, label):
        return label.strip() + ".mp3"

    FILES = list(build_all_files(parsed, main_line_indices, naming_fn))
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Generator, Iterable

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

#: Patterns whose lines (and the block that follows) are treated as
#: "alternative" blocks to be stripped during normalisation.
_ALTERNATIVE_STARTERS: tuple[str, ...] = (
    "let's explore an alternative",
    "main line",
    "alternative:",
    "variation:",
    "let's look at",
    "instead,",
    "another option",
    "let's consider",
)

#: A line that begins with digits followed by '.' or '...' is a move-number
#: annotation (e.g. "1.", "14...", "4...").
_MOVE_NUMBER_RE = re.compile(r"^\d+\.{1,3}$")

#: A line consisting only of short chess tokens — piece moves, pawn moves,
#: special moves — is treated as a move line, not commentary.
_MOVE_TOKEN_RE = re.compile(
    r"^(?:"
    r"(?:Knight|Bishop|Rook|Queen|King)\s+(?:to|takes)\s+\w+"  # piece moves
    r"|[a-h][1-8]"                                              # pawn destination
    r"|[a-h]\s+takes\s+[a-h][1-8]"                             # pawn capture
    r"|short\s+castle|long\s+castle"                            # castling
    r"|[bcdefgh]\d+[⚡✓]?"                                      # simple pawn push
    r"|[a-h]\s+takes\s+\w+[⚡✓]?"                              # pawn capture variant
    r")$",
    re.IGNORECASE,
)

#: Section header written by ``build_master_txt`` / expected by ``parse_master_txt``.
_SECTION_HEADER_RE = re.compile(r"^===FILE\s+(\d+)===\s*(.*)$")

# Speed values
SPEED_PREFIX = 1.45   # repeated opening prefix in a derivative file
SPEED_MOVE = 1.12     # new move lines / all lines in a main-line file
SPEED_LONG_COMMENT = 1.05  # new long-commentary lines in a derivative file

LONG_COMMENT_THRESHOLD = 80  # characters; above this → SPEED_LONG_COMMENT


# ─────────────────────────────────────────────────────────────────────────────
# LINE CLASSIFICATION
# ─────────────────────────────────────────────────────────────────────────────

def is_commentary(line: str) -> bool:
    """Return True if *line* is an explanatory commentary line.

    A line is *not* commentary if it looks like a chess-move annotation:
    - A bare move-number token like ``"1."`` or ``"14..."``
    - A piece-move or pawn-move token like ``"Knight to f6"`` or ``"d5"``

    Everything else (full sentences, game references, explanations) is
    treated as commentary.

    Parameters
    ----------
    line:
        A single stripped line of text.
    """
    stripped = line.strip()
    if not stripped:
        return False
    if _MOVE_NUMBER_RE.match(stripped):
        return False
    if _MOVE_TOKEN_RE.match(stripped):
        return False
    # If it contains a space and is reasonably long, it's commentary.
    if " " in stripped and len(stripped) > 10:
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# PREFIX LENGTH
# ─────────────────────────────────────────────────────────────────────────────

def find_prefix_length(curr_lines: list[str], prev_lines: list[str]) -> int:
    """Return the number of leading lines that *curr_lines* and *prev_lines* share.

    Comparison is done after stripping surrounding whitespace from each line.
    The search stops at the first differing line.

    Parameters
    ----------
    curr_lines:
        Lines of the current (derivative) file.
    prev_lines:
        Lines of the immediately preceding file.

    Returns
    -------
    int
        0 if the very first lines differ, ``min(len(curr), len(prev))`` if
        every line in the shorter list matches.
    """
    count = 0
    for a, b in zip(curr_lines, prev_lines):
        if a.strip() == b.strip():
            count += 1
        else:
            break
    return count


# ─────────────────────────────────────────────────────────────────────────────
# LOAD & NORMALISE
# ─────────────────────────────────────────────────────────────────────────────

def load_folder(folder_path: str | Path) -> list[tuple[str, list[str]]]:
    """Load all ``.txt`` files in *folder_path*, sorted alphabetically.

    Returns a list of ``(filename, lines)`` tuples where *lines* is a list
    of non-empty stripped strings.

    Parameters
    ----------
    folder_path:
        Path to the folder containing the ``.txt`` source files.
    """
    folder = Path(folder_path)
    results: list[tuple[str, list[str]]] = []
    for txt_file in sorted(folder.glob("*.txt")):
        lines = [
            ln.strip()
            for ln in txt_file.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
        results.append((txt_file.name, lines))
    return results


def strip_alternatives(lines: list[str]) -> list[str]:
    """Remove "alternative" blocks from *lines*.

    An alternative block starts when a line (case-insensitively) begins with
    one of the phrases in ``_ALTERNATIVE_STARTERS``.  The block ends at the
    next numbered move annotation (``"1."``, ``"3..."`` etc.) or at a line
    that is clearly a chess-move token, signalling a return to the main line.

    Parameters
    ----------
    lines:
        Raw lines from a source file (already stripped of surrounding blanks).

    Returns
    -------
    list[str]
        Lines with alternative blocks removed.
    """
    cleaned: list[str] = []
    skip = False
    for line in lines:
        lower = line.lower()
        # Start of an alternative block
        if any(lower.startswith(starter) for starter in _ALTERNATIVE_STARTERS):
            skip = True
            continue
        # End of a skipped block: a move-number annotation signals we're back
        if skip:
            if _MOVE_NUMBER_RE.match(line.strip()) or _MOVE_TOKEN_RE.match(line.strip()):
                skip = False
            else:
                continue
        cleaned.append(line)
    return cleaned


# ─────────────────────────────────────────────────────────────────────────────
# BUILD master.txt
# ─────────────────────────────────────────────────────────────────────────────

def _repeated_commentary(
    curr_lines: list[str], prev_lines: list[str], prefix_len: int
) -> set[int]:
    """Return a set of indices in *curr_lines* (after *prefix_len*) that are
    repeated commentary present in the same relative position in *prev_lines*.

    Only lines **after** the shared prefix are candidates; within that tail
    section, commentary lines are compared against the corresponding line in
    the tail of *prev_lines* (by relative offset).
    """
    to_strip: set[int] = set()
    curr_tail = curr_lines[prefix_len:]
    prev_tail = prev_lines[prefix_len:]
    for rel_idx, (c_line, p_line) in enumerate(zip(curr_tail, prev_tail)):
        if c_line.strip() == p_line.strip() and is_commentary(c_line):
            to_strip.add(prefix_len + rel_idx)
    return to_strip


def build_master_txt(
    raw_files: list[tuple[str, list[str]]],
    output_path: str | Path,
    *,
    strip_repeated_commentary: bool = True,
) -> dict[int, list[str]]:
    """Merge all files into a single ``master.txt``.

    For FILE 1 every line is kept.  For each subsequent FILE N, commentary
    lines that appear identically (at the same relative position) in FILE N-1
    are removed.

    Parameters
    ----------
    raw_files:
        Output of :func:`load_folder` — a list of ``(filename, lines)`` tuples.
    output_path:
        Where to write ``master.txt``.
    strip_repeated_commentary:
        When *True* (default), repeated commentary lines are stripped.

    Returns
    -------
    dict[int, list[str]]
        Mapping of 1-based file index → processed lines (useful for Phase 3).
    """
    output_path = Path(output_path)
    processed: dict[int, list[str]] = {}
    lines_out: list[str] = []

    prev_lines: list[str] = []
    for file_idx, (fname, lines) in enumerate(raw_files, start=1):
        label = fname.replace(".txt", "")
        if strip_repeated_commentary and file_idx > 1:
            prefix_len = find_prefix_length(lines, prev_lines)
            to_strip = _repeated_commentary(lines, prev_lines, prefix_len)
            kept = [ln for i, ln in enumerate(lines) if i not in to_strip]
        else:
            kept = list(lines)

        processed[file_idx] = kept
        prev_lines = lines  # always compare against the *original* lines

        lines_out.append(f"===FILE {file_idx}=== {label}")
        lines_out.extend(kept)
        lines_out.append("")  # blank separator

    output_path.write_text("\n".join(lines_out), encoding="utf-8")
    return processed


# ─────────────────────────────────────────────────────────────────────────────
# PARSE master.txt
# ─────────────────────────────────────────────────────────────────────────────

def parse_master_txt(master_path: str | Path) -> dict[int, tuple[str, list[str]]]:
    """Parse ``master.txt`` into a mapping of file-index → (label, lines).

    Parameters
    ----------
    master_path:
        Path to the ``master.txt`` produced by :func:`build_master_txt`.

    Returns
    -------
    dict[int, tuple[str, list[str]]]
        ``{1: ("file-1", [...lines...]), 2: ("file-2", [...lines...]), ...}``
    """
    master_path = Path(master_path)
    raw = master_path.read_text(encoding="utf-8").splitlines()

    result: dict[int, tuple[str, list[str]]] = {}
    current_idx: int | None = None
    current_label = ""
    current_lines: list[str] = []

    for line in raw:
        m = _SECTION_HEADER_RE.match(line.strip())
        if m:
            # Save previous section
            if current_idx is not None:
                result[current_idx] = (current_label, [ln for ln in current_lines if ln])
            current_idx = int(m.group(1))
            current_label = m.group(2).strip()
            current_lines = []
        elif current_idx is not None:
            current_lines.append(line.strip())

    if current_idx is not None:
        result[current_idx] = (current_label, [ln for ln in current_lines if ln])

    return result


# ─────────────────────────────────────────────────────────────────────────────
# BUILD SEGMENTS
# ─────────────────────────────────────────────────────────────────────────────

def _assign_speed(line: str, *, is_prefix: bool, is_main_line: bool) -> float:
    """Return the TTS speed for a single *line*.

    Parameters
    ----------
    line:
        The text of the line.
    is_prefix:
        True if the line belongs to the shared prefix of a derivative file.
    is_main_line:
        True if the file is a main-line file (all segments use SPEED_MOVE).
    """
    if is_main_line:
        return SPEED_MOVE
    if is_prefix:
        return SPEED_PREFIX
    # Tail of a derivative file
    if is_commentary(line) and len(line) > LONG_COMMENT_THRESHOLD:
        return SPEED_LONG_COMMENT
    return SPEED_MOVE


def _combine_move_numbers(lines: Iterable[str]) -> list[str]:
    """Merge bare move-number tokens with the following move line.

    For example::

        ["1.", "d4", "Knight to f6", "2.", "c4"]
        →  ["1. d4", "Knight to f6", "2. c4"]

    This produces cleaner TTS output where the move number and move are read
    together.
    """
    result: list[str] = []
    pending: str | None = None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _MOVE_NUMBER_RE.match(stripped):
            pending = stripped
        elif pending is not None:
            result.append(f"{pending} {stripped}")
            pending = None
        else:
            result.append(stripped)
    if pending is not None:
        result.append(pending)
    return result


def build_segments_for_file(
    file_lines: list[str],
    *,
    is_main_line: bool,
    prev_lines: list[str] | None = None,
) -> list[tuple[str, float]]:
    """Convert a list of chess lines into ``(text, speed)`` TTS segments.

    Parameters
    ----------
    file_lines:
        Non-empty lines of the chess file (after commentary stripping if needed).
    is_main_line:
        When *True*, every segment is assigned :data:`SPEED_MOVE` (1.12).
        When *False*, the shared prefix with *prev_lines* gets
        :data:`SPEED_PREFIX` (1.45) and the tail follows the move/comment
        split rules.
    prev_lines:
        Lines of the immediately preceding file.  Required (and used) only
        when *is_main_line* is *False*.

    Returns
    -------
    list[tuple[str, float]]
        Ready-to-use ``FILES`` entry segments for the TTS script.
    """
    combined = _combine_move_numbers(file_lines)
    if is_main_line or prev_lines is None:
        return [(text, SPEED_MOVE) for text in combined]

    # Compute prefix length on the *combined* (merged move-number) lines so
    # that the prefix boundary is consistent with how lines actually appear.
    combined_prev = _combine_move_numbers(prev_lines)
    prefix_len = find_prefix_length(combined, combined_prev)

    segments: list[tuple[str, float]] = []
    for idx, text in enumerate(combined):
        speed = _assign_speed(text, is_prefix=(idx < prefix_len), is_main_line=False)
        segments.append((text, speed))
    return segments


# ─────────────────────────────────────────────────────────────────────────────
# BUILD ALL FILES
# ─────────────────────────────────────────────────────────────────────────────

def build_all_files(
    parsed: dict[int, tuple[str, list[str]]],
    main_line_indices: set[int],
    naming_fn: Callable[[int, str], str],
) -> Generator[tuple[str, list[tuple[str, float]]], None, None]:
    """Yield ``(mp3_name, segments)`` for every file in *parsed*.

    "Main-line" detection can be provided explicitly via *main_line_indices*.
    If an index is not listed there but its prefix length vs the previous file
    is shorter than 6 lines, it is also treated as a main-line file
    automatically.

    Parameters
    ----------
    parsed:
        Output of :func:`parse_master_txt`:
        ``{file_idx: (label, lines), ...}`` with 1-based integer keys.
    main_line_indices:
        Set of 1-based file indices that should be treated as main-line files
        (all segments at :data:`SPEED_MOVE`).  Typically the first file in
        each opening sub-group (e.g. ``{1, 6}`` for a 5-file Bd2 group
        followed by a 14-file Nf3 group).
    naming_fn:
        Callable ``(file_index: int, label: str) -> str`` that returns the
        desired MP3 filename for the given file.

    Yields
    ------
    tuple[str, list[tuple[str, float]]]
        ``(mp3_filename, [(text, speed), ...])`` — the exact structure used
        by ``generate_chess_mp3_final.py``.
    """
    prev_lines: list[str] = []
    for file_idx in sorted(parsed.keys()):
        label, lines = parsed[file_idx]
        mp3_name = naming_fn(file_idx, label)

        # Determine whether this is a main-line file.
        if file_idx in main_line_indices:
            is_main = True
        elif file_idx == min(parsed.keys()):
            # Always treat the very first file as main-line.
            is_main = True
        elif prev_lines and find_prefix_length(lines, prev_lines) < 6:
            # Very short shared prefix → treat as a new main line.
            is_main = True
        else:
            is_main = False

        segments = build_segments_for_file(
            lines,
            is_main_line=is_main,
            prev_lines=prev_lines if not is_main else None,
        )
        yield mp3_name, segments
        prev_lines = lines


# ─────────────────────────────────────────────────────────────────────────────
# CONVENIENCE: parse "new files" style source (===FILE N=== headers)
# ─────────────────────────────────────────────────────────────────────────────

def parse_new_files_source(source_path: str | Path) -> dict[int, tuple[str, list[str]]]:
    """Parse a combined source file that uses ``===FILE N=== <label>`` headers.

    This is the format used by
    ``Rubinstein System 4.e3 O-O 5.Bd2 & Nf3/new files`` in this repository.
    It is equivalent to :func:`parse_master_txt` but accepts the slightly
    different header style (no spaces around ``===``).

    Parameters
    ----------
    source_path:
        Path to the combined source file.

    Returns
    -------
    dict[int, tuple[str, list[str]]]
        Same structure as :func:`parse_master_txt`.
    """
    # The "new files" format is: ===FILE N=== Label (no spaces around ===)
    header_re = re.compile(r"^===FILE\s+(\d+)===\s*(.*)$")
    source_path = Path(source_path)
    raw = source_path.read_text(encoding="utf-8").splitlines()

    result: dict[int, tuple[str, list[str]]] = {}
    current_idx: int | None = None
    current_label = ""
    current_lines: list[str] = []

    for line in raw:
        m = header_re.match(line.strip())
        if m:
            if current_idx is not None:
                result[current_idx] = (current_label, [ln for ln in current_lines if ln.strip()])
            current_idx = int(m.group(1))
            current_label = m.group(2).strip()
            current_lines = []
        elif current_idx is not None:
            stripped = line.strip()
            if stripped:
                current_lines.append(stripped)

    if current_idx is not None:
        result[current_idx] = (current_label, [ln for ln in current_lines if ln.strip()])

    return result


# ─────────────────────────────────────────────────────────────────────────────
# CLI DEMO
# ─────────────────────────────────────────────────────────────────────────────

def _demo_from_new_files(source_path: str | Path, main_line_indices: set[int]) -> None:
    """Print the generated FILES list to stdout.

    This is a quick sanity-check you can run from the command line::

        python tools/build_master_and_tts.py \\
            "Rubinstein System 4.e3 O-O 5.Bd2 & Nf3/new files" \\
            1 6
    """
    parsed = parse_new_files_source(source_path)

    def naming_fn(idx: int, label: str) -> str:
        return label.strip() + ".mp3"

    print("FILES = [")
    for mp3_name, segments in build_all_files(parsed, main_line_indices, naming_fn):
        print(f"    (")
        print(f"        {mp3_name!r},")
        print(f"        [")
        for text, speed in segments:
            print(f"            ({text!r}, {speed}),")
        print(f"        ],")
        print(f"    ),")
    print("]")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print(
            "Usage: python tools/build_master_and_tts.py <source_file> [main_line_idx ...]\n"
            "Example:\n"
            '  python tools/build_master_and_tts.py '
            '"Rubinstein System 4.e3 O-O 5.Bd2 & Nf3/new files" 1 6'
        )
        sys.exit(1)

    source = sys.argv[1]
    main_indices = {int(x) for x in sys.argv[2:]} if len(sys.argv) > 2 else {1}
    _demo_from_new_files(source, main_indices)
