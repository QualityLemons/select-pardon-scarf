def evaluate_logic(submitted, target):
    # Check if all output states match
    if submitted['outputs'] != target['outputs']:
        return False, "The machine logic is not achieving the required output state."
    
    # Check for efficiency: Compare number of rungs/gates used
    if len(submitted['rungs']) > len(target['rungs']):
        return True, "Task completed, but the solution was inefficient. Consider optimizing the logic."
    
    return True, "Excellent work. The logic is functional and optimized."