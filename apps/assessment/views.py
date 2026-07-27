from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView
from .models import AssessmentResult


class ResultHistoryView(LoginRequiredMixin, ListView):
    template_name = 'assessment/history.html'
    context_object_name = 'results'
    paginate_by = 20

    def get_queryset(self):
        return AssessmentResult.objects.filter(
            user=self.request.user
        ).order_by('-created_at')
