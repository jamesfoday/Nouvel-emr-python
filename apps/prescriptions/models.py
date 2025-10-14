from django.db import models
from django.conf import settings
from apps.patients.models import Patient

class Prescription(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("final", "Final"),
    ]

    clinician = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="prescriptions"
    )
    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="prescriptions"
    )

    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="draft")
    file = models.FileField(upload_to="prescriptions/", blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title or f"Rx #{self.pk}"
