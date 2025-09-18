# apps/appointments/management/commands/send_due_reminders.py
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.appointments.models import Appointment
from apps.appointments.tasks import send_appointment_email


class Command(BaseCommand):
    help = "Send due appointment reminders (24h & 2h). Use --dry-run to preview only."

    def add_arguments(self, parser):
        parser.add_argument("--window", type=int, default=5, help="Window in minutes around the target time")
        parser.add_argument("--kind", choices=["both", "24h", "2h"], default="both", help="Which reminders to send")
        parser.add_argument("--dry-run", action="store_true", help="Preview only; do not send emails")

    def handle(self, *args, **opts):
        now = timezone.now()
        window_minutes = opts["window"]
        kinds = ["24h", "2h"] if opts["kind"] == "both" else [opts["kind"]]

        total = 0
        for k in kinds:
            hours_ahead = 24 if k == "24h" else 2
            sent_field = "reminder_24h_sent_at" if k == "24h" else "reminder_2h_sent_at"

            target = now + timedelta(hours=hours_ahead)
            window_start = target - timedelta(minutes=window_minutes)
            window_end = target + timedelta(minutes=window_minutes)

            qs = (
                Appointment.objects.select_related("patient", "clinician")
                .filter(
                    status__in=["scheduled", "confirmed"],
                    start__gte=window_start,
                    start__lt=window_end,
                )
                .filter(**{f"{sent_field}__isnull": True})
                .order_by("start")
            )

            count = 0
            for appt in qs:
                if not getattr(appt.patient, "email", ""):
                    # no recipient; skip quietly
                    continue

                if opts["dry_run"]:
                    self.stdout.write(
                        f"[DRY RUN] would send {k} reminder for appt #{appt.id} @ {appt.start.isoformat()}"
                    )
                    count += 1
                    continue

                # Send the email (in dev, Celery runs inline because ALWAYS_EAGER=True)
                send_appointment_email.delay(appt.id, kind="reminder")

                # Mark as sent to avoid duplicates
                setattr(appt, sent_field, now)
                appt.save(update_fields=[sent_field])

                self.stdout.write(self.style.SUCCESS(f"sent {k} reminder for appt #{appt.id}"))
                count += 1

            self.stdout.write(self.style.SUCCESS(f"{k}: {count} reminder(s)"))
            total += count

        self.stdout.write(self.style.SUCCESS(f"Done. Total: {total}"))
