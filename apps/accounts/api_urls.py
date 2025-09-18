from django.urls import path
from .api import WhoAmIView

app_name = "accounts_api"

urlpatterns = [
    path("accounts/whoami/", WhoAmIView.as_view(), name="whoami"),
]
