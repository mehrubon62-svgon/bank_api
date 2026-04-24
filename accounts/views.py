import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from bank_app.models import Account

from .models import OTPCode
from .serializers import (
    OTPAuthSerializer,
    OTPVerifySerializer,
    RegisterSerializer,
)

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(
                {"detail": "Logout successful"},
                status=status.HTTP_205_RESET_CONTENT,
            )
        except Exception:
            return Response(
                {"detail": "Invalid token"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class OTPAuthView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = OTPAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone_num = serializer.validated_data["phone_num"]
        otp_code = f"{random.randint(100000, 999999)}"
        OTPCode.objects.create(
            phone_num=phone_num,
            code=otp_code,
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        # In production this code should be sent via SMS provider.
        return Response(
            {
                "message": "OTP sent successfully.",
                "phone_num": phone_num,
                "otp": otp_code,
                "expires_in_seconds": 300,
            },
            status=status.HTTP_200_OK,
        )


class OTPVerifyView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone_num = serializer.validated_data["phone_num"]
        otp_obj = serializer.validated_data["otp_obj"]

        if otp_obj.expires_at < timezone.now():
            return Response({"otp": "OTP code has expired."}, status=status.HTTP_400_BAD_REQUEST)

        user, _ = User.objects.get_or_create(
            phone_num=phone_num,
            defaults={"username": phone_num},
        )
        if not user.username:
            user.username = phone_num
        user.is_phone_verified = True
        user.save(update_fields=["username", "is_phone_verified"])

        account, created = Account.objects.get_or_create(
            user=user,
            defaults={
                "first_name": serializer.validated_data["first_name"],
                "last_name": serializer.validated_data["last_name"],
                "passport_id": serializer.validated_data["passport_id"],
                "balance": 0,
            },
        )
        if not created:
            account.first_name = serializer.validated_data["first_name"]
            account.last_name = serializer.validated_data["last_name"]
            account.passport_id = serializer.validated_data["passport_id"]
            account.save(update_fields=["first_name", "last_name", "passport_id"])

        otp_obj.is_used = True
        otp_obj.save(update_fields=["is_used"])

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "message": "OTP verified. Account is ready.",
                "account": {
                    "public_id": str(account.public_id),
                    "first_name": account.first_name,
                    "last_name": account.last_name,
                    "fname": account.first_name,
                    "lname": account.last_name,
                    "passport_id": account.passport_id,
                    "balance": str(account.balance),
                },
                "tokens": {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                },
            },
            status=status.HTTP_200_OK,
        )
