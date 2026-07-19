"""Template context shared by every page (the nav lives in base.html)."""
from .models import Action, Character, Town


def nav(request):
    """Expose the town the player is standing in, so the nav can offer a
    Town link only when there's a town to enter."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    try:
        character = request.user.character
    except Character.DoesNotExist:
        return {}
    if character.current_action != Action.IN_TOWN:
        return {"nav_town": None}
    return {
        "nav_town": Town.objects.filter(
            latitude=character.latitude, longitude=character.longitude
        ).first()
    }
