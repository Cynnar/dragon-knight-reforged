# Dragon Knight — Combat & Progression Spec

Engine-neutral description of the game rules, reverse-engineered from the original
PHP source (`fight.php`, `explore.php`, `towns.php`, `heal.php`, `install.php`).
This is the **source of truth** for the Django port — implement against this document,
not the old code. All randomness uses inclusive integer ranges: `rand(a, b)` picks an
integer in `[a, b]`.

Notation: `floor`, `ceil`, `sqrt` are the usual math functions. Character stats
(`attackpower`, `defensepower`, `strength`, `dexterity`, `maxhp`, etc.) come from the
character record; monster stats come from `monsters.json`.

---

## 1. The world & movement

- The map is a grid indexed by `latitude` / `longitude`, ranging from `-gamesize` to
  `+gamesize` on each axis (`gamesize` default **250**, from `control.json`).
- Each move step changes latitude or longitude by ±1 (N/S = latitude, E/W = longitude),
  clamped to the map bounds.
- If the destination tile holds a town (matching lat/long in `towns.json`), the player
  enters that town instead of exploring.
- Otherwise, each step has a **1-in-5** chance of triggering a random encounter
  (`rand(1,5) == 1`). On a trigger, the character enters the `Fighting` state.

## 2. Encounter generation

When a fight begins (first round only):

1. Take absolute values of the character's latitude and longitude.
2. `max_mlevel = floor( max(|lat| + 5, |long| + 5) / 5 )`  → one monster tier per 5 tiles
   from the origin. Floor at 1.
3. `min_mlevel = max_mlevel - 2`, floored at 1.
4. Pick a random monster whose `level` is within `[min_mlevel, max_mlevel]`.
5. Monster starting HP = `rand( floor(maxhp * 4/5), maxhp )` — i.e. 80–100% of its `maxhp`.
6. Apply the difficulty modifier to that HP (see §7): `ceil(hp * diffmod)`.
7. Copy the monster's `immune` flag onto the fight state.

The world therefore gets harder the farther you travel from (0,0), regardless of direction.

## 3. Initiative (who strikes first)

```
player_roll  = rand(1,10) + ceil(sqrt(character.dexterity))
monster_roll = rand(1,7)  + ceil(sqrt(monster.maxdam))
player_first = player_roll > monster_roll
```

## 4. A combat round

Each round the player chooses an action (Attack, cast a spell, or Run). Then, if the
monster is still alive and awake, the monster attacks back.

### 4a. Player attack → damage to monster

```
tohit = ceil( rand(attackpower * 0.75, attackpower) / 3 )

# Excellent hit (crit): scales with strength
if rand(1,150) <= sqrt(strength):
    tohit *= 2

# Monster mitigation
toblock = ceil( rand(monster.armor * 0.75, monster.armor) / 3 )

# Monster dodge: scales with monster armor
if rand(1,200) <= sqrt(monster.armor):
    damage = 0            # monster dodges, no damage
else:
    damage = max(1, tohit - toblock)
    if buff_damage active (uberdamage %):
        damage += ceil(damage * uberdamage/100)

monster.hp -= damage
```

### 4b. Monster attack → damage to player

Only happens if the monster is awake (see §5 sleep).

```
tohit = ceil( rand(monster.maxdam * 0.5, monster.maxdam) )
tohit = ceil(tohit * diffmod)      # difficulty applies to incoming damage

toblock = ceil( rand(defensepower * 0.75, defensepower) / 4 )

# Player dodge: scales with dexterity
if rand(1,150) <= sqrt(dexterity):
    damage = 0            # player dodges
else:
    damage = max(1, tohit - toblock)
    if buff_defense active (uberdefense %):
        damage -= ceil(damage * uberdefense/100)
    damage = max(1, damage)

character.hp -= damage
```

Note the asymmetry: the player's block divisor is `/4`, the monster's is `/3`, and the
player's raw hit is divided by 3 while the monster's is not — the numbers are deliberately
tuned, so port the constants exactly.

### 4c. Running away

```
run_roll     = rand(4,10) + ceil(sqrt(dexterity))
monster_roll = rand(1,5)  + ceil(sqrt(monster.maxdam))
escaped = run_roll > monster_roll
```

On success the character returns to `Exploring` with no reward or penalty.

## 5. Spells

Spell `type` (see `spells.json` → `effect`) determines behavior. `attribute` means
different things per type; `mp_cost` is deducted on cast.

