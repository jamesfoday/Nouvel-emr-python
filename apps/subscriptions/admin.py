# apps/subscriptions/admin.py
from django.contrib import admin
from .models import Plan, Subscription

@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "interval", "price_cents", "is_active", "sort_order")
    list_filter = ("interval", "is_active")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "status", "current_period_end", "cancel_at_period_end")
    list_filter = ("status", "plan__interval")
    search_fields = ("user__email", "user__username", "stripe_sub_id")
