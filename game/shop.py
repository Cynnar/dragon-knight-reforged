"""
Town economy for Dragon Knight — the inn and the shop.

Faithful to the original towns.php:
  * Inn: pay the town's price, restore HP/MP/TP to full.
  * Shop: buying an item trades in whatever's in that slot for half its value,
    swaps the item's power into your attack (weapons) or defense (armor/shields),
    and applies any "special" stat bonus the item carries.

Item `special` is the original "field,amount" string, e.g. "strength,50" or
"maxmp,50". Those map onto Character fields below.
"""
import math

from .models import EquipSlot

# original special-field name -> Character attribute
SPECIAL_FIELD = {
    "strength": "strength",
    "dexterity": "dexterity",
    "maxhp": "max_hp",
    "maxmp": "max_mp",
    "expbonus": "exp_bonus",
    "goldbonus": "gold_bonus",
}

SLOT_ATTR = {EquipSlot.WEAPON: "weapon", EquipSlot.ARMOR: "armor", EquipSlot.SHIELD: "shield"}
# weapons feed attack power; armor and shields feed defense power
SLOT_POWER_STAT = {
    EquipSlot.WEAPON: "attack_power",
    EquipSlot.ARMOR: "defense_power",
    EquipSlot.SHIELD: "defense_power",
}


def stay_at_inn(character, town):
    """Restore expendable stats to max for the town's price. Returns (ok, message)."""
    if character.gold < town.inn_price:
        return False, "You don't have enough gold to stay the night."
    character.gold -= town.inn_price
    character.current_hp = character.max_hp
    character.current_mp = character.max_mp
    character.current_tp = character.max_tp
    return True, f"You rest at the inn and recover fully.  (-{town.inn_price} gold)"


def parse_special(special):
    """'strength,50' -> ('strength', 50) as a (Character attr, amount) pair, or None."""
    if not special:
        return None
    try:
        field, amount = special.split(",")
        amount = int(amount)
    except (ValueError, AttributeError):
        return None
    attr = SPECIAL_FIELD.get(field.strip())
    return (attr, amount) if attr else None


def _apply_special(character, item, sign):
    """Add (sign=+1) or remove (sign=-1) an item's special bonus. Strength and
    dexterity bonuses also flow into attack/defense, matching the original."""
    parsed = parse_special(item.special)
    if not parsed:
        return
    attr, amount = parsed
    setattr(character, attr, getattr(character, attr) + sign * amount)
    if attr == "strength":
        character.attack_power += sign * amount
    elif attr == "dexterity":
        character.defense_power += sign * amount


def buy_item(character, item):
    """Purchase and equip `item`, trading in whatever occupies its slot.
    Returns (ok, message); mutates character (caller saves). Like the original,
    you must have the full price in gold on hand — the trade-in is credited after."""
    if character.gold < item.buy_cost:
        return False, "You don't have enough gold to buy that."

    slot_attr = SLOT_ATTR[item.slot]
    power_stat = SLOT_POWER_STAT[item.slot]
    old = getattr(character, slot_attr)

    trade_in = math.ceil(old.buy_cost / 2) if old else 0
    old_power = old.power if old else 0

    if old:
        _apply_special(character, old, -1)   # unequip old bonuses
    _apply_special(character, item, +1)      # equip new bonuses

    character.gold = character.gold + trade_in - item.buy_cost
    setattr(character, power_stat, getattr(character, power_stat) + item.power - old_power)
    setattr(character, slot_attr, item)

    # a special may have lowered a max; keep current vitals within bounds
    character.current_hp = min(character.current_hp, character.max_hp)
    character.current_mp = min(character.current_mp, character.max_mp)
    character.current_tp = min(character.current_tp, character.max_tp)

    msg = f"You bought the {item.name}."
    if old:
        msg += f"  Traded in your {old.name} for {trade_in} gold."
    return True, msg


# ── drops (accessory loot) ───────────────────────────────────────────────────
# Drop attribute fields ("field,amount") map onto Character attributes.
DROP_FIELD = {
    "maxhp": "max_hp", "maxmp": "max_mp", "maxtp": "max_tp",
    "strength": "strength", "dexterity": "dexterity",
    "attackpower": "attack_power", "defensepower": "defense_power",
    "expbonus": "exp_bonus", "goldbonus": "gold_bonus",
}
ATTR_LABEL = {
    "maxhp": "Max HP", "maxmp": "Max MP", "maxtp": "Max TP",
    "strength": "Strength", "dexterity": "Dexterity",
    "attackpower": "Attack", "defensepower": "Defense",
    "expbonus": "Exp Bonus", "goldbonus": "Gold Bonus",
}


def _drop_attrs(drop):
    """Yield (raw_field, amount) for a drop's attribute1 and attribute2 (skips 'X')."""
    for raw in (drop.attribute1, drop.attribute2):
        if not raw or raw.strip().upper() == "X":
            continue
        try:
            field, amount = raw.split(",")
            yield field.strip(), int(amount)
        except ValueError:
            continue


def apply_drop(character, drop, sign):
    """Add (+1) or remove (-1) a drop's stat bonuses. strength/dexterity also flow
    into attack/defense, mirroring the original."""
    for field, amount in _drop_attrs(drop):
        attr = DROP_FIELD.get(field)
        if attr is None:
            continue
        setattr(character, attr, getattr(character, attr) + sign * amount)
        if field == "strength":
            character.attack_power += sign * amount
        elif field == "dexterity":
            character.defense_power += sign * amount


def describe_drop(drop):
    """Human-readable bonus list, e.g. ['Max HP +50', 'Strength +10']."""
    out = []
    for field, amount in _drop_attrs(drop):
        label = ATTR_LABEL.get(field, field)
        out.append(f"{label} {'+' if amount >= 0 else ''}{amount}")
    return out


def equip_drop(character, drop, slot_num):
    """Equip a drop into accessory slot 1/2/3, discarding whatever was there.
    Returns (ok, message); mutates character (caller saves)."""
    if slot_num not in (1, 2, 3):
        return False, "Choose a valid slot."
    slot_attr = f"accessory{slot_num}"
    old = getattr(character, slot_attr)
    if old:
        apply_drop(character, old, -1)
    apply_drop(character, drop, +1)
    setattr(character, slot_attr, drop)
    character.pending_drop = None
    character.current_hp = min(character.current_hp, character.max_hp)
    character.current_mp = min(character.current_mp, character.max_mp)
    character.current_tp = min(character.current_tp, character.max_tp)
    msg = f"You equip the {drop.name} in slot {slot_num}."
    if old:
        msg += f"  (Discarded your {old.name}.)"
    return True, msg
