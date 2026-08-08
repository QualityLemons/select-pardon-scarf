from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Max, OuterRef, Subquery
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.views.generic import ListView
from .forms import ReflectionForm
from .models import AssessmentResult, MissionLogEntry


class ResultHistoryView(LoginRequiredMixin, ListView):
    template_name = 'assessment/history.html'
    context_object_name = 'results'
    paginate_by = 20

    def get_queryset(self):
        return AssessmentResult.objects.filter(
            user=self.request.user
        ).order_by('-created_at')

    # Maps URL sort key → ORM order_by expression
    _SORT_MAP = {
        'level':     'level_key',
        '-level':    '-level_key',
        'grade':     'best_grade',
        '-grade':    '-best_grade',
        'score':     'best_score',
        '-score':    '-best_score',
        'attempts':  'attempts',
        '-attempts': '-attempts',
    }
    _DEFAULT_SORT = 'level'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        sort_param = self.request.GET.get('sort', self._DEFAULT_SORT)
        if sort_param not in self._SORT_MAP:
            sort_param = self._DEFAULT_SORT
        orm_order = self._SORT_MAP[sort_param]

        # Grade belonging to the highest-scoring attempt for each level
        best_grade_sub = (
            AssessmentResult.objects
            .filter(user=self.request.user, level_key=OuterRef('level_key'))
            .order_by('-score')
            .values('grade')[:1]
        )

        ctx['best_scores'] = (
            AssessmentResult.objects
            .filter(user=self.request.user)
            .values('level_key')
            .annotate(
                best_score=Max('score'),
                attempts=Count('id'),
                best_grade=Subquery(best_grade_sub),
            )
            .order_by(orm_order)
        )

        # Expose sort state to the template
        ctx['sort'] = sort_param
        return ctx


class ReflectionCreateView(LoginRequiredMixin, View):
    """
    GET  — display the blank reflection form + the user's recent entries.
    POST — validate and create a MissionLogEntry; redirect with ?saved=1 on success.
    """
    template_name = 'assessment/reflect.html'
    login_url = '/login/'
    _PREVIEW_COUNT = 10

    def _entries_context(self, request):
        qs = MissionLogEntry.objects.filter(user=request.user).order_by('-created_at')
        total = qs.count()
        entries = qs[:self._PREVIEW_COUNT]
        return entries, total

    def get(self, request):
        form = ReflectionForm()
        entries, total = self._entries_context(request)
        return render(request, self.template_name, {
            'form': form,
            'entries': entries,
            'total_count': total,
            'preview_count': self._PREVIEW_COUNT,
            'saved': request.GET.get('saved'),
        })

    def post(self, request):
        form = ReflectionForm(request.POST)
        if form.is_valid():
            MissionLogEntry.objects.create(
                user=request.user,
                level=form.cleaned_data['level'],
                skill=form.cleaned_data['skill'],
                notes=form.cleaned_data['notes'],
                rating=form.cleaned_data['rating'],
            )
            return redirect('/reflect/?saved=1')
        entries, total = self._entries_context(request)
        return render(request, self.template_name, {
            'form': form,
            'entries': entries,
            'total_count': total,
            'preview_count': self._PREVIEW_COUNT,
            'saved': None,
        })


class ReflectionListView(LoginRequiredMixin, ListView):
    """
    Paginated list of all reflection entries for the current user.
    Accessible at /reflect/all/?page=N
    """
    template_name = 'assessment/reflect_list.html'
    context_object_name = 'entries'
    paginate_by = 10
    login_url = '/login/'

    def get_queryset(self):
        return MissionLogEntry.objects.filter(
            user=self.request.user
        ).order_by('-created_at')


class ReflectionUpdateView(LoginRequiredMixin, View):
    """
    GET  — pre-populate the form with the existing entry's data.
    POST — validate and save changes; redirect to /reflect/?updated=1.
    Ownership-scoped: returns 404 if the entry belongs to a different user.
    """
    template_name = 'assessment/reflect_edit.html'
    login_url = '/login/'

    def _get_entry(self, request, pk):
        return get_object_or_404(MissionLogEntry, pk=pk, user=request.user)

    def get(self, request, pk):
        entry = self._get_entry(request, pk)
        form = ReflectionForm(initial={
            'level':  entry.level,
            'skill':  entry.skill,
            'notes':  entry.notes,
            'rating': entry.rating,
        })
        return render(request, self.template_name, {'form': form, 'entry': entry})

    def post(self, request, pk):
        entry = self._get_entry(request, pk)
        form = ReflectionForm(request.POST)
        if form.is_valid():
            entry.level  = form.cleaned_data['level']
            entry.skill  = form.cleaned_data['skill']
            entry.notes  = form.cleaned_data['notes']
            entry.rating = form.cleaned_data['rating']
            entry.save(update_fields=['level', 'skill', 'notes', 'rating'])
            return redirect('/reflect/?updated=1')
        return render(request, self.template_name, {'form': form, 'entry': entry})


class ReflectionDeleteView(LoginRequiredMixin, View):
    """
    GET  — show a confirmation page with the entry preview.
    POST — delete the entry; redirect to /reflect/?deleted=1.
    Ownership-scoped: returns 404 if the entry belongs to a different user.
    """
    template_name = 'assessment/reflect_delete.html'
    login_url = '/login/'

    def _get_entry(self, request, pk):
        return get_object_or_404(MissionLogEntry, pk=pk, user=request.user)

    def get(self, request, pk):
        entry = self._get_entry(request, pk)
        return render(request, self.template_name, {'entry': entry})

    def post(self, request, pk):
        entry = self._get_entry(request, pk)
        entry.delete()
        return redirect('/reflect/?deleted=1')
