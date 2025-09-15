from django.urls import path
from .api import WhoAmIView

app_name = "accounts_api"

urlpatterns = [
    path("whoami/", WhoAmIView.as_view(), name="whoami"),
]
