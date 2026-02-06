from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
class User(AbstractUser):
    ROLE_CHOICES = (
        ("ADMIN", "Admin"),
        ("CHURCH", "Church"),
        ("USER", "User"),  # for future family head login
    )

    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default="USER"
    )

    church = models.OneToOneField(
        "registry.Church",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    member = models.OneToOneField(
        "registry.Member",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user"
    )

    def __str__(self):
        return f"{self.username} ({self.role})"


class PasswordResetOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    otp_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    def is_expired(self):
        return timezone.now() > self.created_at + timezone.timedelta(minutes=10)