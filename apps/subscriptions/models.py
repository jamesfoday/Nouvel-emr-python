from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator

class PlanInterval(models.TextChoices):
    MONTH = "month", "Monthly"
    YEAR  = "year", "Yearly"

class Plan(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    price_cents = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    interval = models.CharField(max_length=10, choices=PlanInterval.choices, default=PlanInterval.MONTH)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    # Stripe hook (optional)
    stripe_price_id = models.CharField(max_length=120, blank=True, help_text="Stripe Price ID (price_...)")

    # Feature flags (simple MVP; expand later)
    max_patients = models.PositiveIntegerField(default=100)
    max_staff    = models.PositiveIntegerField(default=3)
    storage_mb   = models.PositiveIntegerField(default=512)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "price_cents"]

    def __str__(self):
        return f"{self.name} ({self.get_interval_display()})"

    @property
    def price_display(self):
        return f"€{self.price_cents/100:.2f}/{self.interval}"

class SubscriptionStatus(models.TextChoices):
    ACTIVE    = "active", "Active"
    CANCELED  = "canceled", "Canceled"
    PAST_DUE  = "past_due", "Past due"
    TRIALING  = "trialing", "Trialing"
    INACTIVE  = "inactive", "Inactive"

class Subscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscriptions")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")

    status = models.CharField(max_length=20, choices=SubscriptionStatus.choices, default=SubscriptionStatus.ACTIVE)
    start_at = models.DateTimeField(default=timezone.now)
    current_period_start = models.DateTimeField(default=timezone.now)
    current_period_end   = models.DateTimeField()
    cancel_at_period_end = models.BooleanField(default=False)

    # Stripe hook (optional)
    stripe_sub_id = models.CharField(max_length=120, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "status"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} → {self.plan} [{self.status}]"

    def is_active(self):
        return self.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING} and self.current_period_end >= timezone.now()

    def renew_period_bounds(self):
        """Compute next period start/end from interval."""
        start = self.current_period_end
        if self.plan.interval == PlanInterval.MONTH:
            end = start + timezone.timedelta(days=30)
        else:
            end = start + timezone.timedelta(days=365)
        return start, end
