from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView
)
from .views import LogoutView, OTPAuthView, OTPVerifyView, RegisterView

urlpatterns = [
    path('auth/', OTPAuthView.as_view(), name='otp_auth'),
    path('verify/', OTPVerifyView.as_view(), name='otp_verify'),
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
]
