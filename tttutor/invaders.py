"""Letter Invaders — faithful reimplementation of Typing Tutor IV's game.

The original game (TT.EXE, 1987) is a word-based Space Invaders variant:

* A round has up to 40 falling words.  Words drift down one row at a time.
* New words appear only when their *first key* is not already in use.
* Typing the first letter locks onto the word; the remaining letters must be
  typed exactly.  A wrong letter costs 10 points and cancels the lock.
* A word that reaches the ground destroys as many shield cells as it has
  letters.  The shield has 80 cells.  If it reaches zero the player is out.
* Scoring is 10 + 20 + 30 ... for the 1st, 2nd, 3rd ... letter, i.e.
  ``5 * len * (len + 1)``.  Boomlets and Word Ships score double.
* Round 2 introduces Boomlets (single letters that fall fast), round 3
  introduces Word Ships (long words that race across the screen).
* Accuracy is ``hits / (hits + misses)``.  Above 90% the player receives an
  accuracy bonus of ``(accuracy - 90) * hits``.
* A two-player game alternates players after each round.
* Top-five scores are kept separately for Practice Keys and Full Keyboard.

This module is UI-independent: it exposes a deterministic state machine plus a
small rendering helper.  The curses layer in ``ui.py`` consumes it.
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence


# The teaching order used by Typing Tutor IV (from the EXE's key-order table
# at DS:0x7a53).  The game's "Practice Keys" mode only uses a prefix of it.
KEY_ORDER = (
    "asdfjkl;eit.nro,hcpumygwvbxqz"
    "':\"?!()-4738291056=$+%&*#@<>/[]{}^_"
)

# Keyboard physical-key mapping: characters that share a key.  The original
# maps both cases and shifted symbols to the same key index so that only one
# word can start with a given physical key at a time.
def key_for_char(ch: str) -> str:
    if len(ch) != 1:
        return ch
    if "a" <= ch <= "z":
        return ch
    if "A" <= ch <= "Z":
        return ch.lower()
    pairs = {
        "!": "1", "@": "2", "#": "3", "$": "4", "%": "5",
        "^": "6", "&": "7", "*": "8", "(": "9", ")": "0",
        "_": "-", "+": "=", "{": "[", "}": "]", "|": "\\",
        ":": ";", '"': "'", "<": ",", ">": ".", "?": "/",
        "~": "`",
    }
    return pairs.get(ch, ch)


# A compact English word pool.  The original ships a compressed corpus; the
# exact words are not important for faithful *behaviour*, but the pool is
# deliberately rich and includes short words for the practice levels.
_WORDS = """
a an am as at be by do go he if in is it me my no of on or so to up us we
add age ago aid aim air all and ant any are arm art ask bad bag ban bar bat
bed bee beg bet bid big bit box boy bug bus but buy cab can car cat cop cow
cry cup cut dad day did die dig dog dry due ear eat egg end eye fan far fat
few fig fit fix fly for fox fun fur gas get got gum gun guy had has hat her
him his hit hoe hog hop hot how hub hug ice ill ink inn ion its jam jar job
jog joy jug key kid kin kit lab lad lag lap law lay leg let lid lie lip log
lot low mad man map mat may men met mix mom mop mud mug nap net new nit nod
nor not now nut oak oar odd off oil old one opt orb ore our out owe own pad
pan par pat paw pay pea pen pet pie pig pin pit pod pop pot pro pry pub pun
pup put rag ran rat raw ray red rib rid rig rim rip rob rod rot row rub rug
run sad sag sap sat saw say sea see set sew she shy sin sip sir sit six ski
sky sly sob sod son sow soy spa spy sum sun tab tag tan tap tar tax tea ten
the tie tin tip toe ton too top tow toy try tub tug two urn use van vat vet
via vie vow wag war was wax way web wed wet who why wig win wit woe wok won
wow yak yam yes yet you zip zoo
able acid aged also area army away baby back ball band bank base bath beam
bean bear beat beef been beer bell belt bend best bike bill bird blow blue
boat body boil bold bomb bond bone book boot born boss both bowl brew brow
bulk burn bush busy cake call calm came camp cane card care case cash cast
cave cell chat chip city clad claw clay clip club coal coat code coil coin
cold come cook cool cope copy cord core corn cost cove crab crew crib crop
crow cube curl dark dart dash data date dawn deal dear debt deck deed deep
deer desk dial dice diet dirt dish dive dock does dome door dose down draw
drew drop drum dual duck dull dust duty each earn ease east easy echo edge
else even ever evil exam exit face fact fade fail fair fall fame farm fast
fate fear feed feel feet fell felt fern file fill film find fine fire firm
fish fist five flag flat flea fled flee flew flex flip flow foam fold folk
food fool foot ford form fort four free frog from fuel full fund gain game
gate gave gear gene gift girl give glad glass gleam glide glob glove glow
goal goat goes gold golf gone good gown grab gram gray grew grid grim grin
grip grow gulf hail hair half hall hand hang hard harm harp hate haul have
hawk hay head heal heap hear heat held hell helm help herb herd here hero
hide high hill hint hire hold hole holy home hook hope horn hose host hour
huge hunt hurt idea inch into iron item jack jade jail jazz jeep join joke
jump june jury just keen keep kept kick kind king kiss kite knee knew knit
knob knot know lack lady laid lake lamb lamp land lane last late lava lawn
lazy lead leaf lean leap left lend lens less lied life lift like limb lime
line link lion list live load loan lock loft logo long look loop lord lose
loss lost loud love luck lung made mail main make male mall mane many map
mark mars mask mass mast mate math meal mean meat meet meld melt menu mere
mesh mess mild mile milk mill mind mine mint miss mist mode mold mole monk
mood moon more moss most move much mule myth nail name navy near neck need
nest news next nice nine node none noon norm nose note noun nova numb obey
odds once only onto open oral oven over pace pack page paid pail pain pair
pale palm park part pass past path pave peak pear peck peer pick pile pill
pine pink pipe plan play plea plot plow plug plus poem poet pole poll pond
pool poor pope pork port pose post pour pray prey pull pump pure push quad
quit race rack raid rail rain rake ramp rank rare rash rate read real reap
rear reed reef rest rice rich ride ring rise risk road roam roar robe rock
role roll roof room root rope rose rule rush rust safe sail salt same sand
sane sang save scan scar seal seat seed seek seem seen self sell send sent
ship shoe shop shot show shut sick side sign silk sing sink site size skin
slab slam slap sled slip slot slow snap snow soak soap soar sock soda soft
soil sold sole solo some song soon sort soul soup sour spin spot star stay
stem step stew stir stop such suit sure swim tack tail take tale talk tall
tank tape task team tear tell tend tent term test text than that them then
they thin this thus tide tidy tile till time tiny tire toad toll tone tool
torn toss tour town trap tree trim trip true tune turn twin type unit upon
urge used user vary vase vast vein verb very veto view vine void vote wait
wake walk wall want warm warn wash wave weak wear week well went were west
what when whim whip whom wide wife wild will wind wine wing wire wise wish
with wolf wood wool word wore work worm worn wrap yard yarn year yell your
zero zone
"""

WORDS = sorted({w for w in _WORDS.split() if w.isalpha()})


def _load_original_corpus() -> list[str]:
    """Load the bit-exact corpus extracted from TT.EXE.

    The JSON is generated by ``tools/extract_word_corpus.py`` from
    ``DS:0x214e`` / ``DS:0x2992``.  We keep the built-in fallback so the
    clone still works if the data file is absent.
    """
    path = Path(__file__).resolve().parent / "data" / "tt_word_corpus.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        words = {e["word"] for e in raw.get("entries", []) if e.get("word")}
        return sorted(words)
    except Exception:
        return []


ORIGINAL_WORDS = _load_original_corpus()


@dataclass
class Word:
    """One falling word on the playfield."""
    text: str
    kind: int                  # 1 = normal, 2 = boomlet, 3 = word ship
    x: int
    y: int
    speed: int = 12            # ticks between downward steps
    phase: int = 0
    typed: int = 0
    key: str = ""
    alive: bool = True
    move_counter: int = 0

    @property
    def height(self) -> int:
        return len(self.text)

    @property
    def double_score(self) -> bool:
        return self.kind != 1


@dataclass
class ScoreEntry:
    name: str
    score: int
    keys: int
    date: str


class HighScores:
    """Top-five tables for the two game levels.

    Stored as JSON next to the history file.  The original uses a binary
    ``fzvf.txt``; we deliberately use a separate file so that running the
    clone cannot corrupt the 1987 program's high-score file.
    """

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else Path.home() / ".tttutor" / "fzvf.json"
        self.tables: dict[str, list[ScoreEntry]] = {"practice": [], "full": []}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for key in ("practice", "full"):
                self.tables[key] = [ScoreEntry(**e) for e in raw.get(key, [])]
        except Exception:
            self.tables = {"practice": [], "full": []}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {k: [e.__dict__ for e in v] for k, v in self.tables.items()}
        self.path.write_text(json.dumps(data, indent=1), encoding="utf-8")

    def add(self, level: int, name: str, score: int, keys: int) -> bool:
        table = self.tables["practice" if level == 0 else "full"]
        entry = ScoreEntry(
            name=(name or "(anonymous)")[:26],
            score=int(score),
            keys=int(keys),
            date=time.strftime("%m-%d-%y"),
        )
        table.append(entry)
        table.sort(key=lambda e: e.score, reverse=True)
        del table[5:]
        self.save()
        return entry in table

    def top(self, level: int) -> list[ScoreEntry]:
        return list(self.tables["practice" if level == 0 else "full"])

    def delete(self, name: str) -> int:
        removed = 0
        for key in ("practice", "full"):
            before = len(self.tables[key])
            self.tables[key] = [e for e in self.tables[key] if e.name != name]
            removed += before - len(self.tables[key])
        self.save()
        return removed


class LetterInvaders:
    """Deterministic state machine for one game."""

    PLAYFIELD_WIDTH = 80
    PLAYFIELD_HEIGHT = 18
    GROUND_ROW = 18
    SHIELD_CELLS = 80
    MAX_WORDS_PER_ROUND = 40
    TICK_MS = 120

    def __init__(
        self,
        *,
        level: int = 0,
        players: int = 1,
        names: Optional[Sequence[str]] = None,
        learned_keys: str = "asdfjkl;",
        rng: Optional[random.Random] = None,
        max_words_per_round: int = MAX_WORDS_PER_ROUND,
    ):
        self.level = 0 if level == 0 else 1
        self.players = 1 if players == 1 else 2
        self.names = list(names or ["Player 1"])
        while len(self.names) < self.players:
            self.names.append(f"Player {len(self.names) + 1}")
        self.learned_keys = learned_keys or "asdfjkl;"
        self.rng = rng or random.Random()
        self.max_words_per_round = max_words_per_round

        self.round = 1
        self.current_player = 0
        self.scores = [0, 0]
        self.shields = [self.SHIELD_CELLS, self.SHIELD_CELLS]
        self.shield_grid = [[True] * self.SHIELD_CELLS for _ in range(2)]
        self.hits = [0, 0]
        self.misses = [0, 0]
        self.accuracy_bonus = 0
        self.eliminated = [False, False]
        self.round_hits = 0
        self.round_misses = 0
        self.round_spawned = 0
        self.round_destroyed = 0
        self.active: list[Word] = []
        self.explosions: list[tuple[int, int, str, int]] = []
        self.current_word: Optional[Word] = None
        self.game_over = False
        self.round_over = False
        self.last_feedback = ""
        self._tick_accum = 0
        self._tick = 0
        self._spawn_cooldown = 10
        self._pool: list[str] = []
        self.stream_index = self._choose_stream_index()
        self._refresh_pool()
        self._start_round()

    def _choose_stream_index(self) -> int:
        """Pick a TT text stream for the current lesson state.

        The original FUN_1000_5854 selects among the 51 streams based on the
        learned-key count and a random distribution.  We use the same rough
        progression: early lessons use the name/place streams, later lessons
        use the general vocabulary streams.
        """
        if self.level == 1:
            return self.rng.randrange(51)
        learned = len(self.learned_keys or "")
        return min(50, max(0, learned // 2))

    def _template_words(self) -> list[str]:
        """Words produced by the original token/macro text streams."""
        try:
            from .original_text import TemplateRenderer
            renderer = TemplateRenderer(self.rng, self._allowed_chars())
            return renderer.render_words(self.stream_index, limit=300)
        except Exception:
            return []

    # ---- configuration -------------------------------------------------
    @property
    def spawn_interval(self) -> int:
        # Original starts at 20 ticks and drops to a floor of 3.
        return max(3, 21 - self.round)

    @property
    def normal_speed(self) -> int:
        # Original starts at 12 and drops to 6 from round 4 onward.
        return max(6, 13 - self.round)

    @property
    def player_name(self) -> str:
        return self.names[self.current_player]

    @property
    def shield(self) -> int:
        return self.shields[self.current_player]

    @property
    def score(self) -> int:
        return self.scores[self.current_player]

    @property
    def accuracy(self) -> float:
        total = self.round_hits + self.round_misses
        return (self.round_hits / total * 100.0) if total else 0.0

    # ---- word generation ----------------------------------------------
    def _allowed_chars(self) -> str:
        if self.level == 1:
            return (
                "abcdefghijklmnopqrstuvwxyz"
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                "0123456789"
                "',.;:-_+=!@#$%^&*()[]{}<>/?\\\" "
            )
        # Practice mode follows the TT teaching order; letters are allowed
        # in both cases once the key has been learned.
        out = [" "]
        for ch in self.learned_keys:
            if ch.isalpha():
                out.extend([ch.lower(), ch.upper()])
            else:
                out.append(ch)
        return "".join(dict.fromkeys(out))

    def _word_fits(self, word: str) -> bool:
        allowed = set(self._allowed_chars())
        return all(ch in allowed for ch in word)

    def _refresh_pool(self) -> None:
        allowed = set(self._allowed_chars())
        source = ORIGINAL_WORDS or WORDS
        if self.level == 1:
            corpus = [w for w in source if 1 <= len(w) <= 14]
        else:
            corpus = [w for w in source
                      if 1 <= len(w) <= 14 and all(c in allowed for c in w)]
        template = [w for w in self._template_words()
                    if 1 <= len(w) <= 14 and all(c in allowed for c in w)
                    and "'s" not in w[1:-1]]
        # Template words are the original stream's content; the corpus pool
        # supplies enough breadth for a full 40-word round.
        pool = list(dict.fromkeys(template + corpus))
        if len(pool) < 20:
            pool = corpus or ["as", "ad", "fa", "ja", "ka", "la", "sad", "lad", "dad"]
        self.rng.shuffle(pool)
        self._pool = pool

    def _next_word(self) -> Optional[str]:
        for _ in range(200):
            if not self._pool:
                self._refresh_pool()
            word = self._pool.pop()
            if not self._word_fits(word):
                continue
            key = key_for_char(word[0])
            if any(w.key == key for w in self.active):
                continue
            return word
        return None

    # ---- round lifecycle ----------------------------------------------
    def _start_round(self) -> None:
        self.round_over = False
        self.round_hits = 0
        self.round_misses = 0
        self.round_spawned = 0
        self.round_destroyed = 0
        self.active.clear()
        self.current_word = None
        self.explosions.clear()
        self._tick = 0
        self._tick_accum = 0
        self._spawn_cooldown = 8
        self.last_feedback = ""
        self._refresh_pool()

    def next_round(self) -> None:
        self.round += 1
        self._start_round()

    def switch_player(self) -> None:
        self.current_player = 1 - self.current_player
        self._start_round()

    def begin_turn(self, player: int, *, increment_round: bool = False) -> None:
        """Start a specific player's turn, optionally advancing the round."""
        if increment_round:
            self.round += 1
        self.current_player = 0 if player == 0 else 1
        self._start_round()

    def end_round(self) -> dict:
        """Finalise the round, award the accuracy bonus, return a summary."""
        if self.round_over:
            return self.round_summary()
        self.round_over = True
        acc = self.accuracy
        bonus = 0
        if acc > 90.0:
            bonus = int((acc - 90.0) * self.round_hits)
            self.scores[self.current_player] += bonus
        self.accuracy_bonus = bonus
        self.hits[self.current_player] += self.round_hits
        self.misses[self.current_player] += self.round_misses
        if self.shields[self.current_player] <= 0:
            self.eliminated[self.current_player] = True
        self.game_over = all(self.eliminated[p] for p in range(self.players))
        return self.round_summary()

    def round_summary(self) -> dict:
        return {
            "round": self.round,
            "player": self.current_player,
            "player_name": self.player_name,
            "hits": self.round_hits,
            "misses": self.round_misses,
            "accuracy": self.accuracy,
            "accuracy_bonus": self.accuracy_bonus,
            "score": self.scores[self.current_player],
            "shield": max(0, self.shields[self.current_player]),
            "eliminated": self.eliminated[self.current_player],
            "game_over": self.game_over,
        }

    # ---- simulation ---------------------------------------------------
    def advance(self, dt_ms: int) -> None:
        """Advance the clock by ``dt_ms`` milliseconds.

        The delta is capped at one second so that suspending the terminal
        cannot make the simulation run thousands of ticks in one call.
        """
        if self.game_over or self.round_over:
            return
        self._tick_accum += min(max(0, dt_ms), 1000)
        while self._tick_accum >= self.TICK_MS:
            self._tick_accum -= self.TICK_MS
            self._do_tick()

    def _do_tick(self) -> None:
        self._tick += 1
        # Move words.
        for w in list(self.active):
            if not w.alive:
                continue
            if w.kind == 3:
                # Word Ships race left every other tick.
                if self._tick % 2 == 0:
                    w.x -= 1
                    if w.x + len(w.text) < 0:
                        w.alive = False
                        self.active.remove(w)
                        if self.current_word is w:
                            self.current_word = None
                continue
            w.move_counter += 1
            period = 3 if w.kind == 2 else w.speed
            if w.move_counter >= period:
                w.move_counter = 0
                w.y += 1
                if w.y >= self.GROUND_ROW:
                    self._ground_hit(w)
        # Explosions.
        self.explosions = [
            (x, y, ch, ttl - 1) for (x, y, ch, ttl) in self.explosions if ttl > 1
        ]
        # Spawn.
        if self.round_spawned < self.max_words_per_round and not self.round_over:
            self._spawn_cooldown -= 1
            if self._spawn_cooldown <= 0 and len(self.active) < 12:
                if self._spawn_word():
                    self._spawn_cooldown = self.spawn_interval
                else:
                    self._spawn_cooldown = 2
        # Round complete when all words have appeared and the field is clear.
        if (
            self.round_spawned >= self.max_words_per_round
            and not self.active
            and not self.round_over
        ):
            self.end_round()

    def _spawn_word(self) -> bool:
        text = self._next_word()
        if not text:
            return False
        kind = 1
        # Boomlets appear from round 2, Word Ships from round 3.
        has_special = any(w.kind != 1 for w in self.active)
        if self.round >= 2 and not has_special and len(text) == 1 and self.rng.random() < 0.35:
            kind = 2
        elif self.round >= 3 and not has_special and len(text) >= 4 and self.rng.random() < 0.25:
            kind = 3
        # Occasionally present the first letter in upper case, as the
        # original does when teaching Shift.
        if kind != 3 and self.rng.random() < 0.25:
            text = text[0].upper() + text[1:]
        if kind == 3:
            x = self.PLAYFIELD_WIDTH - 1
        else:
            max_x = max(0, self.PLAYFIELD_WIDTH - len(text))
            x = self.rng.randint(0, max_x)
            # Avoid overlapping an existing word on the same row.
            for _ in range(8):
                if not any(
                    w.kind != 3 and abs(w.x - x) < max(len(w.text), len(text)) and abs(w.y) < 2
                    for w in self.active
                ):
                    break
                x = self.rng.randint(0, max_x)
        w = Word(
            text=text,
            kind=kind,
            x=x,
            y=0,
            speed=self.normal_speed,
            key=key_for_char(text[0]),
            move_counter=0,
        )
        self.active.append(w)
        self.round_spawned += 1
        return True

    # ---- typing -------------------------------------------------------
    def type_char(self, ch: str) -> dict:
        """Process one typed character.  Returns a small event dict."""
        event = {"hit": False, "miss": False, "word": None, "score": 0, "msg": ""}
        if self.game_over or self.round_over or not ch:
            return event
        if self.current_word is None:
            # The original ignores Enter/Space when no word is locked on.
            if ch in (" ", "\r", "\n"):
                return event
            # Find a word whose first character matches.  The original
            # requires the key lane to be free and picks the corresponding
            # word; we do the same by key.
            key = key_for_char(ch)
            candidates = [w for w in self.active if w.key == key and w.text[0] == ch]
            if not candidates:
                # FUN_1000_9f66 calls FUN_1000_9ecc for every unmatched key,
                # including a key that has no active word.
                self.round_misses += 1
                self.scores[self.current_player] = max(
                    0, self.scores[self.current_player] - 10)
                event.update(miss=True, msg="Miss! -10")
                return event
            w = candidates[0]
            self.current_word = w
            w.typed = 1
            self.round_hits += 1
            event.update(hit=True, word=w, msg=f"{ch}")
            if w.typed >= len(w.text):
                event["score"] = self._finish_word(w)
                event["word"] = w
            return event
        w = self.current_word
        if w.typed < len(w.text) and ch == w.text[w.typed]:
            w.typed += 1
            self.round_hits += 1
            event.update(hit=True, word=w)
            if w.typed >= len(w.text):
                event["score"] = self._finish_word(w)
            return event
        # Wrong key: 10-point penalty, cancel the lock, keep the word.
        self.current_word = None
        w.typed = 0
        self.round_misses += 1
        self.scores[self.current_player] = max(0, self.scores[self.current_player] - 10)
        event.update(miss=True, msg=f"Miss! -10")
        return event

    def _finish_word(self, w: Word) -> int:
        n = len(w.text)
        base = 5 * n * (n + 1)
        points = base * (2 if w.double_score else 1)
        self.scores[self.current_player] += points
        self.round_destroyed += 1
        self.explosions.append((w.x + n // 2, w.y, "*", 6))
        if w in self.active:
            self.active.remove(w)
        if self.current_word is w:
            self.current_word = None
        return points

    def _ground_hit(self, w: Word) -> None:
        if w in self.active:
            self.active.remove(w)
        if self.current_word is w:
            self.current_word = None
        n = len(w.text)
        cells = 0
        grid = self.shield_grid[self.current_player]
        for x in range(max(0, w.x), min(self.PLAYFIELD_WIDTH, w.x + n)):
            if grid[x]:
                grid[x] = False
                cells += 1
        self.shields[self.current_player] = max(0, self.shields[self.current_player] - cells)
        self.scores[self.current_player] = max(0, self.scores[self.current_player] - 10)
        self.round_misses += 1
        self.explosions.append((max(0, w.x + n // 2), self.GROUND_ROW - 1, "%", 6))
        if self.shields[self.current_player] <= 0:
            self.end_round()

    # ---- rendering ----------------------------------------------------
    def render(self) -> list[str]:
        """Return the playfield as text rows (no title/status rows)."""
        rows = [[" "] * self.PLAYFIELD_WIDTH for _ in range(self.PLAYFIELD_HEIGHT)]
        for w in self.active:
            if 0 <= w.y < self.PLAYFIELD_HEIGHT:
                for i, ch in enumerate(w.text):
                    x = w.x + i
                    if 0 <= x < self.PLAYFIELD_WIDTH:
                        rows[w.y][x] = ch
        for (x, y, ch, _ttl) in self.explosions:
            if 0 <= y < self.PLAYFIELD_HEIGHT and 0 <= x < self.PLAYFIELD_WIDTH:
                rows[y][x] = ch
        return ["".join(r) for r in rows]

    def shield_bar(self, width: int = 80) -> str:
        grid = self.shield_grid[self.current_player]
        if width == self.PLAYFIELD_WIDTH:
            return "".join("=" if ok else "." for ok in grid)
        cells = int(round(self.shields[self.current_player] / self.SHIELD_CELLS * width))
        return "=" * cells + "." * (width - cells)

    def status_line(self) -> str:
        return (
            f"Round {self.round}   Score: {self.scores[self.current_player]}   "
            f"Player: {self.player_name}   Hits: {self.round_hits}   "
            f"Misses: {self.round_misses}   Accuracy: {self.accuracy:.0f}%"
        )
