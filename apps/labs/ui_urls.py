from django.urls import path
from . import ui_views as v

app_name = "labs_ui"

urlpatterns = [
    path("clinicians/<int:pk>/tests/order/new/",  v.order_create,  name="order_create"),
    path("clinicians/<int:pk>/tests/result/new/", v.result_create, name="result_create"),
]
