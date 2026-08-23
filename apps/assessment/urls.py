from django.urls import path

from . import api_views

urlpatterns = [
    path("modules", api_views.modules_list, name="api_modules"),
    path("tips/<str:module_id>", api_views.tips_list, name="api_tips"),
    path("assess", api_views.assess_submit, name="api_assess"),
    path("assess/", api_views.assess_submit),
    path("results", api_views.results_list_or_create, name="api_results"),
    path("results/<int:result_id>", api_views.result_detail, name="api_result_detail"),
    path("results/<int:result_id>/note", api_views.update_note, name="api_result_note"),
]
