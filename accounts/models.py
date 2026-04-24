from django.db import models
from django.contrib.auth.models import AbstractUser


class CustomUser(AbstractUser):
    phone_num = models.CharField(max_length=20, unique=True, null=True, blank=True)
    is_phone_verified = models.BooleanField(default=False)

    def __str__(self):
        return self.phone_num or self.username


class OTPCode(models.Model):
    phone_num = models.CharField(max_length=20, db_index=True)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"OTP for {self.phone_num}"
