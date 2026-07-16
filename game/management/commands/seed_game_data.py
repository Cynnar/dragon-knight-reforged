"""
Seed static game content from the extracted JSON in game/seed_data/.

Usage:  python manage.py seed_game_data
Idempotent: uses update_or_create keyed on the original IDs, so re-running syncs
rather than duplicating. Does NOT touch player Characters.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from game import models

SEED_DIR = Path(__file__).resolve().parents[2] / "seed_data"


def load(name):
    return json.loads((SEED_DIR / name).read_text())


class Command(BaseCommand):
    help = "Load monsters, items, spells, levels, towns, drops and control from seed_data/."

    @transaction.atomic
    def handle(self, *args, **options):
        # Order matters: Spell before LevelTier (FK), Item before Town (M2M).
        for row in load("monsters.json"):
            models.Monster.objects.update_or_create(id=row["id"], defaults=dict(
                name=row["name"], max_hp=row["maxhp"], max_damage=row["maxdam"],
                armor=row["armor"], level=row["level"], max_exp=row["maxexp"],
                max_gold=row["maxgold"], immune=row["immune"]))
        self.stdout.write(f"monsters: {models.Monster.objects.count()}")

        for row in load("items.json"):
            special = row.get("special")
            models.Item.objects.update_or_create(id=row["id"], defaults=dict(
                slot=row["type"], name=row["name"], buy_cost=row["buycost"],
                power=row["power"], special=special or None))
        self.stdout.write(f"items: {models.Item.objects.count()}")

        for row in load("spells.json"):
            models.Spell.objects.update_or_create(id=row["id"], defaults=dict(
                name=row["name"], mp_cost=row["mp_cost"], effect=row["type"],
                attribute=row["attribute"]))
        self.stdout.write(f"spells: {models.Spell.objects.count()}")

        # levels.json is one entry per level, each with per-class gains.
        for row in load("levels.json"):
            level = row["level"]
            for class_id, cname in ((1, "mage"), (2, "warrior"), (3, "paladin")):
                c = row["classes"][cname]
                spell = None
                if c.get("spell_learned_id"):
                    spell = models.Spell.objects.filter(id=c["spell_learned_id"]).first()
                models.LevelTier.objects.update_or_create(
                    char_class=class_id, level=level, defaults=dict(
                        exp_required=c["exp_required"], hp_gain=c["hp_gain"],
                        mp_gain=c["mp_gain"], tp_gain=c["tp_gain"],
                        strength_gain=c["strength_gain"], dexterity_gain=c["dexterity_gain"],
                        spell_learned=spell))
        self.stdout.write(f"level tiers: {models.LevelTier.objects.count()}")

        for row in load("drops.json"):
            models.Drop.objects.update_or_create(id=row["id"], defaults=dict(
                name=row["name"], min_monster_level=row["mlevel"], drop_type=row["type"],
                attribute1=str(row.get("attribute1", "")), attribute2=str(row.get("attribute2", ""))))
        self.stdout.write(f"drops: {models.Drop.objects.count()}")

        for row in load("towns.json"):
            town, _ = models.Town.objects.update_or_create(id=row["id"], defaults=dict(
                name=row["name"], latitude=row["latitude"], longitude=row["longitude"],
                inn_price=row["innprice"], map_price=row["mapprice"],
                travel_points=row["travelpoints"]))
            town.shop_items.set(models.Item.objects.filter(id__in=row.get("shop_item_ids", [])))
        self.stdout.write(f"towns: {models.Town.objects.count()}")

        ctrl = load("control.json")
        models.GameControl.objects.update_or_create(id=1, defaults=dict(
            game_name=ctrl.get("gamename", "Dragon Knight"),
            game_size=ctrl.get("gamesize", 250),
            game_open=bool(ctrl.get("gameopen", 1)),
            verify_email=bool(ctrl.get("verifyemail", 0)),
            show_news=bool(ctrl.get("shownews", 1)),
            show_babble=bool(ctrl.get("showbabble", 1)),
            show_online=bool(ctrl.get("showonline", 1)),
            difficulty_medium_mod=ctrl.get("diff2mod", 1.2),
            difficulty_hard_mod=ctrl.get("diff3mod", 1.5)))
        self.stdout.write(self.style.SUCCESS("Seed complete."))
