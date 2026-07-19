"""
Dragon Knight — data models.

These map the 11 tables of the original PHP game onto Django's ORM. Where the original
schema had warts (denormalized name columns, CSV-in-a-varchar, no foreign keys, a
users table that mixed account + game state), this cleans them up. Every such change is
called out in a comment so the lineage stays clear.

Integer choice values are kept IDENTICAL to the original codes (item type 1/2/3, spell
type 1-5, immune 0/1/2, class 1/2/3, difficulty 1/2/3). That means the extracted JSON in
`data/` loads straight into these models without remapping.
"""
from django.conf import settings
from django.db import models


# ─────────────────────────────────────────────────────────────────────────────
# Shared enumerations (original integer codes preserved as the values)
# ─────────────────────────────────────────────────────────────────────────────
class CharClass(models.IntegerChoices):
    MAGE = 1, "Mage"
    WARRIOR = 2, "Warrior"
    PALADIN = 3, "Paladin"


class Difficulty(models.IntegerChoices):
    EASY = 1, "Easy"
    MEDIUM = 2, "Medium"
    HARD = 3, "Hard"


class EquipSlot(models.IntegerChoices):
    WEAPON = 1, "Weapon"
    ARMOR = 2, "Armor"
    SHIELD = 3, "Shield"


class SpellEffect(models.IntegerChoices):
    HEAL = 1, "Heal"
    DAMAGE = 2, "Damage"
    SLEEP = 3, "Sleep"
    BUFF_DAMAGE = 4, "Buff: Damage"
    BUFF_DEFENSE = 5, "Buff: Defense"


class MonsterImmunity(models.IntegerChoices):
    NONE = 0, "None"
    DAMAGE_MAGIC = 1, "Immune to damage magic"
    SLEEP = 2, "Immune to sleep"


class VendorKind(models.IntegerChoices):
    """What a vendor deals in. The *kind* drives which goods it shows; the
    vendor's name, blurb and ordering are all editable data."""
    WEAPONS = 1, "Weapons"
    ARMOR = 2, "Armor & shields"
    MAGIC = 3, "Enchanted goods"
    MAPS = 4, "Maps"
    GENERAL = 5, "General store"


class VendorMode(models.IntegerChoices):
    BY_STOCK = 1, "By stock — a vendor appears if the town has goods for it"
    ASSIGNED = 2, "Assigned — each town lists exactly the vendors you choose"


class Action(models.TextChoices):
    # Original stored these as the strings "In Town" / "Exploring" / "Fighting";
    # normalized to tokens here.
    IN_TOWN = "in_town", "In Town"
    EXPLORING = "exploring", "Exploring"
    FIGHTING = "fighting", "Fighting"


# ─────────────────────────────────────────────────────────────────────────────
# Static game content (the "data/" JSON files load into these)
# ─────────────────────────────────────────────────────────────────────────────
class Monster(models.Model):
    """Bestiary. Original table: monsters."""
    name = models.CharField(max_length=50)
    max_hp = models.PositiveIntegerField()
    max_damage = models.PositiveIntegerField()
    armor = models.PositiveIntegerField()
    level = models.PositiveIntegerField(help_text="Tier; drives where it spawns and what it can drop.")
    max_exp = models.PositiveIntegerField()
    max_gold = models.PositiveIntegerField()
    immune = models.IntegerField(choices=MonsterImmunity.choices, default=MonsterImmunity.NONE)

    class Meta:
        ordering = ["level", "name"]

    def __str__(self):
        return f"{self.name} (lv {self.level})"


class Item(models.Model):
    """Equipment. Original table: items. `type` -> `slot`, `attribute` -> `power`."""
    slot = models.IntegerField(choices=EquipSlot.choices)
    name = models.CharField(max_length=30)
    buy_cost = models.PositiveIntegerField(default=0)
    power = models.PositiveIntegerField(
        default=0, help_text="Attack power for weapons; defense power for armor/shields."
    )
    # Original stored "X" for none; we store NULL. Effect semantics live in the equip
    # logic (towns.php) and will be formalized when the inventory system is built.
    special = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        ordering = ["slot", "power"]

    def __str__(self):
        return f"{self.name} ({self.get_slot_display()} +{self.power})"


