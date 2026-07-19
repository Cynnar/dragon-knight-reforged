"""
Bag and equipment handling.

The rule everywhere here: a stat bonus is *applied* when something is equipped and
*removed* when it comes off, so equip/unequip are exact inverses and nothing is ever
destroyed — items you replace go back into the bag instead of being traded away.

Shop gear (Item) fills the weapon/armor/shield slots and contributes its `power` to
attack or defense, plus any "special" bonus. Accessory loot (Drop) fills the three
accessory slots and contributes its attribute bonuses.
"""
import math

from . import shop
from .models import EquipSlot, GameControl, InventoryItem, ItemLocation

SLOT_ATTR = shop.SLOT_ATTR              # EquipSlot -> character field name
SLOT_POWER_STAT = shop.SLOT_POWER_STAT  # EquipSlot -> attack_power / defense_power
ACCESSORY_SLOTS = (1, 2, 3)


# ── bag ─────────────────────────────────────────────────────────────────────
def add_item(character, item, location=ItemLocation.BAG):
    return InventoryItem.objects.create(character=character, item=item, location=location)


def add_drop(character, drop, location=ItemLocation.BAG):
    return InventoryItem.objects.create(character=character, drop=drop, location=location)


def bag(character):
    return InventoryItem.objects.filter(character=character, location=ItemLocation.BAG)


def vault(character):
    return InventoryItem.objects.filter(character=character, location=ItemLocation.BANK)


def bank_slots(control=None):
    control = control or GameControl.objects.first()
    return control.bank_slots if control else 20


def vault_is_full(character, control=None):
    limit = bank_slots(control)
    return bool(limit) and vault(character).count() >= limit


def clamp_vitals(character):
    """A removed bonus can lower a maximum; keep current values inside it."""
    character.current_hp = min(character.current_hp, character.max_hp)
    character.current_mp = min(character.current_mp, character.max_mp)
    character.current_tp = min(character.current_tp, character.max_tp)


# ── gear (weapon / armor / shield) ──────────────────────────────────────────
def _apply_item(character, item, sign):
    """Add (+1) or remove (-1) a gear item's power and special bonus."""
    stat = SLOT_POWER_STAT[item.slot]
    setattr(character, stat, getattr(character, stat) + sign * item.power)
    shop._apply_special(character, item, sign)


def equip_item(character, entry):
    """Equip gear from the bag. Whatever was in that slot returns to the bag."""
    item = entry.item
    slot_attr = SLOT_ATTR[item.slot]
    previous = getattr(character, slot_attr)

    if previous:
        _apply_item(character, previous, -1)
    _apply_item(character, item, +1)
    setattr(character, slot_attr, item)
    entry.delete()
    if previous:
        add_item(character, previous)
    clamp_vitals(character)

    msg = f"You equip the {item.name}."
    if previous:
        msg += f"  The {previous.name} goes back in your bag."
    return True, msg


def unequip_slot(character, slot):
    """Take gear off and put it in the bag. `slot` is an EquipSlot value."""
    slot_attr = SLOT_ATTR[slot]
    item = getattr(character, slot_attr)
    if item is None:
        return False, "Nothing is equipped there."
    _apply_item(character, item, -1)
    setattr(character, slot_attr, None)
    add_item(character, item)
    clamp_vitals(character)
    return True, f"You stow the {item.name} in your bag."


# ── accessories (drops) ─────────────────────────────────────────────────────
def equip_drop(character, entry, slot_num):
    """Equip an accessory into slot 1/2/3; the previous one returns to the bag."""
    if slot_num not in ACCESSORY_SLOTS:
        return False, "Choose a valid accessory slot."
    drop = entry.drop
    slot_attr = f"accessory{slot_num}"
    previous = getattr(character, slot_attr)

    if previous:
        shop.apply_drop(character, previous, -1)
    shop.apply_drop(character, drop, +1)
    setattr(character, slot_attr, drop)
    entry.delete()
    if previous:
        add_drop(character, previous)
    clamp_vitals(character)

    msg = f"You equip the {drop.name} in slot {slot_num}."
    if previous:
        msg += f"  The {previous.name} goes back in your bag."
    return True, msg


def unequip_accessory(character, slot_num):
    if slot_num not in ACCESSORY_SLOTS:
        return False, "Choose a valid accessory slot."
    slot_attr = f"accessory{slot_num}"
    drop = getattr(character, slot_attr)
    if drop is None:
        return False, "Nothing is equipped there."
    shop.apply_drop(character, drop, -1)
    setattr(character, slot_attr, None)
    add_drop(character, drop)
    clamp_vitals(character)
    return True, f"You stow the {drop.name} in your bag."


# ── selling ─────────────────────────────────────────────────────────────────
def sale_value(entry):
    """Gear sells for half its shop price; found accessories have no resale value."""
    if entry.item_id:
        return math.ceil(entry.item.buy_cost / 2)
    return 0


def sell(character, entry):
    if entry.drop_id:
        return False, "No merchant will buy a trinket like that."
    value = sale_value(entry)
    name = entry.item.name
    character.gold += value
    entry.delete()
    return True, f"You sell the {name} for {value} gold."


# ── bank ────────────────────────────────────────────────────────────────────
def deposit_gold(character, amount):
    if amount <= 0:
        return False, "Enter an amount to deposit."
    if amount > character.gold:
        return False, "You don't have that much gold on you."
    character.gold -= amount
    character.bank_gold += amount
    return True, f"You deposit {amount} gold."


def withdraw_gold(character, amount):
    if amount <= 0:
        return False, "Enter an amount to withdraw."
    if amount > character.bank_gold:
        return False, "Your account doesn't hold that much."
    character.bank_gold -= amount
    character.gold += amount
    return True, f"You withdraw {amount} gold."


def store_item(character, entry, control=None):
    """Move something from the bag into the vault, respecting the slot limit."""
    if entry.location == ItemLocation.BANK:
        return False, "That's already in the vault."
    if vault_is_full(character, control):
        return False, f"Your vault is full ({bank_slots(control)} slots)."
    entry.location = ItemLocation.BANK
    entry.save(update_fields=["location"])
    return True, f"You store the {entry.name} in the vault."


def retrieve_item(character, entry):
    if entry.location == ItemLocation.BAG:
        return False, "That's already in your bag."
    entry.location = ItemLocation.BAG
    entry.save(update_fields=["location"])
    return True, f"You take the {entry.name} from the vault."
