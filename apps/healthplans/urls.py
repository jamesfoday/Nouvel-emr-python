from django.urls import path
from . import views

app_name = "healthplans"

urlpatterns = [
    # Patient-facing
    path("", views.user_plan_list, name="plans"),
    path("checkout/<slug:slug>/", views.checkout_modal, name="checkout_modal"),
    path("checkout/start/", views.checkout_start, name="checkout_start"),
    path("cancel/", views.cancel, name="cancel"),
    path("resume/", views.resume, name="resume"),

    # Staff
    path("staff/", views.staff_plan_list, name="staff_plans"),
    path("staff/create/", views.plan_create, name="plan_create"),
    path("staff/<slug:slug>/edit/", views.plan_update, name="plan_update"),
    path("staff/<slug:slug>/delete/", views.plan_delete, name="plan_delete"),
    path("staff/enroll/", views.staff_enroll_patient, name="staff_enroll_patient"),
    path("staff/<slug:slug>/archive/", views.plan_archive, name="plan_archive"),
    path("staff/enrollment/<int:enrollment_id>/cancel/", views.staff_enrollment_cancel, name="staff_enrollment_cancel"),
    path("staff/enrollment/<int:enrollment_id>/resume/", views.staff_enrollment_resume, name="staff_enrollment_resume"),


]
