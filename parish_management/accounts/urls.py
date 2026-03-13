from django.urls import  path
from .views import ChangePasswordAPIView, CheckEmailAPIView, LoginAPIView, ChurchProfileAPIView, LogoutAPIView, reset_password
from rest_framework_simplejwt.views import TokenRefreshView
from accounts.views import forgot_password

urlpatterns = [
    path("auth/check-email/", CheckEmailAPIView.as_view(), name="check-email"),
    path("login/", LoginAPIView.as_view()),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("logout/", LogoutAPIView.as_view()),
    path("change-password/", ChangePasswordAPIView.as_view()),
    path("church/profile/", ChurchProfileAPIView.as_view()),
    path("auth/forgot-password/",forgot_password,name='forgot-password'),
    path("auth/reset-password/", reset_password,name='reset-password'),



]
