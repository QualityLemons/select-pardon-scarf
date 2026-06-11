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