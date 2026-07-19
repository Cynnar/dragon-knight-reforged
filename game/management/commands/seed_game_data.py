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

        # Default merchants. These are ordinary rows — rename, re-blurb or
        # replace them freely for a different world.
        for order, (slug, name, kind, blurb) in enumerate([
            ("weapons", "Weaponsmith", 1, "Blades, clubs and other means of persuasion."),
            ("armor", "Armorer", 2, "Plate, mail and shields to keep you breathing."),
            ("magic", "Enchanter", 3, "Curious goods humming with power."),
            ("maps", "Cartographer", 4, "Charts to distant towns."),
        ], start=1):
            models.Vendor.objects.update_or_create(
                slug=slug,
                defaults=dict(name=name, kind=kind, blurb=blurb, sort_order=order),
            )
        self.stdout.write(f"vendors: {models.Vendor.objects.count()}")

        # Seed the per-town assignment to mirror what each town stocks, so
        # switching the admin toggle to "Assigned" starts from a sane default.
        from game import vendors as vendor_rules
        for town in models.Town.objects.all():
            matching = [
                v for v in models.Vendor.objects.all()
                if (vendor_rules.maps_for_sale_count(town) if v.kind == 4
                    else vendor_rules.items_for_kind(v.kind, town).count())
            ]
            town.vendors.set(matching)

        # ── town descriptions ───────────────────────────────────────────
        # Flavour only; edit or replace freely in the admin.
        town_blurbs = {
            "Midworld": [("The Crossroads",
                "Every road in the realm passes through Midworld sooner or later. "
                "It is neither the largest town nor the richest, but it sits at the "
                "centre of the map and every adventurer starts here.")],
            "Roma": [("The Terraced Town",
                "Built up the side of a green hill, Roma looks down on the eastern "
                "plains. Traders come for the markets and stay for the wine.")],
            "Bris": [("The Salt Gate",
                "Wind-scoured and stubborn, Bris guards the southern reaches. "
                "Its smiths are said to fold sea-salt into their steel.")],
            "Kalle": [("The Quiet North",
                "Kalle keeps to itself among the northern pines. Strangers are served "
                "politely and watched carefully.")],
            "Narcissa": [("The Mirror City",
                "Narcissa's towers are faced with polished stone, and the city is "
                "proud of its reflection. Magic is common here, and expensive.")],
            "Hambry": [("The Far Fields",
                "A long way from anywhere, Hambry survives on hard work and harder "
                "weather. The monsters beyond its walls are no longer small.")],
            "Gilead": [("The Old Seat",
                "Once the heart of the realm, Gilead still carries itself like a "
                "capital. Only the strongest travellers arrive here on foot.")],
            "Endworld": [("The Last Town",
                "At the very corner of the known map, Endworld exists because someone "
                "refused to turn back. Beyond it, the maps go blank.")],
        }
        made = 0
        for town_name, blocks in town_blurbs.items():
            town = models.Town.objects.filter(name=town_name).first()
            if not town:
                continue
            for order, (heading, body) in enumerate(blocks, start=1):
                models.TownSection.objects.update_or_create(
                    town=town, heading=heading,
                    defaults=dict(body=body, sort_order=order, is_active=True))
                made += 1
        self.stdout.write(f"town sections: {made}")

        # ── starter quests ──────────────────────────────────────────────
        # Looked up by name so a replaced world degrades gracefully rather
        # than failing: a missing monster just means "any monster".
        def monster(name):
            return models.Monster.objects.filter(name=name).first()

        def town(name):
            return models.Town.objects.filter(name=name).first()

        starter_quests = [
            dict(name="A Slime Problem",
                 summary="The fields outside the gates are crawling with them. Thin them out.",
                 objective=1, target_monster=monster("Blue Slime"), required_count=3,
                 giver_town=town("Midworld"), min_level=1,
                 reward_exp=15, reward_gold=40, sort_order=1),
            dict(name="Blooded",
                 summary="Every adventurer has a first ten. Go and get yours.",
                 objective=1, target_monster=None, required_count=10,
                 giver_town=None, min_level=1,
                 reward_exp=40, reward_gold=75, sort_order=2),
            dict(name="The Road East",
                 summary="Roma lies east of the crossroads. See it with your own eyes.",
                 objective=3, target_town=town("Roma"),
                 giver_town=town("Midworld"), min_level=1,
                 reward_exp=30, reward_gold=60, sort_order=3),
            dict(name="Prove Yourself",
                 summary="Come back when you've grown into your boots.",
                 objective=2, target_level=5,
                 giver_town=None, min_level=1,
                 reward_exp=60, reward_gold=120, sort_order=4),
            dict(name="Standing Bounty",
                 summary="The board always has work. Bring proof of five kills.",
                 objective=1, target_monster=None, required_count=5,
                 giver_town=None, min_level=2, repeatable=True,
                 reward_exp=25, reward_gold=50, sort_order=5),
            dict(name="Journeyman",
                 summary="A seasoned hand is worth more than a sharp sword.",
                 objective=2, target_level=10,
                 giver_town=None, min_level=5,
                 reward_exp=150, reward_gold=400, sort_order=6),
        ]
        for q in starter_quests:
            name = q.pop("name")
            models.Quest.objects.update_or_create(name=name, defaults=q)
        self.stdout.write(f"quests: {models.Quest.objects.count()}")

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
