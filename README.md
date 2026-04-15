# pycaenhv: Python Toolkit for CAEN High Voltage Systems

A modernized, lightweight Python toolkit designed for efficient control and monitoring of CAEN High Voltage (HV) devices (SY series mainframes, NDT1470, etc.). 

This project uses a **ZeroMQ-based Server-Client architecture** to allow multiple simultaneous connections, remote monitoring, and robust background operation.

## 1. Key Features
- **Server-Client Architecture**: A central server manages the hardware link, while multiple CLI/GUI clients can connect simultaneously.
- **Table-less Server**: The server automatically discovers all available hardware slots and channels. Configuration (naming, grouping) is managed by the clients.
- **Automated Parameter Calculation**: Clients automatically calculate current limits ($I_0Set$) based on target voltage ($V$) and resistance ($R$ in MΩ) using Ohm's Law ($I = V/R$), including a 10% safety margin.
- **Daemon Support**: The server can run in the background with robust logging and signal handling.
- **Multi-Client Monitoring**: ZeroMQ PUB/SUB pattern allows real-time telemetry broadcasting to all connected clients.
- **GUI & CLI**: Professional terminal dashboard (CLI) and a flexible PySide6 GUI with remote connection support.

## 2. File Structure
- `caenhv.py`: Core hardware interface wrapping `CAENHVWrapper` via `ctypes`. Supports dynamic crate map discovery.
- `hvserver.py`: Central background service. Manages the direct CAEN connection and ZeroMQ sockets.
- `hvclient.py`: Shared communication library used by both CLI and GUI. Handles command timeouts and reconnection.
- `hvcontrol.py`: CLI client (Local Only). Table-based monitoring and control.
- `hvcontrol_gui.py`: GUI client (Local/Remote). Supports server address selection and interactive table editing.
- `hvchannel.py`: Shared data model for channel parameters.
- `hv.table`: (User-provided) Configuration file for channel-to-pmt mapping.

## 3. Prerequisites

### 1) CAEN HV Wrapper Library
Official `CAENHVWrapper` library must be installed and in your library path:
```bash
export LD_LIBRARY_PATH=/path/to/caen/lib:$LD_LIBRARY_PATH
```

### 2) Python Dependencies
Requires `pyzmq` for communication and `PySide6` for the GUI:
```bash
pip install pyzmq PySide6
```

### 3) System Dependencies (OpenSSL 1.1)
CAEN libraries often require OpenSSL 1.1 compatibility:
- **RHEL/Rocky/AlmaLinux**: `sudo dnf install compat-openssl11`

## 4. Usage Flow

### Step 1: Start the Server (`hvserver.py`)
The server must be running to handle hardware communication.

**Foreground Mode (with output):**
```bash
python hvserver.py --ip [MAINFRAME_IP] --sys [SYS_TYPE]
```

**Daemon Mode (Background):**
```bash
python hvserver.py --daemon --log hvserver.log
```
*The server will automatically discover all slots and channels. Check `hvserver.log` for details.*

### Step 2: Launch a Client

#### CLI Client (Local Monitoring)
```bash
# Monitor all channels in hv.table
python hvcontrol.py mon -t hv.table

# Power on a specific group
python hvcontrol.py on -g 10 -t hv.table
```

#### GUI Client (Remote/Local Monitoring)
```bash
python hvcontrol_gui.py
```
1. **Load Table**: Click **Browse...** to select your `hv.table`.
2. **Set Server**: Enter the **Server Address** (IP or `localhost`).
3. **Connect**: Click **Connect**. The client will synchronize your table settings (Names, I-limits) with the server.
4. **Interactive Control**: 
   - **Edit VSet**: Double-click "Set (V)" cells to change voltage (I-limit is auto-recalculated).
   - **Toggle Power**: Double-click the "Status" cell of an individual channel.
   - **Group Control**: Use the "Group Filter" and the Power ON/OFF buttons.

## 5. Communications Protocol
- **CMD Port (5555)**: ZMQ REQ/REP pattern for explicit commands (Turn ON, Set Voltage).
- **PUB Port (5556)**: ZMQ PUB/SUB pattern for 1Hz real-time telemetry broadcasting.