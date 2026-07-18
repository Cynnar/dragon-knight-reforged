"""
Combat math for Dragon Knight, faithful to docs/combat-and-progression.md.

These are (mostly) pure functions: they compute results and return them; the views
apply the results to character state and emit the player-facing messages. Keeping the
math here makes it easy to read against the spec and to unit-test.
"""
import math
import random

from .models import Action, Difficulty, LevelTier


def rnd(a, b):
    """Inclusive integer roll, tolerant of float/reversed bounds (PHP rand() semantics)."""
    a, b = int(math.floor(a)), int(math.floor(b))
    if a > b:
        a, b = b, a
    return random.randint(a, b)


def difficulty_mod(character, control):
    if control and character.difficulty == Difficulty.MEDIUM:
        return control.difficulty_medium_mod
    if control and character.difficulty == Difficulty.HARD:
        return control.difficulty_hard_mod
    return 1.0


# ── per-swing resolution ─────────────────────────────────────────────────────
def player_swings_first(character, monster):
    """Initiative (spec §3): decides who acts first on the opening round."""
    return (rnd(1, 10) + math.ceil(math.sqrt(character.dexterity))) > \
           (rnd(1, 7) + math.ceil(math.sqrt(monster.max_damage)))


def player_attack(character, monster):
    """Damage the player deals to the monster this swing (spec §4a)."""
    tohit = math.ceil(rnd(character.attack_power * 0.75, character.attack_power) / 3)
    excellent = rnd(1, 150) <= math.sqrt(character.strength)
    if excellent:
        tohit *= 2
    toblock = math.ceil(rnd(monster.armor * 0.75, monster.armor) / 3)
    if rnd(1, 200) <= math.sqrt(monster.armor):
        return {"damage": 0, "excellent": False, "dodged": True}
    dmg = max(1, tohit - toblock)
    if character.uber_damage:
        dmg += math.ceil(dmg * character.uber_damage / 100)
    return {"damage": dmg, "excellent": excellent, "dodged": False}


def monster_attack(character, monster, mod):
    """Damage the monster deals to the player this swing, after difficulty (spec §4b)."""
    tohit = math.ceil(rnd(monster.max_damage * 0.5, monster.max_damage))
    tohit = math.ceil(tohit * mod)
    toblock = math.ceil(rnd(character.defense_power * 0.75, character.defense_power) / 4)
    if rnd(1, 150) <= math.sqrt(character.dexterity):
        return {"damage": 0, "dodged": True}
    dmg = max(1, tohit - toblock)
    if character.uber_defense:
        dmg -= math.ceil(dmg * character.uber_defense / 100)
    return {"damage": max(1, dmg), "dodged": False}


def player_escapes(character, monster):
    """Run check (spec §4c)."""
    return (rnd(4, 10) + math.ceil(math.sqrt(character.dexterity))) > \
           (rnd(1, 5) + math.ceil(math.sqrt(monster.max_damage)))


# ── victory / progression / death ────────────────────────────────────────────
def victory_rewards(character, monster, mod):
    """EXP and gold for a kill (spec §6). The old 16.7M cap is intentionally dropped."""
    exp = max(1, rnd(math.floor(monster.max_exp * 5 / 6), monster.max_exp))
    gold = max(1, rnd(math.floor(monster.max_gold * 5 / 6), monster.max_gold))
    exp = math.ceil(exp * mod)
    gold = math.ceil(gold * mod)
    exp += math.ceil(exp * character.exp_bonus / 100)
    gold += math.ceil(gold * character.gold_bonus / 100)
    return exp, gold


def try_level_up(character):
    """One level-up check per victory (matches the original). Raises the MAX stats but
    does NOT refill current HP/MP — healing comes from inns/spells. Attack tracks
    strength gains, defense tracks dexterity gains. Returns (leveled, spell_name|None)."""
    if character.level >= 100:
        return False, None
    tier = LevelTier.objects.filter(
        char_class=character.char_class, level=character.level + 1
    ).select_related("spell_learned").first()
    if not tier or character.experience < tier.exp_required:
        return False, None
    character.level = tier.level
    character.max_hp += tier.hp_gain
    character.max_mp += tier.mp_gain
    character.max_tp += tier.tp_gain
    character.strength += tier.strength_gain
    character.dexterity += tier.dexterity_gain
    character.attack_power += tier.strength_gain
    character.defense_power += tier.dexterity_gain
    spell_name = None
    if tier.spell_learned_id:
        character.known_spells.add(tier.spell_learned)
        spell_name = tier.spell_learned.name
    return True, spell_name


def clear_fight(character):
    """Reset the transient battle state (does not touch action/position)."""
    character.current_monster = None
    character.current_monster_hp = 0
    character.current_monster_sleep = 0
    character.current_monster_immune = 0
    character.uber_damage = 0
    character.uber_defense = 0


def apply_death(character):
    """Death (spec §8): lose half your gold, revive at 1/4 max HP, back to town at origin."""
    character.gold = math.ceil(character.gold / 2)
    character.current_hp = math.ceil(character.max_hp / 4)
    character.current_action = Action.IN_TOWN
    character.latitude = 0
    character.longitude = 0
    clear_fight(character)


# ── spells (spec §5) ─────────────────────────────────────────────────────────
def cast_spell(character, monster, spell):
    """Apply a spell's effect and deduct its MP. Returns a player-facing message.
    Assumes the caller already checked the spell is known and affordable.

    Immunity quirk carried over from the original (raw `immune` codes):
      * a DAMAGE spell is blocked by ANY nonzero immunity (immune != 0)
      * a SLEEP spell is blocked only by immune == 2
    """
    from .models import SpellEffect

    character.current_mp -= spell.mp_cost

    if spell.effect == SpellEffect.HEAL:
        healed = min(spell.attribute, character.max_hp - character.current_hp)
        character.current_hp += healed
        return f"You cast {spell.name} and recover {healed} HP."

    if spell.effect == SpellEffect.DAMAGE:
        if character.current_monster_immune != 0:
            return f"You cast {spell.name}, but the {monster.name} is immune."
        dmg = rnd(math.floor(spell.attribute * 5 / 6), spell.attribute)
        character.current_monster_hp -= dmg
        return f"You cast {spell.name} for {dmg} damage."

    if spell.effect == SpellEffect.SLEEP:
        if character.current_monster_immune == 2:
            return f"You cast {spell.name}, but the {monster.name} is immune."
        character.current_monster_sleep = spell.attribute
        return f"You cast {spell.name}. The {monster.name} falls asleep."

    if spell.effect == SpellEffect.BUFF_DAMAGE:
        character.uber_damage = spell.attribute
        return f"You cast {spell.name}. +{spell.attribute}% damage until the fight ends."

    if spell.effect == SpellEffect.BUFF_DEFENSE:
        character.uber_defense = spell.attribute
        return f"You cast {spell.name}. +{spell.attribute}% defense until the fight ends."

    return f"You cast {spell.name}."


def wake_check(character):
    """Sleep wake roll at the start of the monster's turn (spec §5).
    Returns 'woke', 'asleep', or 'awake' (was never asleep)."""
    if not character.current_monster_sleep:
        return "awake"
    if rnd(1, 15) > character.current_monster_sleep:
        character.current_monster_sleep = 0
        return "woke"
    return "asleep"


def roll_drop(monster):
    """1-in-30 chance on a (non-level-up) victory to drop loot (spec §6).
    Returns a Drop the monster's level qualifies for, or None."""
    from .models import Drop
    if rnd(1, 30) != 1:
        return None
    return Drop.objects.filter(min_monster_level__lte=monster.level).order_by("?").first()
