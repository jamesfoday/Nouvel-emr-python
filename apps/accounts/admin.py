from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import User, Invite


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "username", "email", "display_name", "is_staff")
    search_fields = ("username", "email", "display_name")


@admin.register(Invite)
class InviteAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "role", "expires_at", "accepted_at", "accept_link", "created_at")
    list_filter = ("role", "accepted_at")
    search_fields = ("email",)

    def accept_link(self, obj: Invite):
        # rendering a relative link; pair it with your site origin in dev/prod.
        url = reverse("accounts:accept_invite", args=[obj.token])
        return format_html('<a href="{}">Open</a>', url)

    accept_link.short_description = "Accept URL"
