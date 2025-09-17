# apps/accounts/api_urls.py
from django.urls import path
from .api import CsrfView, LoginView, LogoutView, WhoAmIView

app_name = "auth_api"

urlpatterns = [
    path("csrf/", CsrfView.as_view(), name="csrf"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("whoami/", WhoAmIView.as_view(), name="whoami"),
]
