from django.db.models import Case, IntegerField, When
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from startups.constants import CONTACT_ROLE_STRENGTH, ContactFoundVia, ContactStatus
from startups.models import Contact, Startup
from web.constants import CONTACT_STATUS_ORDER
from web.forms import ContactForm, ContactReviewForm


def contacts_context(startup, contact_form):
    return {
        "startup": startup,
        "contacts": _ordered_contacts(startup),
        "contact_form": contact_form,
    }


@require_POST
def contact_create(request, pk):
    startup = get_object_or_404(Startup, pk=pk)
    form = ContactForm(request.POST)
    if not form.is_valid():
        return _render_contacts(request, startup, form, status=400)
    contact = form.save(commit=False)
    contact.startup = startup
    contact.found_via = ContactFoundVia.MANUAL
    contact.status = ContactStatus.CONFIRMED
    contact.save()
    return _render_contacts(request, startup, ContactForm())


@require_POST
def contact_review(request, pk):
    contact = get_object_or_404(Contact.objects.select_related("startup"), pk=pk)
    form = ContactReviewForm(request.POST)
    if form.is_valid():
        contact.status = form.cleaned_data["status"]
        contact.save(update_fields=["status"])
    return _render_contacts(request, contact.startup, ContactForm())


def _render_contacts(request, startup, contact_form, status=200):
    return render(
        request,
        "web/partials/contacts.html",
        contacts_context(startup, contact_form),
        status=status,
    )


def _ordered_contacts(startup):
    return startup.contacts.annotate(
        status_order=_position_of("status", CONTACT_STATUS_ORDER),
        role_order=_position_of("role", CONTACT_ROLE_STRENGTH),
    ).order_by("status_order", "role_order", "full_name", "id")


def _position_of(field_name, ordered_values):
    return Case(
        *[
            When(**{field_name: value}, then=position)
            for position, value in enumerate(ordered_values)
        ],
        default=len(ordered_values),
        output_field=IntegerField(),
    )
