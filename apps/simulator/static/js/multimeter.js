let isProbeMode = false;

function toggleMultimeter() {
    isProbeMode = !isProbeMode;
    document.getElementById('workbench-svg').style.cursor = isProbeMode ? 'crosshair' : 'default';
}

// Attach click listener to all SVG wire segments
document.querySelectorAll('line[id^="wire-"]').forEach(wire => {
    wire.addEventListener('click', () => {
        if (!isProbeMode) return;

        // Determine voltage based on the wire's logical state
        // In this simulation, L1 (Power) is 24V, others are logic-dependent
        const isEnergized = (wire.getAttribute('stroke') === 'red');
        const voltage = isEnergized ? "24V" : "0V";
        
        alert(`Multimeter Reading: ${voltage}`);
    });
});