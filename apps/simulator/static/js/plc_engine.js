/**
 * Simple PLC Scan Cycle Engine
 */
class PLCEngine {
    constructor() {
        this.inputs = { 'I0': false, 'I1': false };
        this.outputs = { 'Q0': false };
        this.memory = {}; // Internal relays (M bits)
    }

    // 1. READ INPUTS: Map physical switch states to memory
    readInputs(physicalHardwareState) {
        this.inputs['I0'] = physicalHardwareState.switchA;
        this.inputs['I1'] = physicalHardwareState.switchB;
    }

    // 2. EXECUTE LOGIC: The "Ladder Logic" simulation
    executeLogic() {
        // Simple logic: Q0 = I0 AND NOT I1
        // (A motor starts if switch A is on, but only if emergency stop switch B is NOT pressed)
        this.outputs['Q0'] = (this.inputs['I0'] === true && this.inputs['I1'] === false);
    }

    // 3. WRITE OUTPUTS: Map memory to physical hardware
    writeOutputs() {
        return {
            motorLight: this.outputs['Q0']
        };
    }

    // The main loop that runs every ~100ms
    scan(physicalState) {
        this.readInputs(physicalState);
        this.executeLogic();
        return this.writeOutputs();
    }
}

// Instantiate and start simulation
const myPLC = new PLCEngine();

class PLC {
    constructor() {
        // Physical memory representation
        this.inputs = { 'I0': false };
        this.outputs = { 'Q0': false };
    }

    // 1. READ: Update the virtual state from physical "hardware"
    readInputs(physicalSwitches) {
        this.inputs['I0'] = physicalSwitches.switchA;
    }

    // 2. EXECUTE: The Ladder Logic
    // This runs in a "snapshot" of time, ignoring outside changes 
    // until the next cycle begins.
    executeLogic() {
        // Simple Ladder Logic: Lamp (Q0) is ON if Switch (I0) is ON
        this.outputs['Q0'] = this.inputs['I0'];
    }

    // 3. WRITE: Update the output hardware
    writeOutputs() {
        return { lampStatus: this.outputs['Q0'] };
    }

    // The Scan Cycle
    scan(physicalSwitches) {
        this.readInputs(physicalSwitches);
        this.executeLogic();
        return this.writeOutputs();
    }
}

const myPLC = new PLC();
const physicalHardware = { switchA: false };

// UI Interaction
document.getElementById('mySwitch').addEventListener('click', (e) => {
    physicalHardware.switchA = !physicalHardware.switchA;
});

// The continuous Scan Cycle (mimicking the 10-50ms scan time of a real PLC)
setInterval(() => {
    const hardwareResult = myPLC.scan(physicalHardware);
    
    // Update the Lamp visualization
    const lamp = document.getElementById('myLamp');
    lamp.style.backgroundColor = hardwareResult.lampStatus ? 'yellow' : 'gray';
}, 50); // 50ms scan cycle

class PLC {
    constructor() {
        this.inputs = { 'I0': false, 'I1': false }; // I0=Start, I1=Stop
        this.outputs = { 'Q0': false };
        this.memory = { 'M0': false };             // Internal Bit
    }

    readInputs(physicalSwitches) {
        this.inputs['I0'] = physicalSwitches.startBtn;
        this.inputs['I1'] = physicalSwitches.stopBtn;
    }

    executeLogic() {
        // Latching Logic (Self-Holding Circuit)
        // M0 turns ON if Start (I0) is pressed OR if M0 is already ON
        // M0 turns OFF if Stop (I1) is pressed
        
        const startCondition = this.inputs['I0'] || this.memory['M0'];
        const stopCondition = !this.inputs['I1']; // Assuming I1 is normally closed

        this.memory['M0'] = (startCondition && stopCondition);
        
        // Output follows the internal memory
        this.outputs['Q0'] = this.memory['M0'];
    }

    writeOutputs() {
        return { lampStatus: this.outputs['Q0'] };
    }

    scan(physicalSwitches) {
        this.readInputs(physicalSwitches);
        this.executeLogic();
        return this.writeOutputs();
    }
}

class PLCWithFaults extends PLC {
    constructor() {
        super();
        this.activeFaults = []; // List of injected faults
    }

    readInputs(physicalSwitches) {
        // Apply fault logic: If 'BROKEN_WIRE' is on I0, it always reads False
        let I0_state = physicalSwitches.startBtn;
        
        if (this.activeFaults.includes('I0_BROKEN_WIRE')) {
            I0_state = false; // The signal never reaches the PLC
        }

        this.inputs['I0'] = I0_state;
        this.inputs['I1'] = physicalSwitches.stopBtn;
    }
    
    injectFault(faultCode) {
        this.activeFaults.push(faultCode);
    }
}