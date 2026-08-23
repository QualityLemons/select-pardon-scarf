from django.urls import path

from .views import PLeCLoginView, PLeCLogoutView, RegisterView, profile_view

app_name = "accounts"

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", PLeCLoginView.as_view(), name="login"),
    path("logout/", PLeCLogoutView.as_view(), name="logout"),
    path("profile/", profile_view, name="profile"),
]
