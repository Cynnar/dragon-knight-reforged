from django.contrib import admin
from . import models


@admin.register(models.Monster)
class MonsterAdmin(admin.ModelAdmin):
    list_display = ("name", "level", "max_hp", "max_damage", "armor", "max_exp", "max_gold", "immune")
    list_filter = ("level", "immune")
    search_fields = ("name",)


@admin.register(models.Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("name", "slot", "power", "buy_cost", "special")
    list_filter = ("slot",)
    search_fields = ("name",)


@admin.register(models.Spell)
class SpellAdmin(admin.ModelAdmin):
    list_display = ("name", "effect", "mp_cost", "attribute")
    list_filter = ("effect",)
    search_fields = ("name",)


@admin.register(models.LevelTier)
class LevelTierAdmin(admin.ModelAdmin):
    list_display = ("char_class", "level", "exp_required", "hp_gain", "mp_gain",
                    "strength_gain", "dexterity_gain", "spell_learned")
    list_filter = ("char_class",)


@admin.register(models.Drop)
class DropAdmin(admin.ModelAdmin):
    list_display = ("name", "min_monster_level", "drop_type")
    list_filter = ("min_monster_level",)
    search_fields = ("name",)


@admin.register(models.Town)
class TownAdmin(admin.ModelAdmin):
    list_display = ("name", "latitude", "longitude", "inn_price", "travel_points")
    filter_horizontal = ("shop_items",)
    search_fields = ("name",)


@admin.register(models.Character)
class CharacterAdmin(admin.ModelAdmin):
    list_display = ("char_name", "user", "char_class", "level", "current_action", "gold")
    list_filter = ("char_class", "difficulty", "current_action")
    search_fields = ("char_name", "user__username")
    filter_horizontal = ("known_spells", "unlocked_towns")
    raw_id_fields = ("weapon", "armor", "shield", "accessory1", "accessory2", "accessory3",
                     "current_monster", "pending_drop")


@admin.register(models.ForumPost)
class ForumPostAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "parent", "posted_at", "last_reply_at")
    search_fields = ("title", "content")


admin.site.register(models.News)
admin.site.register(models.BabbleMessage)
admin.site.register(models.GameControl)
