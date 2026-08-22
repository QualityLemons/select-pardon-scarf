from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import views as auth_views
from apps.accounts import views as account_views
from apps.assessment.views import (
    ResultHistoryView, ReflectionCreateView, ReflectionListView,
    ReflectionUpdateView, ReflectionDeleteView,
)


class LoginRequiredTemplateView(LoginRequiredMixin, TemplateView):
    """A TemplateView that redirects to /login/ when the user is not authenticated."""

# Sub-pages served under /challenge/<slug>/
_challenge_pages = [
    path('plc-primer/',        TemplateView.as_view(template_name='challenge/plc-primer.html'),        name='challenge_plc_primer'),
    path('multimeter/',        TemplateView.as_view(template_name='challenge/multimeter.html'),        name='challenge_multimeter'),
    path('multimeter-lesson/', TemplateView.as_view(template_name='challenge/multimeter-lesson.html'), name='challenge_multimeter_lesson'),
    path('level1/',            TemplateView.as_view(template_name='challenge/level1.html'),            name='challenge_level1'),
    path('level2/',            TemplateView.as_view(template_name='challenge/level2.html'),            name='challenge_level2'),
    path('level3/',            TemplateView.as_view(template_name='challenge/level3.html'),            name='challenge_level3'),
    path('level4/',            TemplateView.as_view(template_name='challenge/level4.html'),            name='challenge_level4'),
    path('level5/',            TemplateView.as_view(template_name='challenge/level5.html'),            name='challenge_level5'),
    path('level6/',            TemplateView.as_view(template_name='challenge/level6.html'),            name='challenge_level6'),
    path('learn-your-log/',    TemplateView.as_view(template_name='challenge/learn-your-log.html'),    name='challenge_learn_your_log'),
    path('maintenance-log/',   TemplateView.as_view(template_name='challenge/maintenance-log.html'),   name='challenge_maintenance_log'),
]

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

    path('password-reset/', account_views.RateLimitedPasswordResetView.as_view(
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
    path('profile/edit/', account_views.EditProfileView.as_view(), name='profile_edit'),
    path('api/donations/payment-intent/', account_views.DonationPaymentIntentView.as_view(), name='donation_payment_intent'),
    path('reflect/', ReflectionCreateView.as_view(), name='reflect'),
    path('reflect/all/', ReflectionListView.as_view(), name='reflect_list'),
    path('reflect/<int:pk>/edit/', ReflectionUpdateView.as_view(), name='reflect_edit'),
    path('reflect/<int:pk>/delete/', ReflectionDeleteView.as_view(), name='reflect_delete'),
    path('api/', include('apps.assessment.urls')),

    # Donation page — login required; shown after completing the final mission
    path('donate/', account_views.DonateView.as_view(), name='donate'),

    # Game home
    path('', TemplateView.as_view(template_name='challenge/index.html'), name='home'),

    # Individual challenge/lesson pages
    path('challenge/', include(_challenge_pages)),
]
