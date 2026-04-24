from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from bank_app.models import Account

from .models import OTPCode

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("username", "password")
        extra_kwargs = {"password": {"write_only": True}}

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data["username"],
            password=validated_data["password"],
        )


class OTPAuthSerializer(serializers.Serializer):
    phone_num = serializers.CharField(max_length=20)


class OTPVerifySerializer(serializers.Serializer):
    phone_num = serializers.CharField(max_length=20)
    otp = serializers.CharField(max_length=6)
    first_name = serializers.CharField(max_length=30, required=False)
    last_name = serializers.CharField(max_length=30, required=False)
    fname = serializers.CharField(max_length=30, required=False)
    lname = serializers.CharField(max_length=30, required=False)
    passport_id = serializers.CharField(max_length=20)

    def validate(self, attrs):
        otp_obj = OTPCode.objects.filter(
            phone_num=attrs["phone_num"],
            code=attrs["otp"],
            is_used=False,
        ).first()
        if not otp_obj:
            raise serializers.ValidationError({"otp": "Invalid OTP code."})
        if otp_obj.expires_at <= timezone.now():
            raise serializers.ValidationError({"otp": "OTP code is invalid."})
        attrs["first_name"] = attrs.get("first_name") or attrs.get("fname")
        attrs["last_name"] = attrs.get("last_name") or attrs.get("lname")
        if not attrs["first_name"] or not attrs["last_name"]:
            raise serializers.ValidationError(
                {"first_name": "first_name/last_name (or fname/lname) are required."}
            )
        attrs["otp_obj"] = otp_obj
        return attrs


class AccountAfterVerifySerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = (
            "public_id",
            "first_name",
            "last_name",
            "passport_id",
            "balance",
        )
