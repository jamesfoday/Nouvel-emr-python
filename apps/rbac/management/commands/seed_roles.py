from django.core.management.base import BaseCommand
from apps.rbac.models import Role

DEFAULT_ROLES = {
    "admin": "Full administrative access",
    "clinician": "Clinical access to encounters, orders, results",
    "staff": "Front desk: intake and scheduling",
}

class Command(BaseCommand):
    help = "Seed default roles for Nouvel"

    def handle(self, *args, **options):
        for name, desc in DEFAULT_ROLES.items():
            obj, created = Role.objects.get_or_create(name=name, defaults={"description": desc})
            self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Exists'}: {obj.name}"))
