from apps.assessment.models import Assessment

@login_required
def dashboard_view(request):
    my_tasks = WorkOrder.objects.filter(assigned_to=request.user).exclude(status='C')
    
    # Get the most recent assessment for this user
    latest_feedback = Assessment.objects.filter(user=request.user).order_by('-timestamp').first()
    
    return render(request, 'enterprise/dashboard.html', {
        'tasks': my_tasks,
        'feedback': latest_feedback
    })