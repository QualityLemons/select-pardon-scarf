from django.urls import re_path
from . import api_views

urlpatterns = [
    re_path(r'^me/?$', api_views.MeView.as_view(), name='api_me'),
    re_path(r'^modules/?$', api_views.ModulesView.as_view(), name='api_modules'),
    re_path(r'^tips/(?P<module_id>[^/]+)/?$', api_views.TipsView.as_view(), name='api_tips'),
    re_path(r'^assess/?$', api_views.AssessView.as_view(), name='api_assess'),
    re_path(r'^results/?$', api_views.ResultsListView.as_view(), name='api_results_list'),
    re_path(r'^results/(?P<rid>\d+)/?$', api_views.ResultDetailView.as_view(), name='api_results_detail'),
    re_path(r'^mission-log/(?P<level>[^/]+)/?$', api_views.MissionLogView.as_view(), name='api_mission_log'),
    re_path(r'^mission-log/(?P<level>[^/]+)/(?P<eid>\d+)/?$', api_views.MissionLogEntryView.as_view(), name='api_mission_log_entry'),
    re_path(r'^prereq-dismissals/?$', api_views.PrereqDismissalView.as_view(), name='api_prereq_dismissals'),
]
