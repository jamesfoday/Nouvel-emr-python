from django.db import models
from django.utils import timezone


class Inquiry(models.Model):
    STATUS_CHOICES = [
        ("new", "New"),
        ("in_progress", "In progress"),
        ("closed", "Closed"),
    ]

    name = models.CharField(max_length=120)
    email = models.EmailField()
    message = models.TextField()

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new")
    staff_note = models.TextField(blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Inquiry from {self.name} <{self.email}>"
