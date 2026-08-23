from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView

from apps.assessment.models import AssessmentResult

from .forms import LoginForm, ProfileForm, RegisterForm
from .models import UserProfile


class RegisterView(CreateView):
    form_class = RegisterForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("accounts:profile")

    def form_valid(self, form):
        response = super().form_valid(form)
        UserProfile.objects.get_or_create(user=self.object)
        login(self.request, self.object)
        return response


class PLeCLoginView(LoginView):
    form_class = LoginForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True


class PLeCLogoutView(LogoutView):
    next_page = reverse_lazy("home")


@login_required
def profile_view(request):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)

    if request.method == "POST":
        form = ProfileForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            profile.organisation = request.POST.get("organisation", "").strip()
            profile.job_title = request.POST.get("job_title", "").strip()
            profile.bio = request.POST.get("bio", "").strip()
            profile.save()
            messages.success(request, "Your profile has been updated.")
            return redirect("accounts:profile")
    else:
        form = ProfileForm(instance=user)

    results = AssessmentResult.objects.filter(user=user).order_by("-created_at")

    level_labels = {
        "level1": "Start/Stop Latching",
        "level2": "Tank Filling System",
        "level3": "Modbus TCP",
        "level4": "Safety Interlock",
        "level5": "Timed Conveyor (TON)",
        "level6": "Sequential Batching",
    }

    context = {
        "form": form,
        "profile": profile,
        "results": results,
        "level_labels": level_labels,
        "total_attempts": results.count(),
        "best_score": results.order_by("-score").first(),
        "stripe_publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
    }
    return render(request, "accounts/profile.html", context)
