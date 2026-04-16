# hvcontrol_gui.py

import sys
import os
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
                               QHeaderView, QMessageBox, QLabel, QLineEdit, QFileDialog,
                               QComboBox, QAbstractItemView)
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor
from datetime import datetime

# Import hardware control modules
import hvconfig
from hvclient import HVClient
from hvchannel import HVChannel


def load_hv_table(filepath):
    """
    Parses the HV configuration table from a text file.
    """
    channels = []
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")

    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            parts = line.split()
            if len(parts) >= 7:
                ch = HVChannel(
                    name=parts[0], slot=parts[1], channel=parts[2],
                    hv_set=parts[3], r_val=parts[4], pmtid=parts[5], group=parts[6]
                )
                channels.append(ch)
    return channels


class HVControlApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CAEN HV Control & Monitor")
        self.resize(1000, 650)

        # Initialize client and state variables
        self.client = HVClient()
        self.all_channels = []
        self.is_connected = False

        self.setup_ui()

        # Status bar: connection status (left) + live clock (right)
        self.statusBar().showMessage("Disconnected")
        self._clock_label = QLabel()
        self.statusBar().addPermanentWidget(self._clock_label)
        self._update_clock()

        # Set up the monitoring timer (1-second interval)
        self.monitor_timer = QTimer(self)
        self.monitor_timer.timeout.connect(self.update_monitor)

        # Clock timer (always ticking, even when disconnected)
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)

        # Track server hardware state for dynamic control enable/disable
        self._hw_state = "degraded"   # "operational" | "degraded"
        self._health_fail_count = 0   # consecutive get_server_health failures
        self._HEALTH_FAIL_MAX = 3     # disconnect after this many consecutive failures

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # --- First Row: File Selection Area ---
        file_layout = QHBoxLayout()
        self.file_input = QLineEdit("hv.table")
        self.file_input.setReadOnly(True)
        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.clicked.connect(self.browse_file)

        file_layout.addWidget(QLabel("Table File:"))
        file_layout.addWidget(self.file_input)
        file_layout.addWidget(self.btn_browse)
        layout.addLayout(file_layout)

        # --- Second Row: Connection & Group Control Area ---
        conn_layout = QHBoxLayout()

        conn_layout.addWidget(QLabel("Server Address:"))
        self.host_input = QLineEdit("localhost")
        self.host_input.setFixedWidth(120)
        conn_layout.addWidget(self.host_input)

        self.btn_connect = QPushButton("Connect")
        self.btn_connect.clicked.connect(self.toggle_connection)
        conn_layout.addWidget(self.btn_connect)

        conn_layout.addStretch()

        self.group_combo = QComboBox()
        self.group_combo.addItem("All")
        self.group_combo.currentTextChanged.connect(self.filter_table)
        self.group_combo.setFixedWidth(100)

        self.btn_on = QPushButton("Power ON")
        self.btn_on.clicked.connect(self.power_on_selected)
        self.btn_on.setEnabled(False)

        self.btn_off = QPushButton("Power OFF")
        self.btn_off.clicked.connect(self.power_off_selected)
        self.btn_off.setEnabled(False)

        conn_layout.addWidget(QLabel("Group Filter:"))
        conn_layout.addWidget(self.group_combo)
        conn_layout.addWidget(self.btn_on)
        conn_layout.addWidget(self.btn_off)
        layout.addLayout(conn_layout)

        # --- Monitoring Table ---
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Group", "Name", "Slot", "Ch", "Set (V)", "VMon (V)", "IMon (uA)", "Status"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        # Enable double-click to edit (Specific columns will be enabled in filter_table)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)

        # Connect signals
        self.table.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.table.itemChanged.connect(self.on_item_changed)

        layout.addWidget(self.table)

        self.load_data(show_error=False)

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open HV Table File", "", "Table Files (*.table *.txt);;All Files (*)"
        )
        if file_path:
            self.file_input.setText(file_path)
            self.load_data()

    def _update_clock(self):
        """Update the status bar clock label with the current local time."""
        self._clock_label.setText(
            datetime.now().strftime("  %Y-%m-%d  %H:%M:%S  "))

    def _set_hw_operational(self, operational: bool):
        """Enable or disable write controls based on hw_state."""
        self.btn_on.setEnabled(operational)
        self.btn_off.setEnabled(operational)
        # Make Name/Set(V) cells editable only when hardware is ready
        for row in range(self.table.rowCount()):
            for col in [1, 4]:   # Name, Set(V)
                item = self.table.item(row, col)
                if item:
                    if operational:
                        item.setFlags(item.flags() | Qt.ItemIsEditable)
                    else:
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)

    def load_data(self, show_error=True):
        filepath = self.file_input.text()
        try:
            self.all_channels = load_hv_table(filepath)
            self.group_combo.blockSignals(True)
            self.group_combo.clear()
            self.group_combo.addItem("All")
            groups = sorted(list(set(ch.group for ch in self.all_channels)))
            self.group_combo.addItems(groups)
            self.group_combo.blockSignals(False)
            self.filter_table()
        except Exception as e:
            if show_error:
                QMessageBox.warning(self, "File Error",
                                    f"Failed to load table:\n{e}")

    def filter_table(self):
        selected_group = self.group_combo.currentText()
        self.table.blockSignals(True)   # Prevent on_item_changed during table rebuild
        self.table.setRowCount(0)

        is_filtering = (selected_group != "All")
        blue_color = QColor("blue")

        for ch in self.all_channels:
            row = self.table.rowCount()
            self.table.insertRow(row)

            items = [
                QTableWidgetItem(ch.group),
                QTableWidgetItem(ch.name),
                QTableWidgetItem(str(ch.slot)),
                QTableWidgetItem(str(ch.channel)),
                QTableWidgetItem(str(ch.hv_set)),
                QTableWidgetItem("0.00"),
                QTableWidgetItem("0.00"),
                QTableWidgetItem("OFF")
            ]

            if is_filtering and ch.group == selected_group:
                for item in items:
                    item.setForeground(blue_color)

            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignCenter)

                # Enable editing only for Name (1) and Set (V) (4) columns
                if col in [1, 4]:
                    item.setFlags(item.flags() | Qt.ItemIsEditable)
                else:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)

                self.table.setItem(row, col, item)

            self.table.item(row, 0).setData(Qt.UserRole, ch)
        self.table.blockSignals(False)

    def toggle_connection(self):
        if not self.is_connected:
            if not self.all_channels:
                QMessageBox.warning(
                    self, "Warning", "No channels loaded.\nPlease load a valid table file first.")
                return

            host = self.host_input.text().strip()
            self.client.close()
            self.client = HVClient(
                cmd_url=f"tcp://{host}:{hvconfig.CMD_PORT}",
                sub_url=f"tcp://{host}:{hvconfig.PUB_PORT}")

            if not self.client.check_server():
                QMessageBox.critical(
                    self, "Connection Error",
                    f"HV Server is not running at {host}.\nPlease start hvserver.py first.")
                return

            # Fetch server hardware state
            try:
                health = self.client.get_server_health()
                self._hw_state = health.get("hw_state", "degraded")
            except Exception:
                self._hw_state = "degraded"

            if self._hw_state == "operational":
                # Full connect: sync settings then start monitoring
                try:
                    self._sync_hardware_settings()
                except Exception as e:
                    QMessageBox.critical(
                        self, "Sync Error", f"Failed to push settings to server:\n{e}")
                    return
                self.statusBar().showMessage(
                    f"Server: RUNNING  ({host}:{hvconfig.CMD_PORT})")
                QMessageBox.information(self, "Connected",
                                        "Connected and synchronized with HV Server.")
            else:
                # Degraded: monitoring only, skip sync
                self.statusBar().showMessage(
                    f"Server: DEGRADED (waiting CAEN)  ({host}:{hvconfig.CMD_PORT})")
                QMessageBox.warning(
                    self, "Server Degraded",
                    "HV server is running but hardware is not connected.\n"
                    "Monitoring only — write controls are disabled.\n"
                    "Controls will be enabled automatically when hardware reconnects.")

            self.is_connected = True
            self.btn_connect.setText("Disconnect")
            self._set_hw_operational(self._hw_state == "operational")
            self.monitor_timer.start(1000)

        else:
            self.monitor_timer.stop()
            self.is_connected = False
            self._hw_state = "degraded"
            self._health_fail_count = 0
            self.btn_connect.setText("Connect")
            self.btn_on.setEnabled(False)
            self.btn_off.setEnabled(False)
            self.statusBar().showMessage("Disconnected")

    def on_item_changed(self, item):
        if not self.is_connected or self._hw_state != "operational":
            return

        col = item.column()
        row = item.row()

        if col not in [1, 4]:
            return

        ch = self.table.item(row, 0).data(Qt.UserRole)
        if not ch:
            return

        self.table.blockSignals(True)
        try:
            new_val = item.text().strip()

            if col == 1:  # Name
                ch.name = new_val
                self.client.send_command("set_name", int(
                    ch.slot), int(ch.channel), new_val)

            elif col == 4:  # Set (V)
                try:
                    v_set = float(new_val)
                    ch.hv_set = v_set
                    # Recalculate I-limit
                    i_limit = (v_set / ch.r_val) * 1.1
                    self.client.send_command("set_vset", int(
                        ch.slot), int(ch.channel), v_set)
                    self.client.send_command("set_iset", int(
                        ch.slot), int(ch.channel), i_limit)
                except ValueError:
                    item.setText(f"{ch.hv_set:.2f}")
                    QMessageBox.warning(
                        self, "Invalid Input", "Please enter a valid number for Voltage.")

        except TimeoutError as e:
            QMessageBox.warning(self, "Timeout Error",
                                f"Server communication timeout:\n{e}")
        except Exception as e:
            QMessageBox.warning(self, "Sync Error",
                                f"Failed to update server:\n{e}")

        self.table.blockSignals(False)

    def on_item_double_clicked(self, item):
        if not self.is_connected:
            return
        if item.column() != 7:
            return

        row = item.row()
        ch = self.table.item(row, 0).data(Qt.UserRole)

        reply = QMessageBox.question(
            self, 'Confirm Power Toggle',
            f"Are you sure you want to toggle power for channel: {ch.name}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                # Check current status from server data
                status = self.client.send_command("get_ch_param", int(
                    ch.slot), int(ch.channel), "Status", "int")
                is_on = status & (1 << 0)
                if is_on:
                    self.client.send_command(
                        "turn_off", int(ch.slot), int(ch.channel))
                else:
                    self.client.send_command(
                        "turn_on", int(ch.slot), int(ch.channel))
            except TimeoutError as e:
                QMessageBox.warning(self, "Timeout Error",
                                    f"Server communication timeout:\n{e}")
            except Exception as e:
                QMessageBox.warning(self, "Control Error",
                                    f"Failed to toggle power:\n{e}")

    def update_monitor(self):
        if not self.is_connected:
            return

        try:
            # --- Check server hw_state every cycle ---
            try:
                health = self.client.get_server_health()
                new_hw_state = health.get("hw_state", "degraded")
                self._health_fail_count = 0   # reset on success
            except Exception:
                self._health_fail_count += 1
                host = self.host_input.text().strip()
                self.statusBar().showMessage(
                    f"Server: UNREACHABLE  ({host})  "
                    f"(retry {self._health_fail_count}/{self._HEALTH_FAIL_MAX})")
                if self._health_fail_count >= self._HEALTH_FAIL_MAX:
                    raise RuntimeError(
                        f"Server did not respond {self._HEALTH_FAIL_MAX} times in a row.")
                return   # transient failure — try again next tick

            if new_hw_state != self._hw_state:
                self._hw_state = new_hw_state
                self._set_hw_operational(new_hw_state == "operational")
                host = self.host_input.text().strip()
                if new_hw_state == "operational":
                    # Hardware just recovered: push table settings now
                    try:
                        self._sync_hardware_settings()
                    except Exception:
                        pass
                    self.statusBar().showMessage(
                        f"Server: RUNNING  ({host}:{hvconfig.CMD_PORT})")
                else:
                    self.statusBar().showMessage(
                        f"Server: DEGRADED (waiting CAEN)  ({host}:{hvconfig.CMD_PORT})")

            # --- Poll telemetry ---
            data = self.client.poll_data()
            if not data:
                return

            self.table.blockSignals(True)  # Block signals while updating from monitor
            for row in range(self.table.rowCount()):
                ch = self.table.item(row, 0).data(Qt.UserRole)
                ch_update = next((d for d in data if d["slot"] == int(
                    ch.slot) and d["channel"] == int(ch.channel)), None)

                if ch_update:
                    vcur = ch_update["vmon"]
                    icur = ch_update["imon"]
                    status_val = ch_update["status"]

                    is_on = status_val & (1 << 0)
                    is_ramping = status_val & ((1 << 1) | (1 << 2))
                    is_ovc = status_val & (1 << 3)
                    is_trip = status_val & (1 << 8)

                    if is_ovc or is_trip:
                        state_str = "TRIP"
                        state_color = QColor("red")
                    elif is_ramping:
                        state_str = "RAMPING"
                        state_color = QColor("darkorange")
                    elif is_on:
                        state_str = "ON"
                        state_color = QColor("green")
                    else:
                        state_str = "OFF"
                        state_color = QColor("gray")

                    self.table.item(row, 5).setText(f"{vcur:.2f}")
                    self.table.item(row, 6).setText(f"{icur:.2f}")

                    status_item = self.table.item(row, 7)
                    status_item.setText(state_str)
                    status_item.setForeground(state_color)
            self.table.blockSignals(False)

        except RuntimeError as e:
            self.monitor_timer.stop()
            self.is_connected = False
            self.btn_connect.setText("Connect")
            self.statusBar().showMessage("Disconnected — server shut down")
            QMessageBox.critical(self, "Server Disconnected", str(e))
        except Exception as e:
            self.monitor_timer.stop()
            self.is_connected = False
            self.btn_connect.setText("Connect")
            self.statusBar().showMessage("Disconnected — connection lost")
            QMessageBox.critical(self, "Server Lost",
                                 f"Lost connection to server:\n{e}")

    def power_on_selected(self):
        if not self.is_connected:
            return
        selected_group = self.group_combo.currentText()
        try:
            for row in range(self.table.rowCount()):
                ch = self.table.item(row, 0).data(Qt.UserRole)
                if selected_group == "All" or ch.group == selected_group:
                    self.client.send_command(
                        "turn_on", int(ch.slot), int(ch.channel))
        except Exception as e:
            QMessageBox.warning(self, "Control Error",
                                f"Failed during group power ON:\n{e}")

    def power_off_selected(self):
        if not self.is_connected:
            return
        selected_group = self.group_combo.currentText()
        try:
            for row in range(self.table.rowCount()):
                ch = self.table.item(row, 0).data(Qt.UserRole)
                if selected_group == "All" or ch.group == selected_group:
                    self.client.send_command(
                        "turn_off", int(ch.slot), int(ch.channel))
        except Exception as e:
            QMessageBox.warning(self, "Control Error",
                                f"Failed during group power OFF:\n{e}")

    def _sync_hardware_settings(self):
        """
        Pushes current names, voltages, and calculated I-limits to the server.
        """
        for ch in self.all_channels:
            # Calculate current limit in uA
            i_set = ch.hv_set / ch.r_val
            i_limit = i_set * 1.1

            # Push to server
            self.client.send_command("set_name", int(
                ch.slot), int(ch.channel), ch.name)
            self.client.send_command("set_vset", int(
                ch.slot), int(ch.channel), float(ch.hv_set))
            self.client.send_command("set_iset", int(
                ch.slot), int(ch.channel), float(i_limit))

    def closeEvent(self, event):
        if self.is_connected:
            self.monitor_timer.stop()
            self.client.close()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = HVControlApp()
    window.show()
    sys.exit(app.exec())
