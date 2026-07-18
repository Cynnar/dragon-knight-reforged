import math
import random
from datetime import timedelta

from django.contrib import messages
from django.utils import timezone
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
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
    return render_play(request, character)


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
        return play_response(request, character)

    log_clear(request)

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
        return play_response(request, character)

    character.current_action = Action.EXPLORING
    if random.randint(1, 5) == 1 and _start_encounter(character, control, request):
        character.save()
        return play_response(request, character)

    character.save()
    messages.info(request, f"You travel {direction}.")
    if left_behind:
        messages.info(request, f"You leave the {left_behind} behind.")
    return play_response(request, character)


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
            log(request, "You slip away from the battle.")
            return play_response(request, character)
        log(request, "You try to flee, but the monster blocks your path!")

    elif action == "attack":
        res = combat.player_attack(character, monster)
        if res["dodged"]:
            log(request, f"The {monster.name} dodges your attack.")
        else:
            character.current_monster_hp -= res["damage"]
            prefix = "Excellent hit! " if res["excellent"] else ""
            log(request, f"{prefix}You hit the {monster.name} for {res['damage']} damage.")
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
        return play_response(request, character)
    if character.current_mp < spell.mp_cost:
        messages.info(request, "You don't have enough MP for that spell.")
        return play_response(request, character)

    log(request, combat.cast_spell(character, monster, spell))
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
        log(request, f"The {monster.name} wakes up.")
    elif status == "asleep":
        log(request, f"The {monster.name} sleeps on.")
    else:
        res = combat.monster_attack(character, monster, mod)
        if res["dodged"]:
            log(request, f"You dodge the {monster.name}'s attack.")
        else:
            character.current_hp -= res["damage"]
            log(request, f"The {monster.name} hits you for {res['damage']} damage.")

    if character.current_hp <= 0:
        combat.apply_death(character)
        character.save()
        log(request, "You have fallen. You wake in town, weakened and half your gold gone.")
        return play_response(request, character)

    character.save()
    return play_response(request, character)


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
    log(request, f"You defeated the {name}!  +{exp} EXP, +{gold} gold.")
    if leveled:
        if spell:
            log(request, f"You reached level {character.level} and learned {spell}!")
        else:
            log(request, f"You reached level {character.level}!")
    if dropped:
        log(request, f"The {name} dropped an item: {dropped.name}!")
    return play_response(request, character)


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

    log_clear(request)
    if combat.player_swings_first(character, monster):
        log(request, f"A {monster.name} appears!")
    else:
        res = combat.monster_attack(character, monster, combat.difficulty_mod(character, control))
        if res["dodged"]:
            log(request, f"A {monster.name} lunges before you're ready — but you dodge!")
        else:
            character.current_hp -= res["damage"]
            log(request, f"A {monster.name} attacks before you're ready, for {res['damage']} damage!")
            if character.current_hp <= 0:
                combat.apply_death(character)
                log(request, "The blow fells you instantly! You wake in town, half your gold gone.")
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
        log_clear(request)
    messages.info(request, msg)
    return play_response(request, character)


@login_required
def shop_view(request):
    character = _get_character(request)
    if character is None:
        return redirect("create_character")
    town = _current_town(character)
    if town is None:
        messages.info(request, "You need to be in a town to shop.")
        return redirect("home")
    ctx = {
        "character": character,
        "town": town,
        "items": town.shop_items.all().order_by("slot", "buy_cost"),
    }
    template = "game/_shop_panel.html" if is_htmx(request) else "game/shop.html"
    return render(request, template, ctx)


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
    if is_htmx(request):
        return render(request, "game/_shop_panel.html", {
            "character": character,
            "town": town,
            "items": town.shop_items.all().order_by("slot", "buy_cost"),
        })
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


# ── community: tavern (news + babblebox) ─────────────────────────────────────
@login_required
def tavern(request):
    from .models import News
    ctx = _babble_context()
    ctx["news"] = News.objects.order_by("-posted_at")[:5]
    return render(request, "game/tavern.html", ctx)


def _babble_context():
    from .models import BabbleMessage
    babbles = list(BabbleMessage.objects.select_related("author").order_by("-posted_at")[:20])
    names = dict(
        Character.objects.filter(user__in=[b.author_id for b in babbles if b.author_id])
        .values_list("user_id", "char_name")
    )
    for b in babbles:
        b.display_name = names.get(b.author_id) or (b.author.username if b.author_id else "Unknown")
    return {"babbles": babbles}


@login_required
@require_POST
def post_babble(request):
    from .models import BabbleMessage
    text = (request.POST.get("babble") or "").strip()[:120]
    if text:
        BabbleMessage.objects.create(author=request.user, message=text)
    if is_htmx(request):
        return render(request, "game/_babble_list.html", _babble_context())
    return redirect("tavern")


