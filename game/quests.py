"""
Quest offering, progress tracking and rewards.

Progress is recorded by small `record_*` hooks the game calls when something
happens (a monster dies, a town is reached, a level is gained). Keeping them here
means the combat and movement code stays about combat and movement.
"""
from django.db.models import Q
from django.utils import timezone

from . import inventory
from .models import CharacterQuest, Quest, QuestObjective, QuestState


# ── offering ────────────────────────────────────────────────────────────────
def available_quests(character, town):
    """Quests this character can pick up at this town's board."""
    taken_ids = set(
        CharacterQuest.objects.filter(character=character)
        .exclude(state=QuestState.DONE)
        .values_list("quest_id", flat=True)
    )
    finished_ids = set(
        CharacterQuest.objects.filter(character=character, state=QuestState.DONE)
        .values_list("quest_id", flat=True)
    )

    offers = Quest.objects.filter(is_active=True, min_level__lte=character.level).filter(
        Q(giver_town__isnull=True) | Q(giver_town=town)
    )
    return [
        q for q in offers.select_related("target_monster", "target_town", "reward_item")
        if q.id not in taken_ids and (q.repeatable or q.id not in finished_ids)
    ]


def active_quests(character):
    return (
        CharacterQuest.objects.filter(character=character)
        .exclude(state=QuestState.DONE)
        .select_related("quest", "quest__target_monster", "quest__target_town",
                        "quest__reward_item")
    )


def accept(character, quest):
    if CharacterQuest.objects.filter(character=character, quest=quest).exclude(
        state=QuestState.DONE
    ).exists():
        return None, "You're already on that quest."
    if character.level < quest.min_level:
        return None, f"You need to be level {quest.min_level} for that."
    if not quest.repeatable and CharacterQuest.objects.filter(
        character=character, quest=quest, state=QuestState.DONE
    ).exists():
        return None, "You've already completed that one."

    attempt = CharacterQuest.objects.create(character=character, quest=quest)
    _refresh(attempt, character)
    return attempt, f"Quest accepted: {quest.name}."


# ── progress hooks ──────────────────────────────────────────────────────────
def _refresh(attempt, character):
    """Re-evaluate an attempt and flip it to READY when the goal is met."""
    quest = attempt.quest
    if quest.objective == QuestObjective.REACH_LEVEL:
        attempt.progress = 1 if character.level >= quest.target_level else 0
    done = attempt.progress >= quest.goal_total
    new_state = QuestState.READY if done else QuestState.ACTIVE
    if (attempt.state, attempt.progress) != (new_state, attempt.progress) or attempt.state != new_state:
        attempt.state = new_state
    attempt.save(update_fields=["progress", "state"])
    return done


def record_kill(character, monster):
    """Called on victory. Returns names of quests that just became ready."""
    ready = []
    for attempt in active_quests(character).filter(quest__objective=QuestObjective.SLAY):
        quest = attempt.quest
        if quest.target_monster_id and quest.target_monster_id != monster.id:
            continue
        if attempt.state == QuestState.READY:
            continue
        attempt.progress += 1
        if _refresh(attempt, character):
            ready.append(quest.name)
    return ready


def record_visit(character, town):
    ready = []
    for attempt in active_quests(character).filter(quest__objective=QuestObjective.VISIT_TOWN):
        quest = attempt.quest
        if quest.target_town_id and quest.target_town_id != town.id:
            continue
        if attempt.state == QuestState.READY:
            continue
        attempt.progress = quest.goal_total
        if _refresh(attempt, character):
            ready.append(quest.name)
    return ready


def record_level(character):
    ready = []
    for attempt in active_quests(character).filter(quest__objective=QuestObjective.REACH_LEVEL):
        if attempt.state == QuestState.READY:
            continue
        if _refresh(attempt, character):
            ready.append(attempt.quest.name)
    return ready


# ── handing in ──────────────────────────────────────────────────────────────
def claim(character, attempt):
    """Pay out a finished quest. The caller saves the character."""
    if attempt.state != QuestState.READY:
        return False, "That quest isn't finished yet."
    quest = attempt.quest
    character.experience += quest.reward_exp
    character.gold += quest.reward_gold
    if quest.reward_item_id:
        inventory.add_item(character, quest.reward_item)

    attempt.state = QuestState.DONE
    attempt.completed_at = timezone.now()
    attempt.save(update_fields=["state", "completed_at"])

    bits = []
    if quest.reward_exp:
        bits.append(f"{quest.reward_exp} EXP")
    if quest.reward_gold:
        bits.append(f"{quest.reward_gold} gold")
    if quest.reward_item_id:
        bits.append(quest.reward_item.name)
    reward = ", ".join(bits) if bits else "your thanks"
    return True, f"Quest complete: {quest.name}! You receive {reward}."
