from django.contrib import admin
from django.urls import include, path, re_path

from config.views import challenge_file, home

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", home, name="home"),
    path("accounts/", include("apps.accounts.urls")),
    path("api/", include("apps.assessment.urls")),
    path("donate/", include("apps.donations.urls")),
    re_path(r"^(?P<path>.+\.(html|css|js|png|jpg|svg|ico))$", challenge_file),
]
