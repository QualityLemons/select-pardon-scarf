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

const hardware = { startBtn: false, stopBtn: true }; // stopBtn defaults to TRUE (Normally Closed)

function toggleStart() {
    hardware.startBtn = !hardware.startBtn;
}

function toggleStop() {
    hardware.stopBtn = !hardware.stopBtn;
}

// Inside your scan interval:
setInterval(() => {
    const outputs = plc.scan(hardware);
    document.getElementById('lamp-Q0').setAttribute('fill', outputs.lampStatus ? 'yellow' : '#444');
}, 50);

function updateWiring(engineState) {
    // If Switch I0 is ON, the wire segment after the switch becomes "Hot" (Red)
    const wireL2 = document.getElementById('wire-L2');
    const isEnergized = engineState.inputs['I0']; 
    
    wireL2.setAttribute('stroke', isEnergized ? 'red' : 'black');
}

// Inside the Scan Cycle
setInterval(() => {
    const outputs = plc.scan(hardware);
    // 1. Update output visualization
    updateLamp(outputs.lampStatus);
    // 2. Update the "Live" wire visualization
    updateWiring(plc); 
}, 50);