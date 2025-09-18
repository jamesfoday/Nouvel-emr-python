import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

@pytest.mark.django_db
def test_jwt_login_and_whoami():
    # create a user we can log in with
    U = get_user_model()
    user = U.objects.create_user(username="apiuser", password="pass12345!", is_staff=True)

    client = APIClient()

    # 1) obtain token
    token_url = reverse("token_obtain_pair")  # added in config/urls.py
    res = client.post(token_url, {"username": "apiuser", "password": "pass12345!"}, format="json")
    assert res.status_code == 200, res.content
    access = res.json()["access"]

    # 2) use Bearer token to hit a protected endpoint
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    whoami_url = reverse("accounts_api:whoami")  #  WhoAmIView
    r2 = client.get(whoami_url)
    assert r2.status_code == 200, r2.content
    body = r2.json()
    assert body["username"] == "apiuser"
