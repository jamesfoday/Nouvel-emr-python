from django.urls import path
from . import views

app_name = "inquiry"

urlpatterns = [
    path("", views.inquiry_create, name="create"),
    path("thanks/", views.inquiry_thanks, name="thanks"),
    path("admin/", views.inquiry_list, name="list"),
    path("admin/<int:pk>/", views.inquiry_detail, name="detail"),
]
