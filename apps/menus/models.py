# menus/models.py
from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator


class Menu(models.Model):
    key = models.SlugField(unique=True, help_text="Stable key, e.g. 'main', 'footer'.")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Menu"
        verbose_name_plural = "Menus"

    def __str__(self):
        return self.name


class MenuItem(models.Model):
    URL_KIND_CHOICES = [
        ("reverse", "Internal (named URL)"),
        ("path", "Internal (raw path)"),
        ("external", "External URL"),
        ("none", "No link (header/label)"),
    ]
    VISIBILITY_CHOICES = [
        ("public", "Public"),
        ("auth", "Authenticated users"),
        ("staff", "Staff only"),
        ("super", "Superusers only"),
    ]

    menu = models.ForeignKey(Menu, on_delete=models.CASCADE, related_name="items")
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children"
    )

    # Display
    label = models.CharField(max_length=120)
    icon = models.CharField(
        max_length=120, blank=True, help_text="Optional icon class/name"
    )

    # Link behavior
    url_kind = models.CharField(
        max_length=10, choices=URL_KIND_CHOICES, default="reverse"
    )

    # Internal by name: reverse('namespace:name', kwargs=...)
    named_url = models.CharField(
        max_length=200,
        blank=True,
        help_text="Django named URL (e.g. 'services:detail')",
    )
    url_kwargs = models.JSONField(
        blank=True, null=True, help_text="Dict of kwargs for reverse()"
    )
    url_query = models.JSONField(
        blank=True, null=True, help_text="Optional query dict to append"
    )

    # Internal raw path (e.g. '/pricing/')
    internal_path = models.CharField(max_length=300, blank=True)

    # External
    external_url = models.URLField(blank=True)

    open_in_new_tab = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    visibility = models.CharField(
        max_length=10, choices=VISIBILITY_CHOICES, default="public"
    )

    # Mega menu controls (for top-level items only)
    is_mega = models.BooleanField(
        default=False,
        help_text="If true, children render in a wide grid panel on hover (top-level only).",
    )
    mega_columns = models.PositiveSmallIntegerField(
        default=4,
        validators=[MinValueValidator(2), MaxValueValidator(6)],
        help_text="Number of grid columns for the mega panel (2–6).",
    )

    class Meta:
        ordering = ["menu", "parent__id", "order", "id"]
        verbose_name = "Menu item"
        verbose_name_plural = "Menu items"

    def __str__(self):
        return f"{self.label}"

    # Validation
    def clean(self):
        # Link-specific requirements
        if self.url_kind == "reverse" and not self.named_url:
            raise ValidationError("named_url is required when url_kind is 'reverse'.")
        if self.url_kind == "path" and not self.internal_path:
            raise ValidationError("internal_path is required when url_kind is 'path'.")
        if self.url_kind == "external" and not self.external_url:
            raise ValidationError("external_url is required when url_kind is 'external'.")

        # Parent must be in the same Menu
        if self.parent and self.parent.menu_id != self.menu_id:
            raise ValidationError("Parent item must belong to the same Menu.")

        # Mega menu only allowed on top-level items
        if self.is_mega and self.parent_id is not None:
            raise ValidationError("Mega menu can only be enabled on top-level items.")

        # Columns range enforced by validators; nothing else to do here.

    # Compute final href at render time (template tag uses this)
    def resolved_href(self, request=None):
        from django.urls import reverse
        from urllib.parse import urlencode

        if self.url_kind == "none":
            return ""
        if self.url_kind == "reverse":
            href = reverse(self.named_url, kwargs=self.url_kwargs or {})
        elif self.url_kind == "path":
            href = self.internal_path
        else:  # external
            href = self.external_url

        if self.url_query:
            sep = "&" if "?" in href else "?"
            href = f"{href}{sep}{urlencode(self.url_query, doseq=True)}"
        return href

    # Visibility checks
    def is_visible_for(self, user):
        v = self.visibility
        if v == "public":
            return True
        if v == "auth":
            return user.is_authenticated
        if v == "staff":
            return user.is_authenticated and user.is_staff
        if v == "super":
            return user.is_authenticated and user.is_superuser
        return True
