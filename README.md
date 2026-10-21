# tttutor

A modern terminal typing tutor — pure Python, stdlib only.

## Inspiration
Functionally inspired by classic 16-bit DOS typing tutors (the well-known
`Typing Tutor IV` from 1987 by Kriya Systems). tttutor reimplements the same
*concepts* — sequenced lessons, character-level accuracy tracking, WPM
computation, history persistence, a "Letter Invaders" mini-game — using a
modern Python stack instead of DOSBox + 16-bit real-mode code:

| Concept (TT IV)                       | tttutor                                  |
|---------------------------------------|------------------------------------------|
| Menu (Lessons/Tests/Reports/...)      | `App.menu_screen` with curses highlight  |
| Drill line with per-char feedback     | `TypingDrill` + `progress_chars`         |
| Profile & history (TT.HIS file)       | `history.py` — JSONL at `~/.tttutor/`     |
| Letter Invaders game                  | `invaders.py` — word-based, rounds,      |
|                                       | Boomlets, Word Ships, 2-player, shields  |
| Reports screen with WPM/accuracy      | per-key Speed/Accuracy graphs            |
| Instructor mode                       | `--instructor`, password, Encrypt,       |
|                                       | Delete, Composite reports                |

None of the TT IV source code is reproduced; this is a *fresh implementation*
inspired by the publicly documented feature set. `.TST` lesson files (which
are plain text) can be loaded directly via `--tst-dir`.

## 使用说明书
见 [MANUAL.md](MANUAL.md)（功能详解、游戏规则、教师模式、故障排除）。

## 安装
见 [INSTALL.md](INSTALL.md)。运行时零第三方依赖（纯标准库），
`requirements.txt` 仅在 Windows 原生环境需要 `windows-curses`：

```
pip install -r requirements.txt
pip install .        # 得到 tttutor 命令；或免安装直接 python start.py
```

## Run
```
python start.py                         # default TUI
python start.py --history ./history.jsonl
python start.py --tst-dir ./lessons
python start.py --instructor KRIYA      # Instructor Mode
python start.py --check                 # environment diagnostics
```

`start.py` is self-contained (stdlib only) and works in the conda
`spark13` environment as well as the system Python.

## Original compressed word corpus
The 1987 EXE stores its word corpus as a bit-packed stream at
`DS:0x214e` / `DS:0x2992` (46 lesson streams × 23 buckets). It has been
extracted bit-exactly:

```
python tools/extract_word_corpus.py /mnt/qdata1/tt/game/extracted/TT.EXE
```

Outputs:

* `tttutor/data/tt_word_corpus.json` — every entry with stream/bucket and
  its raw 5-bit letter codes.
* `tttutor/data/tt_word_corpus.txt` — one unique word per line.

Current extraction: **4019 entries / 3876 unique words / 0 decode errors**.
The game's Practice Keys mode filters this corpus by the student's learned
keys; Full Keyboard uses the whole corpus. Words are capped at 14 characters
to match TT.EXE's 15-byte word buffer. Observed original words such as
`sad`, `laf`, `fla`, `camp`, `kate`, `jessie`, `street` and `can` are all
present in the extracted set.

## Original lesson/text streams
The EXE also contains 51 token/macro streams at `DS:0x8632` / `DS:0x8698`.
They are expanded by `FUN_1000_64cc` with:

* literals and macro calls,
* word tokens backed by the corpus above,
* 44 content generators (names, addresses, phone numbers, dates, SSN,
  money, arithmetic and punctuation).

`tools/extract_text_streams.py` exports the exact stream structure to
`tttutor/data/tt_text_streams.json`.  `tttutor/original_text.py` is a Python
port of the renderer.  It is used for:

* the original Practice drills (words filtered by learned keys), and
* the game's word source (template words plus the corpus pool).

The stream structure and corpus words are bit-exact.  The content generators
(names/addresses/numbers) are ported from the decompiled routines but use
fresh random values on each render, just as the original does.

## TT.EXE-style rendering
The curses UI follows the original 80x25 layout:

* row 0: screen title (left) and user name (right)
* row 1: full-width dashed rule
* row 2: horizontal menu bar (`Lessons  Tests  Reports  Options  Game  Help  Quit`)
* row 3: submenu/description of the highlighted item
* rows 4+: green CP437 single-line frames for help and dialog content
* last row: `Esc -> ...` parent hint

Navigation uses left/right arrows or the space bar; Enter selects; typing the
first letter selects immediately, exactly as TT.EXE's menus do.  Dialogs place
their items in a nested green frame with a yellow-on-magenta selection bar.
Drills use the original three-frame layout: the drill line with `^`/`v`
pointers, the Current Focus Keys frame, and the Speed/Accuracy frame.  The game
keeps the original `Round / Score / user` header, 18-row playfield, shield row
and bottom `Esc -> ...` line.

## Architecture
```
tttutor/
  engine.py     — typing state and stats (no UI dependency)
  content.py    — built-in lessons
  lessons.py    — registry combining built-in + .TST on-disk lessons
  history.py    — JSONL session persistence
  invaders.py   — faithful Letter Invaders state machine
  settings.py   — persistent goals, drills, password, learned keys
  ui.py         — curses screens (menu, lessons, tests, reports, game, help)
  __main__.py   — CLI entry
```

## Cross-platform
The whole thing runs in any terminal that supports curses:
- Linux, BSD                — native
- macOS                      — native
- Windows                    — via WSL or any modern terminal that ships
  with libncurses (Windows Terminal + WSL, ConEmu with cygwin, etc.)

No native extension, no PyPI dependency, no platform-specific code.

## 鸣谢 / Credits
本项目为 **Python 复刻传统 DOS TT 打字游戏**（Typing Tutor IV, © 1987
Kriya Systems）的现代终端重制版。开发过程中使用 **DeepSeek V4.1 Flash**
大语言模型辅助完成逆向分析、功能复刻、代码重构与文档编写，特此鸣谢。

