from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CustomUser, OTPCode


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    pass


@admin.register(OTPCode)
class OTPCodeAdmin(admin.ModelAdmin):
    list_display = ("id", "phone_num", "code", "is_used", "created_at", "expires_at")
    search_fields = ("phone_num",)
