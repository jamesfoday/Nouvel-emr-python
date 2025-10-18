from django.urls import path
from . import ui_views as v
from . import ui_views as views 

app_name = "labs_ui"

urlpatterns = [
    path("clinicians/<int:pk>/tests/order/new/",  v.order_create,  name="order_create"),
    path("clinicians/<int:pk>/tests/result/new/", v.result_create, name="result_create"),
    path("<int:pk>/lab/", views.lab_index, name="lab_index"),
    path("<int:pk>/lab/order/new/", views.order_create, name="order_create"),
    path("<int:pk>/lab/result/new/", views.result_create, name="result_create"),
    path("<int:pk>/lab/catalog/", v.catalog_list, name="catalog_list"),
    path("<int:pk>/lab/catalog/new/", v.catalog_create, name="catalog_create"),
    path("<int:pk>/lab/catalog/<int:catalog_id>/edit/", v.catalog_edit, name="catalog_edit"),
    path("<int:pk>/lab/catalog/<int:catalog_id>/delete/", v.catalog_delete, name="catalog_delete"),
    path("<int:pk>/lab/external/", v.external_results_inbox, name="external_results_inbox"),
    path("<int:pk>/lab/external/<int:result_id>/review/", v.external_result_review, name="external_result_review"),
    path("<int:pk>/lab/external/<int:result_id>/decision/", v.external_result_decision, name="external_result_decision"),
    
    path("<int:pk>/lab/external/panel/", v.external_results_panel, name="external_results_panel"),
    path("<int:pk>/lab/external/review/<int:result_id>/", v.external_result_review, name="external_result_review"),
    path("<int:pk>/lab/external/decision/<int:result_id>/", v.external_result_decision, name="external_result_decision"),
]
