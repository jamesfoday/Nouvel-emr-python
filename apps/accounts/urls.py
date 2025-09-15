from django.urls import path
from .views import AcceptInviteView

app_name = "accounts"

urlpatterns = [
    path("invite/accept/<str:token>/", AcceptInviteView.as_view(), name="accept_invite"),
]