class Spell(models.Model):
    """Spell book. Original table: spells. `type` -> `effect`, `mp` -> `mp_cost`."""
    name = models.CharField(max_length=30)
    mp_cost = models.PositiveIntegerField()
    effect = models.IntegerField(choices=SpellEffect.choices)
    attribute = models.PositiveIntegerField(
        help_text="Meaning depends on effect: HP healed, max damage, sleep turns, or % buff."
    )

    class Meta:
        ordering = ["effect", "mp_cost"]

    def __str__(self):
        return f"{self.name} ({self.get_effect_display()})"


class LevelTier(models.Model):
    """
    Level-up curve. Original table: levels — one row per level with three sets of
    per-class columns (1_exp, 2_exp, ...). Normalized here to one row per
    (class, level), so 100 levels x 3 classes = 300 rows. Much easier to query
    ("gains for a warrior reaching level 5") and to seed from levels.json.
    """
    char_class = models.IntegerField(choices=CharClass.choices)
    level = models.PositiveIntegerField()
    exp_required = models.PositiveIntegerField(help_text="Cumulative experience to reach this level.")
    hp_gain = models.PositiveIntegerField(default=0)
    mp_gain = models.PositiveIntegerField(default=0)
    tp_gain = models.PositiveIntegerField(default=0)
    strength_gain = models.PositiveIntegerField(default=0)
    dexterity_gain = models.PositiveIntegerField(default=0)
    spell_learned = models.ForeignKey(
        Spell, on_delete=models.SET_NULL, null=True, blank=True, related_name="learned_at_tiers"
    )

    class Meta:
        ordering = ["char_class", "level"]
        constraints = [
            models.UniqueConstraint(fields=["char_class", "level"], name="unique_class_level")
        ]

    def __str__(self):
        return f"{self.get_char_class_display()} L{self.level}"


class Drop(models.Model):
    """Droppable-item table. Original table: drops."""
    name = models.CharField(max_length=30)
    min_monster_level = models.PositiveIntegerField(
        help_text="Only monsters at or above this level can drop it (original: mlevel)."
    )
    # type / attribute1 / attribute2 encode the effect payload; kept close to the
    # original for now and decoded when the item/effect system is built.
    drop_type = models.PositiveIntegerField(default=0)
    attribute1 = models.CharField(max_length=30, blank=True)
    attribute2 = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["min_monster_level", "name"]

    def __str__(self):
        return self.name


class Vendor(models.Model):
    """A shop counter. Fully admin-editable so a new world can rename or replace
    the whole cast of merchants without touching code."""
    name = models.CharField(max_length=40)
    slug = models.SlugField(max_length=40, unique=True)
    kind = models.IntegerField(choices=VendorKind.choices)
    blurb = models.CharField(max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class Town(models.Model):
    """
    Towns. Original table: towns. The original `itemslist` was a CSV of item IDs in a
    text column — modeled here as a proper many-to-many to Item.
    """
    name = models.CharField(max_length=30)
    latitude = models.IntegerField()
    longitude = models.IntegerField()
    inn_price = models.PositiveIntegerField(default=0, help_text="Cost to fully heal at the inn.")
    map_price = models.PositiveIntegerField(default=0)
    travel_points = models.PositiveIntegerField(default=0)
    shop_items = models.ManyToManyField(Item, blank=True, related_name="sold_in_towns")
    vendors = models.ManyToManyField(
        Vendor, blank=True, related_name="towns",
        help_text="Used when the vendor mode is 'Assigned'. Ignored in 'By stock' mode.",
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["latitude", "longitude"], name="unique_town_coords")
        ]

    def __str__(self):
        return f"{self.name} ({self.latitude},{self.longitude})"


class TownSection(models.Model):
    """A block of descriptive text on a town's page.

    One-to-many so a town can carry several blocks — an overview, some history,
    rumours from the inn — each editable and reorderable in the admin without
    touching the town's mechanical data.
    """
    town = models.ForeignKey(Town, on_delete=models.CASCADE, related_name="sections")
    heading = models.CharField(max_length=80, blank=True)
    body = models.TextField()
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, help_text="Untick to hide without deleting.")

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.town.name}: {self.heading or self.body[:30]}"


