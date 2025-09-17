from django.db import models


class Patient(models.Model):
    # capturing the minimum demographics for intake and search.
    given_name = models.CharField(max_length=100)
    family_name = models.CharField(max_length=100)
    date_of_birth = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=20, blank=True, default="")  # free text for now
    phone = models.CharField(max_length=50, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    external_id = models.CharField(max_length=64, blank=True, default="")  # e.g., MRN from another system

    # lightweight address bundle;  normalize later if needed
    address_line = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    region = models.CharField(max_length=100, blank=True, default="")
    postal_code = models.CharField(max_length=20, blank=True, default="")
    country = models.CharField(max_length=100, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["family_name", "given_name"]),
            models.Index(fields=["date_of_birth"]),
            models.Index(fields=["email"]),
            models.Index(fields=["phone"]),
            models.Index(fields=["external_id"]),
        ]
        ordering = ["family_name", "given_name", "id"]

    def __str__(self) -> str:
        # I prefer a compact card-like label for list screens.
        dob = self.date_of_birth.isoformat() if self.date_of_birth else "—"
        return f"{self.family_name}, {self.given_name} ({dob})"
