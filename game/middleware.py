import time

from django.utils import timezone

from .models import Character


class LastActiveMiddleware:
    """Stamp the logged-in player's character as active, at most once per 60s per
    session (so it's one small UPDATE per minute of activity, not one per click)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated:
            now = time.time()
            if now - request.session.get("_last_active_write", 0) > 60:
                Character.objects.filter(user=request.user).update(last_active=timezone.now())
                request.session["_last_active_write"] = now
        return response
