from decimal import Decimal

from rest_framework import serializers

from accounts.models import CustomUser

from .models import *


class AccountSerializer(serializers.ModelSerializer):
    fname = serializers.CharField(source="first_name")
    lname = serializers.CharField(source="last_name")

    class Meta:
        model = Account
        fields = ("public_id", "fname", "lname", "passport_id", "balance")


class AddCardSerializer(serializers.ModelSerializer):
    card_id = serializers.CharField(source="card_number")
    card_name = serializers.CharField(source="cart_name", required=False)

    class Meta:
        model = Card
        fields = ("public_id", "card_id", "balance", "cart_name", "card_name", "cvv", "created_at", "expair")
        read_only_fields = ("balance", "cvv", "created_at", "expair")


class CheckExistsSerializer(serializers.Serializer):
    phone_num = serializers.CharField(max_length=20)
    card_id = serializers.CharField(max_length=16)


class TransactionCreateSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["phone_num", "card"])
    sender = serializers.UUIDField()
    receiver = serializers.UUIDField(required=False)
    reciver = serializers.UUIDField(required=False)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate(self, attrs):
        if "receiver" not in attrs and "reciver" not in attrs:
            raise serializers.ValidationError({"receiver": "This field is required."})
        attrs["receiver"] = attrs.get("receiver") or attrs.get("reciver")
        return attrs


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = "__all__"


class TransactionInsideSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["phone_num", "card"])
    sender = serializers.CharField(max_length=20)
    receiver = serializers.CharField(max_length=20, required=False)
    reciver = serializers.CharField(max_length=20, required=False)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate(self, attrs):
        if "receiver" not in attrs and "reciver" not in attrs:
            raise serializers.ValidationError({"receiver": "This field is required."})
        attrs["receiver"] = attrs.get("receiver") or attrs.get("reciver")
        return attrs


class CreditDepositRequestSerializer(serializers.Serializer):
    card_id = serializers.CharField(max_length=16)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    percent = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal("0.01"), required=False)
    procent = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal("0.01"), required=False)

    def validate(self, attrs):
        value = attrs.get("percent", attrs.get("procent"))
        if value is None:
            raise serializers.ValidationError({"percent": "This field is required."})
        attrs["percent"] = value
        return attrs


class CreditSerializer(serializers.ModelSerializer):
    class Meta:
        model = Credit
        fields = "__all__"


class DepositSerializer(serializers.ModelSerializer):
    class Meta:
        model = Deposit
        fields = "__all__"


class HistorySerializer(serializers.Serializer):
    card = serializers.CharField(max_length=16, required=False)
    income = serializers.BooleanField(required=False)
    pays = serializers.BooleanField(required=False)
    inside = serializers.BooleanField(required=False)
    time_from = serializers.DateTimeField(required=False)
    time_to = serializers.DateTimeField(required=False)


class AccountBlackListSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountBlackList
        fields = "__all__"


class CardBlackListSerializer(serializers.ModelSerializer):
    class Meta:
        model = CardBlackList
        fields = "__all__"


class AdminUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ("id", "username", "phone_num", "is_phone_verified", "is_staff", "is_superuser")


class AIAssistantRequestSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=1500)
