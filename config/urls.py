from django.contrib import admin
from django.urls import include, path

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
    path("town/buy/<int:item_id>/", views.buy_item, name="buy_item"),
    path("drop/", views.drop_reveal, name="drop_reveal"),
    path("drop/equip/", views.drop_equip, name="drop_equip"),
    path("drop/leave/", views.drop_leave, name="drop_leave"),
    path("tavern/", views.tavern, name="tavern"),
    path("tavern/babble/", views.post_babble, name="post_babble"),
    path("", views.home, name="home"),
]
