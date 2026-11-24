from django import forms
from django.utils import timezone

from sources.constants import SourceKey
from startups.constants import ContactStatus, StartupStatus
from startups.locations import country_choices
from startups.models import Analysis, Contact
from web.constants import (
    ANALYSIS_FILTER_CHOICES,
    CONTACT_FILTER_CHOICES,
    CONTACT_WITHOUT_CHANNEL_MESSAGE,
    OPENINGS_FILTER_CHOICES,
    ORDER_CHOICES,
    TIMEZONE_FILTER_CHOICES,
)


class StartupFilterForm(forms.Form):
    openings = forms.ChoiceField(required=False, label="Búsquedas", choices=OPENINGS_FILTER_CHOICES)
    role = forms.CharField(required=False, label="Puesto contiene")
    remote = forms.BooleanField(required=False, label="Con puesto remoto")
    q = forms.CharField(required=False, label="Buscar")
    status = forms.ChoiceField(
        required=False,
        label="Estado",
        choices=[("", "Activas (sin descartadas)"), *StartupStatus.choices],
    )
    source = forms.ChoiceField(
        required=False, label="Fuente", choices=[("", "Todas"), *SourceKey.choices]
    )
    timezone = forms.ChoiceField(
        required=False, label="Zona horaria", choices=TIMEZONE_FILTER_CHOICES
    )
    country = forms.CharField(required=False, label="País (código)", max_length=2)
    contact = forms.ChoiceField(required=False, label="Contacto", choices=CONTACT_FILTER_CHOICES)
    analysis = forms.ChoiceField(required=False, label="Análisis", choices=ANALYSIS_FILTER_CHOICES)
    since = forms.DateField(
        required=False, label="Vista desde", widget=forms.DateInput(attrs={"type": "date"})
    )
    order = forms.ChoiceField(required=False, label="Orden", choices=ORDER_CHOICES)


class LocationForm(forms.Form):
    country = forms.ChoiceField(label="País", choices=country_choices)
    city = forms.CharField(max_length=255, required=False, label="Ciudad (opcional)")


class DiscardForm(forms.Form):
    reason = forms.CharField(max_length=255, label="Motivo")


class StatusForm(forms.Form):
    status = forms.ChoiceField(choices=StartupStatus.choices, label="Estado")
    note = forms.CharField(max_length=255, required=False, label="Nota")


class ContactForm(forms.ModelForm):
    profile_url = forms.URLField(
        required=False, max_length=500, assume_scheme="https", label="Perfil (LinkedIn u otro)"
    )

    class Meta:
        model = Contact
        fields = ["full_name", "role", "email", "profile_url"]
        labels = {
            "full_name": "Nombre",
            "role": "Cargo",
            "email": "Mail",
            "profile_url": "Perfil (LinkedIn u otro)",
        }

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("email") and not cleaned_data.get("profile_url"):
            raise forms.ValidationError(CONTACT_WITHOUT_CHANNEL_MESSAGE)
        return cleaned_data


class ContactReviewForm(forms.Form):
    status = forms.ChoiceField(choices=ContactStatus.choices)


class AnalysisForm(forms.ModelForm):
    class Meta:
        model = Analysis
        fields = ["title", "body"]
        labels = {"title": "Título", "body": "Análisis (Markdown)"}
        widgets = {"body": forms.Textarea(attrs={"rows": 18})}


class MarkSentForm(forms.Form):
    sent_on = forms.DateField(
        label="Enviado el",
        widget=forms.DateInput(attrs={"type": "date"}),
        initial=timezone.localdate,
    )
    sent_to = forms.ModelChoiceField(
        queryset=Contact.objects.none(), required=False, label="A", empty_label="(sin indicar)"
    )

    def __init__(self, *args, startup, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sent_to"].queryset = startup.contacts.exclude(status=ContactStatus.REJECTED)


class ManualEntryForm(forms.Form):
    website = forms.CharField(max_length=500, label="URL de la startup")
    name = forms.CharField(max_length=255, required=False, label="Nombre (opcional)")


class MergeForm(forms.Form):
    keep = forms.IntegerField(widget=forms.HiddenInput)
