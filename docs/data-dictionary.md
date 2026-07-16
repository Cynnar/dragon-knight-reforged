# Dragon Knight — Extracted Game Data

Engine-neutral seed data pulled from the original `install.php`. These files are the
canonical game content for the Django rewrite: load them as fixtures / seed rows. All
IDs are the original ones, so cross-references between files still line up.

| File            | Rows | What it is |
|-----------------|-----:|------------|
| `monsters.json` | 151  | Bestiary |
| `items.json`    | 33   | Equipment (weapons, armor, shields) |
| `spells.json`   | 19   | Spell book |
| `levels.json`   | 100  | Level curve, per class |
| `drops.json`    | 32   | Droppable items table |
| `towns.json`    | 8    | Towns, their coordinates and shop stock |
| `control.json`  | 1    | Global game config defaults |

## Field reference

### monsters.json
`id`, `name`, `maxhp`, `maxdam` (max hit), `armor`, `level` (tier, drives where it spawns
and what it can drop), `maxexp`, `maxgold`, `immune` (raw code) + `immune_to`
(`none` / `immune_to_damage_magic` / `immune_to_sleep`).

### items.json
`id`, `type` (raw) + `slot` (`weapon` / `armor` / `shield`), `name`, `buycost`,
`power` (attack power for weapons, defense power for armor/shields), `special`
(a special-effect code, or `null` — the original stored `"X"` for none).

### spells.json
`id`, `name`, `mp_cost`, `type` (raw) + `effect`
(`heal` / `damage` / `sleep` / `buff_damage` / `buff_defense`), `attribute`
(meaning depends on effect — HP healed, max damage, sleep turns, or % buff; see the
combat spec §5).

### levels.json
`level`, then `classes.{mage,warrior,paladin}` each with `exp_required` (cumulative exp to
reach this level as that class), `hp_gain`, `mp_gain`, `tp_gain`, `strength_gain`,
`dexterity_gain`, `spell_learned_id` (spell learned on reaching this level, or `null`).

### drops.json
`id`, `name`, `mlevel` (minimum monster level required for this to drop), `type`,
`attribute1`, `attribute2` (effect payload — kept raw; decode against the equip logic in
`towns.php` when you build the item system).

### towns.json
`id`, `name`, `latitude`, `longitude`, `innprice` (HP restore cost), `mapprice`,
`travelpoints`, `shop_item_ids` (array of item IDs sold here — parsed from the original
comma-separated `itemslist`).

### control.json
Global config: `gamename`, `gamesize` (map half-extent, default 250), class names,
difficulty names + modifiers (`diff2mod` 1.2, `diff3mod` 1.5), and various feature flags
(news, babblebox, online list, email verify). In the new build most of this becomes
settings rather than a DB row, but it documents the original defaults.

## Notes
- `special` on items and `attribute1/2` on drops encode bonus effects; their exact
  semantics live in the buy/equip code in `towns.php` and are worth decoding when you
  implement inventory. Left raw here on purpose.
- Experience/gold were capped at 16,777,215 (old mediumint). Not a real design limit —
  raise it in the new schema.
