from django.urls import path

from .views import *

urlpatterns = [
    path("add_card/", AddCardView.as_view(), name="add_card"),
    path("check_if_account_exists/", CheckIfAccountExistsView.as_view(), name="check_if_account_exists"),
    path("check_if_account_exsits/", CheckIfAccountExistsView.as_view(), name="check_if_account_exsits"),
    path("transaction/", TransactionView.as_view(), name="transaction"),
    path("transaction_inside/", TransactionInsideView.as_view(), name="transaction_inside"),
    path("get_credit/", GetCreditView.as_view(), name="get_credit"),
    path("get_creadit/", GetCreditView.as_view(), name="get_creadit"),
    path("put_deposit/", PutDepositView.as_view(), name="put_deposit"),
    path("history/", HistoryView.as_view(), name="history"),
    path("black_list/account/", AccountBlackListView.as_view(), name="black_list_account"),
    path("black_list/card/", CardBlackListView.as_view(), name="black_list_card"),
    path("admin/", AdminDashboardView.as_view(), name="admin_dashboard"),
    path("ai/", FinanceAssistantView.as_view(), name="finance_ai_assistant"),
]
