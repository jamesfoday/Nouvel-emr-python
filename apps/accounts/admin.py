# apps/accounts/admin.py
from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.urls import reverse
from django.utils.html import format_html

from .models import User, Invite


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """
    Custom admin for the project's User model.
    - Keep all Django auth capabilities
    - Add display_name + avatar
    - Show avatar thumbnails in list and a preview in the form
    """
    # What to show in the list
    list_display = ("id", "avatar_thumb", "username", "email", "display_name", "is_staff", "is_active")
    search_fields = ("username", "email", "display_name")
    ordering = ("id",)

    # Add our extra fields to the existing Django sections
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Profile", {"fields": ("display_name", "avatar", "avatar_preview")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("Profile", {"fields": ("display_name", "avatar")}),
    )

    # This is a virtual/read-only field rendered in the form
    readonly_fields = ("avatar_preview",)

    # ---- helpers for UI rendering ----
    def avatar_thumb(self, obj: User):
        if obj.avatar:
            return format_html(
                '<img src="{}" style="width:32px;height:32px;object-fit:cover;'
                'border-radius:50%;border:1px solid #ddd;" />',
                obj.avatar.url,
            )
        return "—"

    avatar_thumb.short_description = "Avatar"

    def avatar_preview(self, obj: User):
        if obj.avatar:
            return format_html(
                '<img src="{}" style="width:80px;height:80px;object-fit:cover;'
                'border-radius:50%;border:1px solid #ddd;" />',
                obj.avatar.url,
            )
        return "—"

    avatar_preview.short_description = "Preview"


@admin.register(Invite)
class InviteAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "role", "expires_at", "accepted_at", "accept_link", "created_at")
    list_filter = ("role", "accepted_at")
    search_fields = ("email",)
    ordering = ("-created_at",)

    def accept_link(self, obj: Invite):
        """
        Render a relative URL to accept the invite.
        Make sure you have a URL named 'accounts:accept_invite' that takes the token.
        """
        try:
            url = reverse("accounts:accept_invite", args=[obj.token])
        except Exception:
            # Fallback: just show the token if the route isn't wired
            return obj.token
        return format_html('<a href="{}">Open</a>', url)

    accept_link.short_description = "Accept URL"
