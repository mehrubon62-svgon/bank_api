from django.db import transaction as db_transaction
from django.db.models import Q
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import CustomUser

from .models import *
from .serializers import *


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
