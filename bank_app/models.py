import random
import uuid
from datetime import timedelta

from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone


class Account(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    user = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    first_name = models.CharField(max_length=30)
    last_name = models.CharField(max_length=30)
    passport_id = models.CharField(max_length=20, unique=True)

    def __str__(self):
        return f"{self.user} account"


class Card(models.Model):
    CARD_TYPES = (
        ("visa", "Visa"),
        ("credit", "Credit"),
        ("master", "Master"),
        ("simple", "Simple"),
    )

    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="cards")
    card_number = models.CharField(
        max_length=16,
        unique=True,
        validators=[RegexValidator(r"^\d{16}$", "Card number must contain exactly 16 digits.")],
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cart_name = models.CharField(max_length=10, choices=CARD_TYPES, default="simple")
    cvv = models.CharField(max_length=3, editable=False, default="000")
    created_at = models.DateTimeField(default=timezone.now)
    expair = models.DateField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.cvv:
            self.cvv = f"{random.randint(100, 999)}"
        if not self.expair:
            self.expair = (timezone.now() + timedelta(days=365 * 5)).date()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.card_number}"


class Transaction(models.Model):
    TRANSFER_TYPES = (("phone_num", "Phone Number"), ("card", "Card"))
    STATUSES = (("success", "Success"), ("failed", "Failed"), ("pending", "Pending"))

    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    type = models.CharField(max_length=20, choices=TRANSFER_TYPES)
    sender = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="sent_transactions", null=True, blank=True
    )
    reciver = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="received_transactions", null=True, blank=True
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)])
    created_at = models.DateTimeField(auto_now_add=True)
    cuur_balance_sender = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cuur_balance_reciver = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    description = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default="success")

    def __str__(self):
        return f"{self.sender_id}->{self.reciver_id}: {self.amount}"


class TransactionInside(models.Model):
    TRANSFER_TYPES = (("phone_num", "Phone Number"), ("card", "Card"))
    STATUSES = (("success", "Success"), ("failed", "Failed"), ("pending", "Pending"))

    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    type = models.CharField(max_length=20, choices=TRANSFER_TYPES)
    sender = models.CharField(max_length=20)
    reciver = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)])
    created_at = models.DateTimeField(auto_now_add=True)
    cuur_balance_sender = models.DecimalField(max_digits=12, decimal_places=2)
    cuur_balance_reciver = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default="success")

    def __str__(self):
        return f"Inside {self.type}: {self.sender}->{self.reciver}"


class Credit(models.Model):
    STATUSES = (("active", "Active"), ("closed", "Closed"), ("failed", "Failed"))

    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    card_id = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="credits")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)])
    percent = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0.01)])
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUSES, default="active")

    def __str__(self):
        return f"Credit {self.amount}"


class Deposit(models.Model):
    STATUSES = (("active", "Active"), ("closed", "Closed"), ("failed", "Failed"))

    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    card_id = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="deposits")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)])
    percent = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0.01)])
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUSES, default="active")

    def __str__(self):
        return f"Deposit {self.amount}"


class AccountBlackList(models.Model):
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="blacklist_entries")
    created_at = models.DateTimeField(auto_now_add=True)
    description = models.CharField(max_length=255)

    def __str__(self):
        return f"BlackList account {self.account_id}"


class CardBlackList(models.Model):
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="blacklist_entries")
    created_at = models.DateTimeField(auto_now_add=True)
    description = models.CharField(max_length=255)

    def __str__(self):
        return f"BlackList card {self.card_id}"


class FamilyGroup(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    owner = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE, related_name="owned_family_groups")
    name = models.CharField(max_length=80, default="My Family")
    cashback_bonus_percent = models.DecimalField(max_digits=4, decimal_places=2, default=0.50)
    transfer_fee_discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=25.00)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"FamilyGroup {self.name} ({self.owner_id})"


class FamilyMember(models.Model):
    group = models.ForeignKey(FamilyGroup, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE, related_name="family_memberships")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("group", "user")

    def __str__(self):
        return f"FamilyMember group={self.group_id} user={self.user_id}"
