from django.urls import path

from . import views

app_name = "donations"

urlpatterns = [
    path("create-checkout/", views.create_checkout, name="create_checkout"),
    path("success/", views.success_view, name="success"),
    path("cancel/", views.cancel_view, name="cancel"),
]
