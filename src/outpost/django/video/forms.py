from django import forms
from outpost.django.campusonline import models as campusonline

from . import models


class PushLiveEventForm(forms.ModelForm):

    class Meta:
        model = models.PushLiveEvent
        exclude = (
            "user",
            "users",
        )


class PushLiveIngestForm(forms.ModelForm):

    class Meta:
        model = models.PushLiveIngest
        fields = '__all__'


class PushEventUserForm(forms.Form):
    personal = forms.CharField()
    students = forms.CharField()
    external = forms.CharField()
