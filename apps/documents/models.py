from django.conf import settings
from django.db import models
from apps.patients.models import Patient
import mimetypes

class Document(models.Model):
    class Kind(models.TextChoices):
        GENERIC = "generic", "Document"
        PRESCRIPTION = "prescription", "Prescription"
        LAB_RESULT = "lab_result", "Lab result"
        IMAGE = "image", "Image"

    clinician = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="documents"
    )
    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="documents"
    )

    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.GENERIC)

    file = models.FileField(upload_to="documents/%Y/%m/%d")
    content_type = models.CharField(max_length=100, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)

    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["clinician", "created_at"]),
            models.Index(fields=["patient", "created_at"]),
        ]

    def __str__(self):
        return self.title or f"Doc #{self.pk}"

    @property
    def is_image(self) -> bool:
        ct = (self.content_type or "").lower()
        return ct.startswith("image/")

    def save(self, *args, **kwargs):
        # Fill content_type / size if the file is present
        if self.file:
            self.size_bytes = getattr(self.file, "size", 0) or 0
            guessed, _ = mimetypes.guess_type(self.file.name or "")
            if guessed and not self.content_type:
                self.content_type = guessed
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Remove the blob from storage when the record is deleted
        storage = self.file.storage if self.file else None
        name = self.file.name if self.file else None
        super().delete(*args, **kwargs)
        if storage and name:
            try:
                storage.delete(name)
            except Exception:
                pass
