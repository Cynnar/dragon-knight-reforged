import json
from datetime import datetime, timezone

from django.contrib import admin, messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import path

from . import models, worldpack


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


@admin.register(models.Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "kind", "sort_order")
    list_editable = ("sort_order",)
    prepopulated_fields = {"slug": ("name",)}


class TownSectionInline(admin.StackedInline):
    """Edit a town's description blocks right on the town record."""
    model = models.TownSection
    extra = 1
    fields = ("heading", "body", "sort_order", "is_active")


class TownImageInline(admin.TabularInline):
    """Swap a town's picture — upload several and flip which one is active."""
    model = models.TownImage
    extra = 1
    fields = ("image", "caption", "is_active", "sort_order")


@admin.register(models.Town)
class TownAdmin(admin.ModelAdmin):
    list_display = ("name", "latitude", "longitude", "inn_price", "travel_points")
    filter_horizontal = ("shop_items", "vendors")
    inlines = [TownSectionInline, TownImageInline]
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
@admin.register(models.GameControl)
class GameControlAdmin(admin.ModelAdmin):
    """Live game tuning — drop rate and encounter rate take effect immediately."""
    fieldsets = (
        ("Game", {"fields": ("game_name", "game_size", "game_open")}),
        ("Vendors", {
            "fields": ("vendor_mode",),
            "description": "By stock = counters appear wherever a town has matching goods. "
                           "Assigned = each town shows exactly the vendors picked on the town record.",
        }),
        ("Rates", {
            "fields": ("drop_rate", "encounter_rate", "bank_slots"),
            "description": "Drop and encounter rates are '1 in N' chances — lower means more. "
                           "Bank slots caps stored items (0 = unlimited).",
        }),
        ("Difficulty", {"fields": ("difficulty_medium_mod", "difficulty_hard_mod")}),
        ("Features", {"fields": ("verify_email", "show_news", "show_babble", "show_online")}),
    )
    list_display = ("game_name", "vendor_mode", "drop_rate", "encounter_rate", "game_open")

    # ── world pack tools ────────────────────────────────────────────────────
    def get_urls(self):
        tools = [
            path("world/export/", self.admin_site.admin_view(self.export_world_view),
                 name="game_world_export"),
            path("world/import/", self.admin_site.admin_view(self.import_world_view),
                 name="game_world_import"),
        ]
        return tools + super().get_urls()

    def export_world_view(self, request):
        """Download the whole world as a JSON pack."""
        payload = json.dumps(worldpack.export_world(), indent=2, ensure_ascii=False)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        response = HttpResponse(payload, content_type="application/json")
        response["Content-Disposition"] = f'attachment; filename="world-{stamp}.json"'
        return response

    def import_world_view(self, request):
        """Upload a pack, optionally replacing the current world outright."""
        if request.method == "POST" and request.FILES.get("pack"):
            replace = bool(request.POST.get("replace"))
            try:
                pack = json.load(request.FILES["pack"])
                counts = worldpack.import_world(pack, replace=replace)
            except json.JSONDecodeError:
                self.message_user(request, "That file isn't valid JSON.", level=messages.ERROR)
            except ValueError as exc:
                self.message_user(request, f"Import failed: {exc}", level=messages.ERROR)
            else:
                summary = ", ".join(f"{v} {k}" for k, v in counts.items())
                self.message_user(
                    request,
                    f"World {'replaced' if replace else 'merged'} — now holding {summary}.",
                    level=messages.SUCCESS,
                )
                return redirect("admin:game_gamecontrol_changelist")
        context = {
            **self.admin_site.each_context(request),
            "title": "Import world pack",
            "opts": self.model._meta,
        }
        return render(request, "admin/game/world_import.html", context)


@admin.register(models.InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ("character", "name", "location", "acquired_at")
    list_filter = ("location",)
    search_fields = ("character__char_name",)
    raw_id_fields = ("character", "item", "drop")


@admin.register(models.Quest)
class QuestAdmin(admin.ModelAdmin):
    """Create, edit and retire quests without touching code."""
    list_display = ("name", "objective", "min_level", "giver_town", "reward_exp",
                    "reward_gold", "repeatable", "is_active")
    list_filter = ("objective", "is_active", "repeatable", "giver_town")
    search_fields = ("name", "summary")
    list_editable = ("is_active",)
    fieldsets = (
        (None, {"fields": ("name", "summary", "is_active", "sort_order")}),
        ("Objective", {
            "fields": ("objective", "target_monster", "required_count",
                       "target_town", "target_level"),
            "description": "Fill in only the fields that match the objective type.",
        }),
        ("Availability", {"fields": ("giver_town", "min_level", "repeatable")}),
        ("Rewards", {"fields": ("reward_exp", "reward_gold", "reward_item")}),
    )


@admin.register(models.CharacterQuest)
class CharacterQuestAdmin(admin.ModelAdmin):
    list_display = ("character", "quest", "state", "progress", "accepted_at", "completed_at")
    list_filter = ("state",)
    search_fields = ("character__char_name", "quest__name")
    raw_id_fields = ("character", "quest")
