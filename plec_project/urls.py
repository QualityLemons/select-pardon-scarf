from django.contrib import admin
from django.conf import settings
from django.urls import path, include
from django.views.generic import RedirectView
from django.contrib.auth import views as auth_views
from apps.accounts import views as account_views
from apps.assessment.views import ResultHistoryView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', account_views.LoginView.as_view(), name='login'),
    path('logout/', account_views.LogoutView.as_view(), name='logout'),
    path('lockout/', account_views.LockoutView.as_view(), name='lockout'),
    path('register/', account_views.RegisterView.as_view(), name='register'),

    path('password-change/', auth_views.PasswordChangeView.as_view(
        template_name='accounts/password_change.html',
        success_url='/password-change/done/',
    ), name='password_change'),
    path('password-change/done/', auth_views.PasswordChangeDoneView.as_view(
        template_name='accounts/password_change_done.html',
    ), name='password_change_done'),

    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='registration/password_reset_form.html',
        email_template_name='registration/password_reset_email.txt',
        subject_template_name='registration/password_reset_subject.txt',
        success_url='/password-reset/done/',
    ), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='registration/password_reset_done.html',
    ), name='password_reset_done'),
    path('password-reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='registration/password_reset_confirm.html',
        success_url='/password-reset/complete/',
    ), name='password_reset_confirm'),
    path('password-reset/complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name='registration/password_reset_complete.html',
    ), name='password_reset_complete'),

    path('profile/', ResultHistoryView.as_view(), name='profile'),
    path('api/', include('apps.assessment.urls')),
]

if settings.DEBUG:
    from django.views.static import serve
    urlpatterns += [
        path('challenge/<path:path>', serve, {'document_root': settings.CHALLENGE_DIR}),
        path('challenge/', serve, {'document_root': settings.CHALLENGE_DIR, 'path': 'index.html'}),
        path('', serve, {'document_root': settings.CHALLENGE_DIR, 'path': 'index.html'}),
    ]
else:
    urlpatterns += [
        path('challenge/', RedirectView.as_view(url='/static/challenge/index.html', permanent=False)),
        path('', RedirectView.as_view(url='/static/challenge/index.html', permanent=False)),
    ]
