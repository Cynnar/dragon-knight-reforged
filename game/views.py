import math
import random

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from . import combat, shop
from .forms import CharacterForm, SignupForm
from .models import Action, Character, GameControl, LevelTier, Monster, Town


# ── pages ────────────────────────────────────────────────────────────────────
def home(request):
    if not request.user.is_authenticated:
        return render(request, "game/home.html")
    try:
        character = request.user.character
    except Character.DoesNotExist:
        return redirect("create_character")

    if character.current_action == Action.FIGHTING and character.current_monster_id:
        return render(request, "game/fight.html", {
            "character": character,
            "monster": character.current_monster,
            "spells": character.known_spells.all(),
        })

    next_tier = LevelTier.objects.filter(
        char_class=character.char_class, level=character.level + 1
    ).first()
    return render(request, "game/status.html", {
        "character": character,
        "next_exp": next_tier.exp_required if next_tier else None,
        "current_town": _current_town(character),
    })


def signup(request):
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("home")
    else:
        form = SignupForm()
    return render(request, "registration/signup.html", {"form": form})


@login_required
def create_character(request):
    try:
        request.user.character
        return redirect("home")
    except Character.DoesNotExist:
        pass
    if request.method == "POST":
        form = CharacterForm(request.POST)
        if form.is_valid():
            character = form.save(commit=False)
            character.user = request.user
            character.save()
            return redirect("home")
    else:
        form = CharacterForm()
    return render(request, "game/create_character.html", {"form": form})


# ── movement ─────────────────────────────────────────────────────────────────
DIRECTIONS = {"north": (0, 1), "south": (0, -1), "east": (1, 0), "west": (-1, 0)}


@login_required
@require_POST
def move(request, direction):
    try:
        character = request.user.character
    except Character.DoesNotExist:
        return redirect("create_character")
    if direction not in DIRECTIONS:
        return redirect("home")
    if character.current_action == Action.FIGHTING:
        messages.info(request, "You can't wander off in the middle of a battle!")
        return redirect("home")

    left_behind = None
    if character.pending_drop_id:
        left_behind = character.pending_drop.name
        character.pending_drop = None

    control = GameControl.objects.first()
    size = control.game_size if control else 250
    d_long, d_lat = DIRECTIONS[direction]
    character.longitude = max(-size, min(size, character.longitude + d_long))
    character.latitude = max(-size, min(size, character.latitude + d_lat))

    town = Town.objects.filter(
        latitude=character.latitude, longitude=character.longitude
    ).first()
    if town:
        character.current_action = Action.IN_TOWN
        character.save()
        messages.info(request, f"You arrive at {town.name}.")
        return redirect("home")

    character.current_action = Action.EXPLORING
    if random.randint(1, 5) == 1 and _start_encounter(character, control, request):
        character.save()
        return redirect("home")

    character.save()
    messages.info(request, f"You travel {direction}.")
    if left_behind:
        messages.info(request, f"You leave the {left_behind} behind.")
    return redirect("home")


# ── combat ───────────────────────────────────────────────────────────────────
@login_required
@require_POST
def fight_action(request, action):
    character, monster = _fighting_character(request)
    if character is None:
        return redirect("home")
    control = GameControl.objects.first()
    mod = combat.difficulty_mod(character, control)

    if action == "run":
        if combat.player_escapes(character, monster):
            combat.clear_fight(character)
            character.current_action = Action.EXPLORING
            character.save()
            messages.info(request, "You slip away from the battle.")
            return redirect("home")
        messages.info(request, "You try to flee, but the monster blocks your path!")

    elif action == "attack":
        res = combat.player_attack(character, monster)
        if res["dodged"]:
            messages.info(request, f"The {monster.name} dodges your attack.")
        else:
            character.current_monster_hp -= res["damage"]
            prefix = "Excellent hit! " if res["excellent"] else ""
            messages.info(request, f"{prefix}You hit the {monster.name} for {res['damage']} damage.")
        if character.current_monster_hp <= 0:
            return _victory(request, character, monster, mod)

    else:
        return redirect("home")

    return _finish_round(request, character, monster, mod)


@login_required
@require_POST
def cast_spell(request):
    character, monster = _fighting_character(request)
    if character is None:
        return redirect("home")
    control = GameControl.objects.first()
    mod = combat.difficulty_mod(character, control)

    spell = character.known_spells.filter(id=request.POST.get("spell_id")).first()
    if spell is None:
        messages.info(request, "You haven't learned that spell.")
        return redirect("home")
    if character.current_mp < spell.mp_cost:
        messages.info(request, "You don't have enough MP for that spell.")
        return redirect("home")

    messages.info(request, combat.cast_spell(character, monster, spell))
    if character.current_monster_hp <= 0:
        return _victory(request, character, monster, mod)

    return _finish_round(request, character, monster, mod)


# ── combat helpers ───────────────────────────────────────────────────────────
def _fighting_character(request):
    """Return (character, monster) if the user is mid-fight, else (None, None)."""
    if not request.user.is_authenticated:
        return None, None
    try:
        character = request.user.character
    except Character.DoesNotExist:
        return None, None
    if character.current_action != Action.FIGHTING or not character.current_monster_id:
        return None, None
    return character, character.current_monster


