from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator

class PlanInterval(models.TextChoices):
    MONTH = "month", "Monthly"
    YEAR  = "year", "Yearly"

class HealthPlan(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)

    interval = models.CharField(max_length=10, choices=PlanInterval.choices, default=PlanInterval.MONTH)
    price_cents = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    # Health plan specifics (MVP)
    plan_code = models.CharField(max_length=40, blank=True)                # for ops/billing
    region = models.CharField(max_length=80, blank=True)                   # e.g., "UK", "EU/EEA", "Sierra Leone"
    includes_telehealth = models.BooleanField(default=True)
    visits_per_period = models.PositiveIntegerField(default=2)             # GP/derm consults per period
    deductible_cents = models.PositiveIntegerField(default=0)
    copay_cents = models.PositiveIntegerField(default=0)                   # per visit
    coinsurance_pct = models.PositiveSmallIntegerField(default=0)          # 0..100
    oop_max_cents = models.PositiveIntegerField(default=0)                 # out-of-pocket max per year

    # Optional Stripe hook
    stripe_price_id = models.CharField(max_length=120, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "price_cents"]

    def __str__(self):
        return self.name

    @property
    def price_display(self):
        return f"€{self.price_cents/100:.2f}/{self.interval}"

    @property
    def copay_display(self):
        return f"€{self.copay_cents/100:.2f}"

    @property
    def deductible_display(self):
        return f"€{self.deductible_cents/100:.2f}"

    @property
    def oop_max_display(self):
        return f"€{self.oop_max_cents/100:.2f}"

class EnrollmentStatus(models.TextChoices):
    ACTIVE    = "active", "Active"
    CANCELED  = "canceled", "Canceled"
    PAST_DUE  = "past_due", "Past due"
    LAPSED    = "lapsed", "Lapsed"
    TRIALING  = "trialing", "Trialing"

class Enrollment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="enrollments")
    plan = models.ForeignKey(HealthPlan, on_delete=models.PROTECT, related_name="enrollments")

    status = models.CharField(max_length=20, choices=EnrollmentStatus.choices, default=EnrollmentStatus.ACTIVE)
    start_at = models.DateTimeField(default=timezone.now)
    current_period_start = models.DateTimeField(default=timezone.now)
    current_period_end   = models.DateTimeField()
    cancel_at_period_end = models.BooleanField(default=False)

    # Utilization
    visits_used_in_period = models.PositiveIntegerField(default=0)

    # Stripe hook
    stripe_sub_id = models.CharField(max_length=120, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "status"])]

    def __str__(self):
        return f"{self.user} → {self.plan} [{self.status}]"

    def is_active(self):
        return self.status in {EnrollmentStatus.ACTIVE, EnrollmentStatus.TRIALING} and self.current_period_end >= timezone.now()

    def renew_bounds(self):
        start = self.current_period_end
        days = 30 if self.plan.interval == PlanInterval.MONTH else 365
        return start, start + timezone.timedelta(days=days)
