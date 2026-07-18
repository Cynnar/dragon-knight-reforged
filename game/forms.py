import re

from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Character


class SignupForm(UserCreationForm):
    """Account signup. Subclasses Django's built-in form so we can add fields later."""
    class Meta(UserCreationForm.Meta):
        pass


CHARNAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class CharacterForm(forms.ModelForm):
    """Character creation: the player picks only name, class, and difficulty —
    everything else uses the model's starting defaults (HP 15, gold 100, pos 0,0)."""

    class Meta:
        model = Character
        fields = ["char_name", "char_class", "difficulty"]
        labels = {"char_name": "Character name", "char_class": "Class", "difficulty": "Difficulty"}

    def clean_char_name(self):
        name = self.cleaned_data["char_name"].strip()
        if not CHARNAME_RE.match(name):
            raise forms.ValidationError("Letters, numbers, underscores and hyphens only.")
        if Character.objects.filter(char_name__iexact=name).exists():
            raise forms.ValidationError("That character name is already taken.")
        return name