class TownImage(models.Model):
    """A picture for a town's page.

    Several may exist per town with only one active, so an admin can swap the
    view — a peaceful market today, smouldering ruins after a raid — without
    losing the original. Files live under MEDIA_ROOT/towns/, which keeps them
    portable alongside a world pack.
    """
    town = models.ForeignKey(Town, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="towns/")
    caption = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(
        default=True, help_text="Only the first active image is shown.")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.town.name} image {self.pk}"


# ─────────────────────────────────────────────────────────────────────────────
# Player state
# ─────────────────────────────────────────────────────────────────────────────
class Character(models.Model):
    """
    Per-player game state. Original table: users — BUT that table mixed account data
    (username, password, email, authlevel/ban) with game state. In Django the account
    half belongs to the built-in auth.User (proper password hashing, sessions, admin,
    is_staff/is_superuser for the old authlevel, is_active for bans). So this model holds
    ONLY the game state and links one-to-one to a User. The old denormalized *name
    columns (weaponname, armorname, ...) are gone — a foreign key gives the name for free.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="character"
    )
    char_name = models.CharField(max_length=30)
    char_class = models.IntegerField(choices=CharClass.choices)
    difficulty = models.IntegerField(choices=Difficulty.choices, default=Difficulty.EASY)

    # Position on the grid.
    latitude = models.IntegerField(default=0)
    longitude = models.IntegerField(default=0)

    # What the character is currently doing + transient fight state.
    current_action = models.CharField(max_length=20, choices=Action.choices, default=Action.IN_TOWN)
    current_monster = models.ForeignKey(
        Monster, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    current_monster_hp = models.PositiveIntegerField(default=0)
    current_monster_max_hp = models.PositiveIntegerField(
        default=0, help_text="The monster's rolled starting HP, for the enemy health bar."
    )
    current_monster_sleep = models.PositiveIntegerField(default=0, help_text="Turns remaining asleep.")
    current_monster_immune = models.IntegerField(choices=MonsterImmunity.choices, default=MonsterImmunity.NONE)
    uber_damage = models.PositiveIntegerField(default=0, help_text="Active % damage buff this fight.")
    uber_defense = models.PositiveIntegerField(default=0, help_text="Active % defense buff this fight.")

    # Vitals.
    current_hp = models.IntegerField(default=15)
    current_mp = models.IntegerField(default=0)
    current_tp = models.IntegerField(default=10)
    max_hp = models.PositiveIntegerField(default=15)
    max_mp = models.PositiveIntegerField(default=0)
    max_tp = models.PositiveIntegerField(default=10)

    # Progression. (Original capped exp/gold at the mediumint max of 16,777,215 —
    # that was a column limit, not a design choice, so it's dropped here.)
    level = models.PositiveIntegerField(default=1)
    experience = models.PositiveBigIntegerField(default=0)
    gold = models.PositiveBigIntegerField(default=100)
    exp_bonus = models.IntegerField(default=0, help_text="Percent bonus to exp gained.")
    gold_bonus = models.IntegerField(default=0, help_text="Percent bonus to gold gained.")

    strength = models.PositiveIntegerField(default=5)
    dexterity = models.PositiveIntegerField(default=5)
    attack_power = models.PositiveIntegerField(default=5)
    defense_power = models.PositiveIntegerField(default=5)

    # Equipment — FKs replace the old id+name column pairs.
    weapon = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    armor = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    shield = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    accessory1 = models.ForeignKey(Drop, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    accessory2 = models.ForeignKey(Drop, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    accessory3 = models.ForeignKey(Drop, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    # Known spells + unlocked towns were CSV strings in the original; now real M2Ms.
    known_spells = models.ManyToManyField(Spell, blank=True, related_name="known_by")
    unlocked_towns = models.ManyToManyField(Town, blank=True, related_name="unlocked_by")

    # Pending post-victory drop (original: dropcode).
    pending_drop = models.ForeignKey(
        Drop, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    # Gold left with the bank — safe from the death penalty.
    bank_gold = models.PositiveBigIntegerField(default=0)

    # Live-presence tracking for the who's-online list.
    last_active = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["char_name"]

    @property
    def equipped_slots(self):
        """(label, slot key, equipped thing) for every slot — drives the bag UI."""
        return [
            ("Weapon", "weapon", self.weapon),
            ("Armor", "armor", self.armor),
            ("Shield", "shield", self.shield),
            ("Slot 1", "accessory1", self.accessory1),
            ("Slot 2", "accessory2", self.accessory2),
            ("Slot 3", "accessory3", self.accessory3),
        ]

    def __str__(self):
        return f"{self.char_name} (L{self.level} {self.get_char_class_display()})"


# ─────────────────────────────────────────────────────────────────────────────
# Community / world flavor
# ─────────────────────────────────────────────────────────────────────────────
class ForumPost(models.Model):
    """Forum. Original table: forum. Threading via self-referential parent."""
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="forum_posts"
    )
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies"
    )
    title = models.CharField(max_length=100)
    content = models.TextField()
    posted_at = models.DateTimeField(auto_now_add=True)
    last_reply_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-last_reply_at"]

    def __str__(self):
        return self.title


class News(models.Model):
    """Front-page news. Original table: news."""
    content = models.TextField()
    posted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-posted_at"]
        verbose_name_plural = "news"

    def __str__(self):
        return f"News #{self.pk}"


class BabbleMessage(models.Model):
    """Shoutbox. Original table: babble. Author linked to a User where possible."""
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="babbles"
    )
    message = models.CharField(max_length=120)
    posted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-posted_at"]

    def __str__(self):
        return f"{self.author}: {self.message[:30]}"


class GameControl(models.Model):
    """
    Global game config. Original table: control (a single row). Kept as an editable
    singleton so it shows up in the admin; some of this could later move to settings.
    """
    game_name = models.CharField(max_length=50, default="Dragon Knight")
    game_size = models.PositiveIntegerField(default=250, help_text="Map half-extent from origin.")
    game_open = models.BooleanField(default=True)
    verify_email = models.BooleanField(default=False)
    show_news = models.BooleanField(default=True)
    show_babble = models.BooleanField(default=True)
    show_online = models.BooleanField(default=True)
    difficulty_medium_mod = models.FloatField(default=1.2)
    difficulty_hard_mod = models.FloatField(default=1.5)

    # Tuning knobs (editable in the admin — no redeploy needed).
    drop_rate = models.PositiveIntegerField(
        default=30,
        help_text="Loot drop chance after a victory: 1 in N. Lower = more drops (1 = every kill).",
    )
    vendor_mode = models.IntegerField(
        choices=VendorMode.choices, default=VendorMode.BY_STOCK,
        help_text="How each town decides which shop counters to show.",
    )
    bank_slots = models.PositiveIntegerField(
        default=20,
        help_text="How many items a character may store in the bank. 0 means unlimited.",
    )
    encounter_rate = models.PositiveIntegerField(
        default=5,
        help_text="Random encounter chance per tile travelled: 1 in N. Lower = more fights.",
    )

    class Meta:
        verbose_name = "game control"
        verbose_name_plural = "game control"

    def __str__(self):
        return self.game_name


class VisitedTile(models.Model):
    """One row per map tile a character has stepped on — powers the minimap.
    Cheap to write (one per new tile) and indexed for fast window queries."""
    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name="visited_tiles")
    latitude = models.IntegerField()
    longitude = models.IntegerField()
    first_seen = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["character", "latitude", "longitude"],
                                    name="unique_visited_tile")
        ]
        indexes = [models.Index(fields=["character", "latitude", "longitude"])]

    def __str__(self):
        return f"{self.character.char_name} @({self.latitude},{self.longitude})"


class ItemLocation(models.IntegerChoices):
    BAG = 1, "Bag"
    BANK = 2, "Bank vault"


class InventoryItem(models.Model):
    """One unequipped thing in a character's bag.

    The game has two item families — shop gear (Item: weapon/armor/shield) and
    accessory loot (Drop) — so a row points at exactly one of them. Equipping
    removes the row and sets the character's slot; unequipping puts a row back.
    """
    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name="inventory")
    item = models.ForeignKey(Item, on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    drop = models.ForeignKey(Drop, on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    location = models.IntegerField(choices=ItemLocation.choices, default=ItemLocation.BAG)
    acquired_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["acquired_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(item__isnull=False, drop__isnull=True)
                    | models.Q(item__isnull=True, drop__isnull=False)
                ),
                name="inventory_item_xor_drop",
            )
        ]

    @property
    def thing(self):
        """The underlying Item or Drop."""
        return self.item or self.drop

    @property
    def name(self):
        return self.thing.name if self.thing else "—"

    @property
    def is_accessory(self):
        return self.drop_id is not None

    def __str__(self):
        return f"{self.character.char_name}: {self.name}"


# ─────────────────────────────────────────────────────────────────────────────
# Quests
# ─────────────────────────────────────────────────────────────────────────────
class QuestObjective(models.IntegerChoices):
    """What finishing a quest actually requires. New kinds go here in code;
    everything else about a quest is admin-editable data."""
    SLAY = 1, "Slay monsters"
    REACH_LEVEL = 2, "Reach a level"
    VISIT_TOWN = 3, "Visit a town"


class QuestState(models.IntegerChoices):
    ACTIVE = 1, "In progress"
    READY = 2, "Ready to hand in"
    DONE = 3, "Completed"


class Quest(models.Model):
    """A goal offered on a town's quest board. Create, edit and retire these
    entirely from the admin."""
    name = models.CharField(max_length=80)
    summary = models.TextField(blank=True, help_text="Flavour text shown on the board.")
    objective = models.IntegerField(choices=QuestObjective.choices, default=QuestObjective.SLAY)

    # Objective parameters — only the ones relevant to the chosen objective matter.
    target_monster = models.ForeignKey(
        Monster, on_delete=models.SET_NULL, null=True, blank=True, related_name="quests",
        help_text="Slay quests: which monster. Leave empty to count any monster.",
    )
    target_town = models.ForeignKey(
        Town, on_delete=models.SET_NULL, null=True, blank=True, related_name="quest_targets",
        help_text="Visit quests: which town to reach.",
    )
    target_level = models.PositiveIntegerField(
        default=0, help_text="Reach-level quests: the level required.")
    required_count = models.PositiveIntegerField(
        default=1, help_text="Slay quests: how many kills are needed.")

    # Where it's offered and who may take it.
    giver_town = models.ForeignKey(
        Town, on_delete=models.CASCADE, null=True, blank=True, related_name="quests",
        help_text="Which town's board offers it. Leave empty to offer it everywhere.",
    )
    min_level = models.PositiveIntegerField(default=1)

    # Rewards.
    reward_gold = models.PositiveIntegerField(default=0)
    reward_exp = models.PositiveIntegerField(default=0)
    reward_item = models.ForeignKey(
        Item, on_delete=models.SET_NULL, null=True, blank=True, related_name="quest_rewards")

    repeatable = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, help_text="Untick to retire without deleting.")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "min_level", "name"]

    @property
    def goal_total(self):
        """How many 'units' completion takes, for progress display."""
        if self.objective == QuestObjective.SLAY:
            return max(1, self.required_count)
        return 1

    def describe(self):
        if self.objective == QuestObjective.SLAY:
            who = self.target_monster.name if self.target_monster_id else "monsters"
            return f"Slay {self.required_count} {who}"
        if self.objective == QuestObjective.REACH_LEVEL:
            return f"Reach level {self.target_level}"
        if self.objective == QuestObjective.VISIT_TOWN:
            where = self.target_town.name if self.target_town_id else "a distant town"
            return f"Travel to {where}"
        return self.get_objective_display()

    def __str__(self):
        return self.name


class CharacterQuest(models.Model):
    """One character's run at one quest."""
    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name="quests")
    quest = models.ForeignKey(Quest, on_delete=models.CASCADE, related_name="attempts")
    state = models.IntegerField(choices=QuestState.choices, default=QuestState.ACTIVE)
    progress = models.PositiveIntegerField(default=0)
    accepted_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-accepted_at"]
        indexes = [models.Index(fields=["character", "state"])]

    @property
    def percent(self):
        total = self.quest.goal_total
        return int(min(100, self.progress * 100 / total)) if total else 0

    def __str__(self):
        return f"{self.character.char_name}: {self.quest.name}"
