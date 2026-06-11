const plc = new PLC(); // Your existing PLC Engine class
const hardware = { switchA: false };

function toggleSwitch(id) {
    hardware.switchA = !hardware.switchA;
    // Visually toggle the switch color
    const sw = document.getElementById(`switch-${id}`);
    sw.setAttribute('fill', hardware.switchA ? '#00cc00' : '#333');
}

// The Scan Cycle loop
setInterval(() => {
    const outputs = plc.scan(hardware);
    
    // Update Lamp visual based on scan result
    const lamp = document.getElementById('lamp-Q0');
    lamp.setAttribute('fill', outputs.lampStatus ? 'yellow' : '#444');
}, 50);