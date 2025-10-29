# apps/subscriptions/urls.py
from django.urls import path
from . import views

app_name = "subscriptions"

urlpatterns = [
    path("plans/", views.plan_list, name="plans"),
    path("plans/create/", views.plan_create, name="plan_create"), 
    path("plans/<slug:slug>/", views.plan_detail, name="plan_detail"),
    path("subscribe/", views.subscribe, name="subscribe"),
    path("cancel/", views.cancel, name="cancel"),
    path("resume/", views.resume, name="resume"),
]
