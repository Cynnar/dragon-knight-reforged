from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

from game import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("accounts/signup/", views.signup, name="signup"),
    path("character/new/", views.create_character, name="create_character"),
    path("explore/<str:direction>/", views.move, name="move"),
    path("fight/cast/", views.cast_spell, name="cast_spell"),
    path("fight/<str:action>/", views.fight_action, name="fight_action"),
    path("town/inn/", views.inn, name="inn"),
    path("town/shop/", views.shop_view, name="shop"),
    path("town/shop/<slug:slug>/", views.vendor_view, name="vendor"),
    path("town/buy/<int:item_id>/", views.buy_item, name="buy_item"),
    path("town/travel/<int:town_id>/", views.travel, name="travel"),
    path("town/map/<int:town_id>/", views.buy_map, name="buy_map"),
    path("drop/", views.drop_reveal, name="drop_reveal"),
    path("drop/equip/", views.drop_equip, name="drop_equip"),
    path("drop/leave/", views.drop_leave, name="drop_leave"),
    path("tavern/", views.tavern, name="tavern"),
    path("tavern/babble/", views.post_babble, name="post_babble"),
    path("tavern/babbles/", views.babble_list, name="babble_list"),
    path("map/", views.world_map, name="world_map"),
    path("character/", views.character_sheet, name="character_sheet"),
    path("town/", views.town_view, name="town"),
    path("bag/", views.inventory_view, name="inventory"),
    path("bank/", views.bank_view, name="bank"),
    path("quests/", views.quest_board, name="quests"),
    path("quests/accept/<int:quest_id>/", views.quest_accept, name="quest_accept"),
    path("quests/claim/<int:attempt_id>/", views.quest_claim, name="quest_claim"),
    path("quests/abandon/<int:attempt_id>/", views.quest_abandon, name="quest_abandon"),
    path("bank/gold/<str:action>/", views.bank_gold, name="bank_gold"),
    path("bank/item/<str:action>/<int:entry_id>/", views.bank_item, name="bank_item"),
    path("bag/equip/<int:entry_id>/", views.equip, name="equip"),
    path("bag/unequip/<str:slot>/", views.unequip, name="unequip"),
    path("bag/sell/<int:entry_id>/", views.sell, name="sell"),
    path("online/", views.whos_online, name="whos_online"),
    path("forum/", views.forum_index, name="forum_index"),
    path("forum/new/", views.forum_new, name="forum_new"),
    path("forum/<int:thread_id>/", views.forum_thread, name="forum_thread"),
    path("forum/<int:thread_id>/reply/", views.forum_reply, name="forum_reply"),
    path("", views.home, name="home"),
]

# Uploaded media (town images). WhiteNoise handles static files but not media,
# so serve MEDIA_ROOT directly — adequate for a self-hosted game.
urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]
