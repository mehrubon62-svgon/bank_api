import json
from datetime import timedelta
from decimal import Decimal
from urllib import error, request as urllib_request

from django.conf import settings
from django.db import transaction as db_transaction
from django.db.models import Q
from django.utils import timezone
from drf_yasg.utils import swagger_auto_schema
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from accounts.models import CustomUser
from .models import *
from .serializers import *


FINANCE_ASSISTANT_SYSTEM_PROMPT = """
You are a highly practical finance and banking assistant for a bank API product.

Primary mission:
1) Give useful, concrete, and actionable answers for finance/banking questions.
2) Do not produce lazy fallback replies like "please clarify" unless absolutely required.
3) If the question is broad, make reasonable assumptions and still provide value.

Domain scope (allowed):
- Personal finance: budgeting, debt payoff, savings strategy, emergency funds.
- Banking: cards, accounts, transfers, payment flows, fees, exchange basics.
- Lending: credit score basics, loans, APR/effective rate, repayment strategy.
- Deposits and interest: simple/compound interest, term deposits, scenarios.
- Business basics: cash flow, treasury basics, payment operations.
- Risk and fraud prevention in banking operations.

Out of scope:
- Programming unrelated to finance.
- Medicine, law outside finance context, general trivia, entertainment, politics.
If out of scope, politely refuse in 1-2 short sentences and offer 2-3 examples of valid finance questions.

Answer quality requirements:
- Always answer in the user's language. If mixed, default to Russian.
- Be specific and practical. Avoid vague generic text.
- Use short structure when useful:
  - "Короткий ответ"
  - "Почему"
  - "Что делать (шаги)"
  - "Пример расчета" (if numbers are relevant)
- If user gives numbers, calculate and show formulas clearly.
- If user gives no numbers but asks optimization question, provide a default scenario with sample numbers.
- Mention uncertainty briefly when assumptions are used.

Safety and compliance style:
- Do not claim guaranteed profits.
- Do not promote fraud, illegal bypasses, or money laundering.
- For high-risk decisions, add a short caution note.

Behavior constraints:
- Never return an empty answer.
- Never reply only with "уточните вопрос" if you can provide even partial help.
- Prefer direct recommendations and checklists.
- Keep tone professional, clear, and concise, but informative.
""".strip()


def _openrouter_chat(question, model_name):
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {
        "model": model_name,
        "max_tokens": settings.OPENROUTER_MAX_TOKENS,
        "messages": [
            {
                "role": "system",
                "content": FINANCE_ASSISTANT_SYSTEM_PROMPT,
            },
            {"role": "user", "content": question},
        ],
    }

    req = urllib_request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "bank-api-assistant",
        },
        method="POST",
    )

    with urllib_request.urlopen(req, timeout=35) as response:
        raw_data = response.read().decode("utf-8")

    data = json.loads(raw_data)
    choices = data.get("choices") or []
    if not choices:
        raise ValidationError({"detail": "OpenRouter returned empty response."})
    return choices[0].get("message", {}).get("content", "")


class AddCardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = AddCardSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = Account.objects.filter(user=request.user).first()
        if not account:
            raise ValidationError({"account": "Account not found for current user."})

        card = Card.objects.create(
            account=account,
            card_number=serializer.validated_data["card_number"],
            cart_name=serializer.validated_data["cart_name"],
            balance=0,
        )
        return Response(AddCardSerializer(card).data, status=status.HTTP_201_CREATED)


class CheckIfAccountExistsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CheckExistsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        account_exists = Account.objects.filter(user__phone_num=serializer.validated_data["phone_num"]).exists()
        card_exists = Card.objects.filter(card_number=serializer.validated_data["card_id"]).exists()

        return Response(
            {
                "account_exists": account_exists,
                "card_exists": card_exists,
            }
        )


class TransactionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = TransactionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        sender = Account.objects.filter(public_id=serializer.validated_data["sender"]).first()
        receiver = Account.objects.filter(public_id=serializer.validated_data["receiver"]).first()

        if not sender or not receiver:
            raise ValidationError({"detail": "Sender or receiver account not found."})
        if sender.user_id != request.user.id:
            raise ValidationError({"sender": "Sender must belong to current user."})
        if sender == receiver:
            raise ValidationError({"receiver": "Sender and receiver must be different."})

        amount = serializer.validated_data["amount"]
        if sender.balance < amount:
            raise ValidationError({"amount": "Insufficient sender balance."})

        with db_transaction.atomic():
            sender.balance -= amount
            receiver.balance += amount
            sender.save(update_fields=["balance"])
            receiver.save(update_fields=["balance"])

            tx = Transaction.objects.create(
                type=serializer.validated_data["type"],
                sender=sender,
                reciver=receiver,
                amount=amount,
                cuur_balance_sender=sender.balance,
                cuur_balance_reciver=receiver.balance,
                description=serializer.validated_data.get("description", ""),
                status="success",
            )

        return Response(TransactionSerializer(tx).data, status=status.HTTP_201_CREATED)


class TransactionInsideView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = TransactionInsideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        transfer_type = serializer.validated_data["type"]
        sender_value = serializer.validated_data["sender"]
        receiver_value = serializer.validated_data["receiver"]
        amount = serializer.validated_data["amount"]

        if transfer_type == "phone_num":
            sender_account = Account.objects.filter(user__phone_num=sender_value).first()
            receiver_account = Account.objects.filter(user__phone_num=receiver_value).first()
        else:
            sender_card = Card.objects.filter(card_number=sender_value).select_related("account").first()
            receiver_card = Card.objects.filter(card_number=receiver_value).select_related("account").first()
            sender_account = sender_card.account if sender_card else None
            receiver_account = receiver_card.account if receiver_card else None

        if not sender_account or not receiver_account:
            raise ValidationError({"detail": "Sender or receiver not found."})
        if sender_account.user_id != request.user.id:
            raise ValidationError({"sender": "Sender must belong to current user."})
        if sender_account.balance < amount:
            raise ValidationError({"amount": "Insufficient sender balance."})

        with db_transaction.atomic():
            sender_account.balance -= amount
            receiver_account.balance += amount
            sender_account.save(update_fields=["balance"])
            receiver_account.save(update_fields=["balance"])

            tx = TransactionInside.objects.create(
                type=transfer_type,
                sender=sender_value,
                reciver=receiver_value,
                amount=amount,
                cuur_balance_sender=sender_account.balance,
                cuur_balance_reciver=receiver_account.balance,
                description=serializer.validated_data.get("description", ""),
                status="success",
            )

        return Response(
            {
                "transaction_inside": {
                    "public_id": str(tx.public_id),
                    "type": tx.type,
                    "sender": tx.sender,
                    "receiver": tx.reciver,
                    "reciver": tx.reciver,
                    "amount": str(tx.amount),
                    "cuur_balance_sender": str(tx.cuur_balance_sender),
                    "cuur_balance_reciver": str(tx.cuur_balance_reciver),
                    "description": tx.description,
                    "status": tx.status,
                    "created_at": tx.created_at,
                }
            },
            status=status.HTTP_201_CREATED,
        )


class GetCreditView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CreditDepositRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        card = Card.objects.filter(card_number=serializer.validated_data["card_id"], account__user=request.user).first()
        if not card:
            raise ValidationError({"card_id": "Card not found for current user."})
        if card.cart_name != "credit":
            raise ValidationError({"card_id": "Credit is available only for card type 'credit'."})

        with db_transaction.atomic():
            credit = Credit.objects.create(
                card_id=card,
                amount=serializer.validated_data["amount"],
                percent=serializer.validated_data["percent"],
                status="active",
            )
            card.balance += serializer.validated_data["amount"]
            card.save(update_fields=["balance"])

        return Response(CreditSerializer(credit).data, status=status.HTTP_201_CREATED)


class PutDepositView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CreditDepositRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        card = Card.objects.filter(card_number=serializer.validated_data["card_id"], account__user=request.user).first()
        if not card:
            raise ValidationError({"card_id": "Card not found for current user."})
        if card.balance < serializer.validated_data["amount"]:
            raise ValidationError({"amount": "Insufficient balance for deposit."})

        with db_transaction.atomic():
            card.balance -= serializer.validated_data["amount"]
            card.save(update_fields=["balance"])
            deposit = Deposit.objects.create(
                card_id=card,
                amount=serializer.validated_data["amount"],
                percent=serializer.validated_data["percent"],
                status="active",
            )

        return Response(DepositSerializer(deposit).data, status=status.HTTP_201_CREATED)


class HistoryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = HistorySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        filters = serializer.validated_data
        transactions = Transaction.objects.filter(
            Q(sender__user=request.user) | Q(reciver__user=request.user)
        ).order_by("-created_at")
        inside_qs = TransactionInside.objects.filter(
            Q(sender=request.user.phone_num) | Q(reciver=request.user.phone_num)
        ).order_by("-created_at")

        card_number = filters.get("card")
        if card_number:
            account_ids = list(Card.objects.filter(card_number=card_number).values_list("account_id", flat=True))
            transactions = transactions.filter(Q(sender_id__in=account_ids) | Q(reciver_id__in=account_ids))

        if filters.get("income") and not filters.get("pays"):
            transactions = transactions.filter(reciver__user=request.user)
        if filters.get("pays") and not filters.get("income"):
            transactions = transactions.filter(sender__user=request.user)

        time_from = filters.get("time_from")
        time_to = filters.get("time_to")
        if time_from:
            transactions = transactions.filter(created_at__gte=time_from)
            inside_qs = inside_qs.filter(created_at__gte=time_from)
        if time_to:
            transactions = transactions.filter(created_at__lte=time_to)
            inside_qs = inside_qs.filter(created_at__lte=time_to)

        return Response(
            {
                "transaction_history": TransactionSerializer(transactions, many=True).data,
                "inside_history": [
                    {
                        "public_id": str(obj.public_id),
                        "type": obj.type,
                        "sender": obj.sender,
                        "receiver": obj.reciver,
                        "reciver": obj.reciver,
                        "amount": str(obj.amount),
                        "created_at": obj.created_at,
                        "status": obj.status,
                    }
                    for obj in inside_qs
                ]
                if filters.get("inside", False)
                else [],
            }
        )


class AccountBlackListView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        serializer = AccountBlackListSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(AccountBlackListSerializer(instance).data, status=status.HTTP_201_CREATED)


class CardBlackListView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        serializer = CardBlackListSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(CardBlackListSerializer(instance).data, status=status.HTTP_201_CREATED)


class AdminDashboardView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        return Response(
            {
                "users": AdminUserSerializer(CustomUser.objects.all(), many=True).data,
                "accounts": [
                    {
                        "public_id": str(a.public_id),
                        "user": a.user.phone_num or a.user.username,
                        "fname": a.first_name,
                        "lname": a.last_name,
                        "passport_id": a.passport_id,
                        "balance": str(a.balance),
                    }
                    for a in Account.objects.select_related("user").all()
                ],
                "cards": AddCardSerializer(Card.objects.select_related("account").all(), many=True).data,
                "transactions": TransactionSerializer(Transaction.objects.all(), many=True).data,
                "transactions_inside": [
                    {
                        "public_id": str(t.public_id),
                        "type": t.type,
                        "sender": t.sender,
                        "receiver": t.reciver,
                        "reciver": t.reciver,
                        "amount": str(t.amount),
                        "status": t.status,
                        "created_at": t.created_at,
                    }
                    for t in TransactionInside.objects.all()
                ],
                "credits": CreditSerializer(Credit.objects.all(), many=True).data,
                "deposits": DepositSerializer(Deposit.objects.all(), many=True).data,
                "account_blacklist": AccountBlackListSerializer(AccountBlackList.objects.all(), many=True).data,
                "card_blacklist": CardBlackListSerializer(CardBlackList.objects.all(), many=True).data,
            }
        )