def _finish_round(request, character, monster, mod):
    """Resolve the monster's turn (honoring sleep), then save or handle death."""
    status = combat.wake_check(character)
    if status == "woke":
        messages.info(request, f"The {monster.name} wakes up.")
    elif status == "asleep":
        messages.info(request, f"The {monster.name} sleeps on.")
    else:
        res = combat.monster_attack(character, monster, mod)
        if res["dodged"]:
            messages.info(request, f"You dodge the {monster.name}'s attack.")
        else:
            character.current_hp -= res["damage"]
            messages.info(request, f"The {monster.name} hits you for {res['damage']} damage.")

    if character.current_hp <= 0:
        combat.apply_death(character)
        character.save()
        messages.error(request, "You have fallen. You wake in town, weakened and half your gold gone.")
        return redirect("home")

    character.save()
    return redirect("home")


def _victory(request, character, monster, mod):
    name = monster.name
    exp, gold = combat.victory_rewards(character, monster, mod)
    character.experience += exp
    character.gold += gold
    combat.clear_fight(character)
    character.current_action = Action.EXPLORING
    leveled, spell = combat.try_level_up(character)
    dropped = None
    if not leveled:
        dropped = combat.roll_drop(monster)
        if dropped:
            character.pending_drop = dropped
    character.save()
    messages.success(request, f"You defeated the {name}!  +{exp} EXP, +{gold} gold.")
    if leveled:
        if spell:
            messages.success(request, f"You reached level {character.level} and learned {spell}!")
        else:
            messages.success(request, f"You reached level {character.level}!")
    if dropped:
        messages.success(request, f"The {name} dropped an item: {dropped.name}!")
    return redirect("home")


def _start_encounter(character, control, request):
    lat, lon = abs(character.latitude), abs(character.longitude)
    max_mlevel = max(1, math.floor(max(lat + 5, lon + 5) / 5))
    min_mlevel = max(1, max_mlevel - 2)
    monster = Monster.objects.filter(
        level__gte=min_mlevel, level__lte=max_mlevel
    ).order_by("?").first()
    if monster is None:
        return False

    hp = combat.rnd(math.floor(monster.max_hp * 4 / 5), monster.max_hp)
    hp = math.ceil(hp * combat.difficulty_mod(character, control))
    character.current_action = Action.FIGHTING
    character.current_monster = monster
    character.current_monster_hp = hp
    character.current_monster_sleep = 0
    character.current_monster_immune = monster.immune
    character.uber_damage = 0
    character.uber_defense = 0

    if combat.player_swings_first(character, monster):
        messages.warning(request, f"A {monster.name} appears!")
    else:
        res = combat.monster_attack(character, monster, combat.difficulty_mod(character, control))
        if res["dodged"]:
            messages.warning(request, f"A {monster.name} lunges before you're ready — but you dodge!")
        else:
            character.current_hp -= res["damage"]
            messages.warning(request, f"A {monster.name} attacks before you're ready, for {res['damage']} damage!")
            if character.current_hp <= 0:
                combat.apply_death(character)
                messages.error(request, "The blow fells you instantly! You wake in town, half your gold gone.")
    return True


# ── towns ────────────────────────────────────────────────────────────────────
def _get_character(request):
    if not request.user.is_authenticated:
        return None
    try:
        return request.user.character
    except Character.DoesNotExist:
        return None


def _current_town(character):
    if character.current_action != Action.IN_TOWN:
        return None
    return Town.objects.filter(
        latitude=character.latitude, longitude=character.longitude
    ).first()


@login_required
@require_POST
def inn(request):
    character = _get_character(request)
    if character is None:
        return redirect("home")
    town = _current_town(character)
    if town is None:
        return redirect("home")
    ok, msg = shop.stay_at_inn(character, town)
    if ok:
        character.save()
    messages.info(request, msg)
    return redirect("home")


@login_required
def shop_view(request):
    character = _get_character(request)
    if character is None:
        return redirect("create_character")
    town = _current_town(character)
    if town is None:
        messages.info(request, "You need to be in a town to shop.")
        return redirect("home")
    return render(request, "game/shop.html", {
        "character": character,
        "town": town,
        "items": town.shop_items.all().order_by("slot", "buy_cost"),
    })


@login_required
@require_POST
def buy_item(request, item_id):
    character = _get_character(request)
    if character is None:
        return redirect("create_character")
    town = _current_town(character)
    if town is None:
        return redirect("home")
    item = town.shop_items.filter(id=item_id).first()
    if item is None:
        messages.info(request, "That item isn't sold here.")
        return redirect("shop")
    ok, msg = shop.buy_item(character, item)
    if ok:
        character.save()
    messages.info(request, msg)
    return redirect("shop")


# ── item drops ───────────────────────────────────────────────────────────────
@login_required
def drop_reveal(request):
    character = _get_character(request)
    if character is None:
        return redirect("create_character")
    if character.pending_drop is None:
        return redirect("home")
    return render(request, "game/drop.html", {
        "character": character,
        "drop": character.pending_drop,
        "bonuses": shop.describe_drop(character.pending_drop),
    })


@login_required
@require_POST
def drop_equip(request):
    character = _get_character(request)
    if character is None:
        return redirect("create_character")
    drop = character.pending_drop
    if drop is None:
        return redirect("home")
    try:
        slot_num = int(request.POST.get("slot", 0))
    except (TypeError, ValueError):
        slot_num = 0
    ok, msg = shop.equip_drop(character, drop, slot_num)
    if ok:
        character.save()
    messages.info(request, msg)
    return redirect("home")


@login_required
@require_POST
def drop_leave(request):
    character = _get_character(request)
    if character is None:
        return redirect("create_character")
    if character.pending_drop_id:
        name = character.pending_drop.name
        character.pending_drop = None
        character.save()
        messages.info(request, f"You leave the {name} behind.")
    return redirect("home")
