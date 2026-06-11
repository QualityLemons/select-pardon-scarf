from django.shortcuts import render, get_object_or_404
from .models import WorkOrder

def workbench_view(request, work_order_id):
    # Fetch a specific "Broken Program" from the database
    work_order = get_object_or_404(WorkOrder, id=work_order_id)
    
    context = {
        'work_order': work_order,
        # Pass the JSON logic to the template so JS can use it
        'initial_logic': work_order.broken_logic 
    }
    return render(request, 'simulator/workbench.html', context)

def submit_work_order(request, work_order_id):
    if request.method == 'POST':
        user_submission = request.POST.get('logic') # From JS
        work_order = WorkOrder.objects.get(id=work_order_id)
        
        passed, feedback = evaluate_logic(user_submission, work_order.target_logic)
        
        Assessment.objects.create(
            user=request.user,
            work_order=work_order,
            submitted_logic=user_submission,
            is_correct=passed,
            manager_feedback=feedback
        )
        # Update WorkOrder status
        work_order.status = 'C' if passed else 'I'
        work_order.save()
        
    return redirect('dashboard')