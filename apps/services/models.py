# apps/services/models.py
from django.conf import settings
from django.db import models
from django.utils.text import slugify


class ServiceCategory(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_public = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Service category"
        verbose_name_plural = "Service categories"

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:140]
        super().save(*args, **kwargs)


class Service(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)

    # Optional marketing fields; safe in templates & search
    summary = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    hero_image = models.ImageField(upload_to="services/heroes/", blank=True, null=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="services_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    categories = models.ManyToManyField(
        "ServiceCategory",  # string ref avoids forward-declare issues
        blank=True,
        related_name="services",
    )

    class Meta:
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title) or "service"
            slug = base
            i = 2
            while Service.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{i}"
                i += 1
            self.slug = slug
        super().save(*args, **kwargs)


class ServiceSection(models.Model):
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="sections"
    )
    heading = models.CharField(max_length=200, blank=True)  # Optional “Section” label
    subtitle = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self) -> str:
        return self.subtitle or f"Section {self.pk}"
