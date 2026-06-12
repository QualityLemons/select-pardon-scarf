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
    
    def submit_maintenance_log(request, work_order_id):
    if request.method == 'POST':
        MaintenanceLog.objects.create(
            user=request.user,
            work_order_id=work_order_id,
            v_idle=request.POST.get('v_idle'),
            v_active=request.POST.get('v_active'),
            signal_registered=(request.POST.get('signal_reg') == 'yes'),
            notes=request.POST.get('notes')
        )
        return redirect('dashboard')