class FinanceAssistantView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(request_body=AIAssistantRequestSerializer)
    def post(self, request):
        serializer = AIAssistantRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question = serializer.validated_data["text"].strip()
        model_name = settings.OPENROUTER_MODEL

        if not settings.OPENROUTER_API_KEY:
            return Response({"detail": "OPENROUTER_API_KEY is not set."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            answer = _openrouter_chat(question, model_name)
        except error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="ignore")
            return Response(
                {"detail": "OpenRouter request failed.", "status_code": exc.code, "error": error_body},
                status=exc.code,
            )
        except error.URLError as exc:
            return Response(
                {"detail": "Unable to reach OpenRouter.", "error": str(exc.reason)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response({"answer": answer})


class CurrencyConvertView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(request_body=CurrencyConvertSerializer)
    def post(self, request):
        serializer = CurrencyConvertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        amount = serializer.validated_data["amount"]
        from_currency = serializer.validated_data["from_currency"]
        to_currency = serializer.validated_data["to_currency"]

        if from_currency == to_currency:
            return Response(
                {
                    "amount": str(amount),
                    "from_currency": from_currency,
                    "to_currency": to_currency,
                    "rate": "1",
                    "converted_amount": str(amount),
                    "source": "same-currency",
                }
            )

        url = f"{settings.EXCHANGE_RATE_API_URL}/{from_currency}"
        req = urllib_request.Request(url, method="GET")
        try:
            with urllib_request.urlopen(req, timeout=20) as response:
                raw_data = response.read().decode("utf-8")
        except error.HTTPError as exc:
            return Response(
                {"detail": "Exchange rate API failed.", "status_code": exc.code},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except error.URLError as exc:
            return Response(
                {"detail": "Cannot reach exchange rate API.", "error": str(exc.reason)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        data = json.loads(raw_data)
        rates = data.get("rates") or {}
        rate_value = rates.get(to_currency)
        if rate_value is None:
            raise ValidationError({"to_currency": f"Currency '{to_currency}' is not available."})

        rate = Decimal(str(rate_value))
        converted = (amount * rate).quantize(Decimal("0.01"))
        return Response(
            {
                "amount": str(amount),
                "from_currency": from_currency,
                "to_currency": to_currency,
                "rate": str(rate),
                "converted_amount": str(converted),
                "source": settings.EXCHANGE_RATE_API_URL,
            }
        )


class MastercardCashbackView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(request_body=MastercardCashbackSerializer)
    def post(self, request):
        serializer = MastercardCashbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        days = serializer.validated_data["days"]
        date_from = timezone.now() - timedelta(days=days)
        card_id = serializer.validated_data.get("card_id")

        master_cards = Card.objects.filter(account__user=request.user, cart_name="master")
        if card_id:
            master_cards = master_cards.filter(card_number=card_id)
        if not master_cards.exists():
            raise ValidationError({"card_id": "Mastercard not found for current user."})

        account_ids = list(master_cards.values_list("account_id", flat=True))
        tx_qs = Transaction.objects.filter(sender_id__in=account_ids, created_at__gte=date_from)
        inside_qs = TransactionInside.objects.filter(sender=request.user.phone_num, created_at__gte=date_from)

        total_spent = Decimal("0.00")
        for tx in tx_qs:
            total_spent += tx.amount
        for tx in inside_qs:
            total_spent += tx.amount

        base_rate = Decimal("0.01")
        cashback_amount = (total_spent * base_rate).quantize(Decimal("0.01"))

        family_group = FamilyGroup.objects.filter(owner=request.user).first()
        family_bonus_percent = family_group.cashback_bonus_percent if family_group else Decimal("0.00")
        family_bonus_amount = (total_spent * (family_bonus_percent / Decimal("100"))).quantize(Decimal("0.01"))

        return Response(
            {
                "period_days": days,
                "mastercard_count": master_cards.count(),
                "total_spent": str(total_spent),
                "base_cashback_rate_percent": "1.00",
                "base_cashback_amount": str(cashback_amount),
                "family_bonus_rate_percent": str(family_bonus_percent),
                "family_bonus_amount": str(family_bonus_amount),
                "total_cashback_amount": str((cashback_amount + family_bonus_amount).quantize(Decimal("0.01"))),
            }
        )


class FamilyGroupView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(request_body=FamilyGroupCreateSerializer)
    def post(self, request):
        serializer = FamilyGroupCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        group, _ = FamilyGroup.objects.get_or_create(
            owner=request.user,
            defaults={"name": serializer.validated_data.get("name") or "My Family"},
        )
        if serializer.validated_data.get("name"):
            group.name = serializer.validated_data["name"]
            group.save(update_fields=["name"])

        return Response(
            {
                "public_id": str(group.public_id),
                "name": group.name,
                "cashback_bonus_percent": str(group.cashback_bonus_percent),
                "transfer_fee_discount_percent": str(group.transfer_fee_discount_percent),
            },
            status=status.HTTP_201_CREATED,
        )

    def get(self, request):
        group = FamilyGroup.objects.filter(owner=request.user).first()
        if not group:
            raise ValidationError({"detail": "Family group is not created yet."})

        members = [
            {
                "id": obj.user.id,
                "phone_num": obj.user.phone_num,
                "username": obj.user.username,
                "added_at": obj.added_at,
            }
            for obj in group.members.select_related("user").all().order_by("-added_at")
        ]
        return Response(
            {
                "public_id": str(group.public_id),
                "name": group.name,
                "owner_phone": request.user.phone_num,
                "cashback_bonus_percent": str(group.cashback_bonus_percent),
                "transfer_fee_discount_percent": str(group.transfer_fee_discount_percent),
                "members_count": len(members),
                "members": members,
            }
        )


class FamilyMemberAddView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(request_body=FamilyMemberAddSerializer)
    def post(self, request):
        serializer = FamilyMemberAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        group = FamilyGroup.objects.filter(owner=request.user).first()
        if not group:
            raise ValidationError({"detail": "Create family group first."})

        member_user = CustomUser.objects.filter(phone_num=serializer.validated_data["phone_num"]).first()
        if not member_user:
            raise ValidationError({"phone_num": "User with this phone number was not found."})
        if member_user.id == request.user.id:
            raise ValidationError({"phone_num": "Owner is already part of the family group."})

        member, created = FamilyMember.objects.get_or_create(group=group, user=member_user)
        http_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(
            {
                "group_public_id": str(group.public_id),
                "member": {
                    "id": member.user.id,
                    "phone_num": member.user.phone_num,
                    "username": member.user.username,
                },
                "created": created,
                "perks": {
                    "cashback_bonus_percent": str(group.cashback_bonus_percent),
                    "transfer_fee_discount_percent": str(group.transfer_fee_discount_percent),
                },
            },
            status=http_status,
        )


class StatementSixMonthsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = StatementSixMonthsSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        include_inside = serializer.validated_data["include_inside"]
        now = timezone.now()
        date_from = now - timedelta(days=183)

        tx_qs = Transaction.objects.filter(
            Q(sender__user=request.user) | Q(reciver__user=request.user),
            created_at__gte=date_from,
        ).order_by("-created_at")
        inside_qs = TransactionInside.objects.filter(
            Q(sender=request.user.phone_num) | Q(reciver=request.user.phone_num),
            created_at__gte=date_from,
        ).order_by("-created_at")

        monthly = {}
        total_income = Decimal("0.00")
        total_expense = Decimal("0.00")

        def ensure_bucket(dt):
            key = dt.strftime("%Y-%m")
            if key not in monthly:
                monthly[key] = {"month": key, "income": Decimal("0.00"), "expense": Decimal("0.00")}
            return monthly[key]

        for tx in tx_qs:
            bucket = ensure_bucket(tx.created_at)
            if tx.sender and tx.sender.user_id == request.user.id:
                bucket["expense"] += tx.amount
                total_expense += tx.amount
            if tx.reciver and tx.reciver.user_id == request.user.id:
                bucket["income"] += tx.amount
                total_income += tx.amount

        inside_items = []
        if include_inside:
            for tx in inside_qs:
                bucket = ensure_bucket(tx.created_at)
                if tx.sender == request.user.phone_num:
                    bucket["expense"] += tx.amount
                    total_expense += tx.amount
                if tx.reciver == request.user.phone_num:
                    bucket["income"] += tx.amount
                    total_income += tx.amount
                inside_items.append(
                    {
                        "public_id": str(tx.public_id),
                        "type": tx.type,
                        "sender": tx.sender,
                        "receiver": tx.reciver,
                        "amount": str(tx.amount),
                        "status": tx.status,
                        "created_at": tx.created_at,
                    }
                )

        monthly_list = []
        for key in sorted(monthly.keys()):
            row = monthly[key]
            monthly_list.append(
                {
                    "month": row["month"],
                    "income": str(row["income"].quantize(Decimal("0.01"))),
                    "expense": str(row["expense"].quantize(Decimal("0.01"))),
                    "net": str((row["income"] - row["expense"]).quantize(Decimal("0.01"))),
                }
            )

        return Response(
            {
                "period": {
                    "from": date_from,
                    "to": now,
                },
                "totals": {
                    "income": str(total_income.quantize(Decimal("0.01"))),
                    "expense": str(total_expense.quantize(Decimal("0.01"))),
                    "net": str((total_income - total_expense).quantize(Decimal("0.01"))),
                },
                "monthly": monthly_list,
                "transaction_history": TransactionSerializer(tx_qs, many=True).data,
                "inside_history": inside_items,
            }
        )
