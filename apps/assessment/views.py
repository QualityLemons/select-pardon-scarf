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