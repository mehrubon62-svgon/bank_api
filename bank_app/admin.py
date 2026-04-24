from django.contrib import admin

from .models import *

admin.site.register(Account)
admin.site.register(Card)
admin.site.register(Transaction)
admin.site.register(TransactionInside)
admin.site.register(Credit)
admin.site.register(Deposit)
admin.site.register(AccountBlackList)
admin.site.register(CardBlackList)