@login_required
def babble_list(request):
    """Just the message list — polled so other players' babbles appear live."""
    return render(request, "game/_babble_list.html", _babble_context())


@login_required
def whos_online(request):
    """Characters active within the last 10 minutes (matches the original window)."""
    cutoff = timezone.now() - timedelta(minutes=10)
    online = Character.objects.filter(last_active__gte=cutoff).order_by("char_name")
    return render(request, "game/online.html", {"online": online, "count": online.count()})


# ── forum ────────────────────────────────────────────────────────────────────
def _attach_author_names(posts):
    """Attach .display_name (character name, else username) to each post."""
    ids = [p.author_id for p in posts if p.author_id]
    names = dict(Character.objects.filter(user__in=ids).values_list("user_id", "char_name"))
    for p in posts:
        p.display_name = names.get(p.author_id) or (p.author.username if p.author_id else "Unknown")
    return posts


@login_required
def forum_index(request):
    from .models import ForumPost
    threads = list(
        ForumPost.objects.filter(parent__isnull=True)
        .select_related("author")
        .annotate(reply_count=Count("replies"))
        .order_by("-last_reply_at")[:30]
    )
    _attach_author_names(threads)
    return render(request, "game/forum/index.html", {"threads": threads})


@login_required
def forum_thread(request, thread_id):
    from .models import ForumPost
    thread = get_object_or_404(ForumPost, id=thread_id, parent__isnull=True)
    replies = list(thread.replies.select_related("author").order_by("posted_at"))
    _attach_author_names([thread] + replies)
    return render(request, "game/forum/thread.html", {"thread": thread, "replies": replies})


@login_required
def forum_new(request):
    from .models import ForumPost
    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()[:100]
        content = (request.POST.get("content") or "").strip()
        if title and content:
            thread = ForumPost.objects.create(author=request.user, parent=None,
                                              title=title, content=content)
            return redirect("forum_thread", thread_id=thread.id)
        messages.info(request, "A thread needs both a title and a message.")
    return render(request, "game/forum/new.html")


@login_required
@require_POST
def forum_reply(request, thread_id):
    from .models import ForumPost
    thread = get_object_or_404(ForumPost, id=thread_id, parent__isnull=True)
    content = (request.POST.get("content") or "").strip()
    if content:
        ForumPost.objects.create(author=request.user, parent=thread,
                                 title=f"Re: {thread.title}", content=content)
        thread.last_reply_at = timezone.now()
        thread.save(update_fields=["last_reply_at"])
    return redirect("forum_thread", thread_id=thread.id)


# ── battle log (session-backed: transient narration, no schema change) ──────
LOG_KEY = "combat_log"
LOG_MAX = 14


def log(request, text):
    """Append a line to the battle log the player sees during/after a fight."""
    entries = request.session.get(LOG_KEY, [])
    entries.append(text)
    request.session[LOG_KEY] = entries[-LOG_MAX:]
    request.session.modified = True


def log_clear(request):
    if request.session.get(LOG_KEY):
        request.session[LOG_KEY] = []
        request.session.modified = True


# ── play screen rendering (shared by full pages and HTMX fragments) ──────────
def is_htmx(request):
    return request.headers.get("HX-Request") == "true"


def play_context(request, character):
    """Everything the status/fight screens need, in one place."""
    in_fight = character.current_action == Action.FIGHTING and bool(character.current_monster_id)
    next_tier = LevelTier.objects.filter(
        char_class=character.char_class, level=character.level + 1
    ).first()
    return {
        "character": character,
        "in_fight": in_fight,
        "monster": character.current_monster if in_fight else None,
        "spells": character.known_spells.all() if in_fight else None,
        "next_exp": next_tier.exp_required if next_tier else None,
        "current_town": _current_town(character),
        "combat_log": request.session.get(LOG_KEY, []),
        # the current round's beats, surfaced at the top of the panel
        "recent_events": request.session.get(LOG_KEY, [])[-2:],
    }


def play_response(request, character):
    """Response for a state-changing action: HTMX gets the updated panel,
    everyone else gets a redirect (POST-redirect-GET keeps refresh safe)."""
    if is_htmx(request):
        return render(request, "game/_panel.html", play_context(request, character))
    return redirect("home")


def render_play(request, character):
    """HTMX request -> just the panel fragment. Otherwise -> the full page.
    Views can therefore return this instead of redirecting."""
    ctx = play_context(request, character)
    if is_htmx(request):
        return render(request, "game/_panel.html", ctx)
    template = "game/fight.html" if ctx["in_fight"] else "game/status.html"
    return render(request, template, ctx)
