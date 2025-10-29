from django.db.models.signals import post_migrate
from django.dispatch import receiver
from .models import Plan, PlanInterval

@receiver(post_migrate)
def seed_default_plans(sender, **kwargs):
    # Only seed when THIS app's migrations run
    if sender.name != "apps.subscriptions":
        return

    Plan.objects.get_or_create(
        slug="basic",
        defaults=dict(
            name="Basic",
            description="Starter plan",
            price_cents=990,
            interval=PlanInterval.MONTH,
            sort_order=1,
            max_patients=200,
            max_staff=5,
            storage_mb=1024,
            is_active=True,
        ),
    )