| effect          | behavior |
|-----------------|----------|
| `heal`          | Restore `attribute` HP, capped at `maxhp`. Castable in combat **and** from the quick-spell menu while exploring. |
| `damage`        | Deal `rand( floor(attribute*5/6), attribute )` to the monster. Blocked entirely if the monster is immune-to-damage-magic. |
| `sleep`         | Set the monster's sleep counter to `attribute` turns. No effect if the monster is immune-to-sleep. |
| `buff_damage`   | Set `uberdamage = attribute` (a % bonus to the player's melee damage) until the fight ends. |
| `buff_defense`  | Set `uberdefense = attribute` (a % reduction of incoming damage) until the fight ends. |

Characters know a comma-separated list of spell IDs; spells are learned on level-up (§6).

### Sleep wake check
At the start of the monster's turn, if it is asleep:
```
if rand(1,15) > sleep_counter:  monster wakes (counter -> 0)
else:                           monster stays asleep, skips its attack
```
Higher-tier sleep spells set a larger counter, so the monster stays down longer.

## 6. Victory, rewards & leveling

On monster death (`monster.hp <= 0`), the player may claim victory:

```
exp  = rand( floor(monster.maxexp  * 5/6), monster.maxexp  );  exp  = max(1, exp)
gold = rand( floor(monster.maxgold * 5/6), monster.maxgold );  gold = max(1, gold)

exp  = ceil(exp  * diffmod)          # difficulty scales reward up
gold = ceil(gold * diffmod)
exp  += ceil(exp  * expbonus/100)    # per-character bonus, default 0
gold += ceil(gold * goldbonus/100)
```

Both `experience` and `gold` are capped at **16,777,215** (the old MySQL mediumint max —
you can raise or drop this cap in the new schema).

### Level-up
Look up the row for `level + 1` in `levels.json`. If the character's new total experience
`>=` that row's `exp_required` **for their class**, they level up and gain that row's
per-class `hp_gain / mp_gain / tp_gain / strength_gain / dexterity_gain`. Additionally:

```
attackpower  += strength_gain      # attack tracks strength growth
defensepower += dexterity_gain     # defense tracks dexterity growth
```

If the level row has a non-null `spell_learned_id` for the class, append it to the
character's known-spells list. Max level is **100**.

At character creation (level 1) every class starts at `hp 15, mp 0, tp 10, strength 5,
dexterity 5, attackpower 5, defensepower 5, gold 100` (from the `users` table defaults),
then class-specific growth diverges via the level table.

### Item drops
Only checked on a victory that did **not** produce a level-up:
```
if rand(1,30) == 1:                # ~3.3% chance
    pick a random drop where drop.mlevel <= monster.level
    offer it to the player to reveal/equip
```

## 7. Difficulty

Chosen at character creation; stored per character. Modifiers come from `control.json`:

| difficulty | modifier | affects |
|------------|----------|---------|
| Easy       | ×1.0     | — |
| Medium     | ×1.2     | monster HP, monster damage, exp reward, gold reward |
| Hard       | ×1.5     | same |

So higher difficulty makes monsters tankier and hit harder, but pays out
proportionally more exp and gold.

## 8. Death

If `character.hp <= 0` during the monster's attack:
- Lose half of current gold: `gold = ceil(gold / 2)`.
- Revive with `hp = ceil(maxhp / 4)`.
- Fight ends; character is sent back to a safe state (original code routes to a
  recovery/town screen).

## 9. Classes

Three classes, from `control.json`: **Mage** (class 1), **Warrior** (class 2),
**Paladin** (class 3). They differ only through the per-class columns of the level
table (`levels.json` → `classes.{mage,warrior,paladin}`): different exp thresholds,
different stat gains per level, and different spells learned and when. Mage leans into
MP/spells, Warrior into HP/strength, Paladin is the hybrid. All combat formulas above
are class-agnostic — class only shapes the stat curve.

---

## Porting notes / gotchas

- **Rounding matters.** The original leans on `ceil` and integer division in specific
  places (block divisors `/3` vs `/4`, hit divisor `/3`). Preserve them or you'll shift
  game balance.
- **`sqrt` thresholds are the dodge/crit knobs.** Dodge and excellent-hit chances are
  `sqrt(stat)` against a `rand(1,150|200)` roll — low probability that grows slowly. Keep
  the roll ranges (150 for crit & player dodge, 200 for monster dodge) to preserve feel.
- **Reward floor of 1.** exp and gold are always at least 1 even against level-1 fodder.
- **Immunity encoding:** `immune` on a monster — 0 none, 1 immune to damage-magic,
  2 immune to sleep. (A monster can only be one in the original data; model it as a set
  in the new schema if you want richer immunities.)
- **Don't port the SQL or escaping.** All of §1–§8 in the original is raw
  string-interpolated SQL with `addslashes`; the Django ORM replaces all of it.
