
import sys
import os
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
                               QHeaderView, QMessageBox, QLabel, QLineEdit, QFileDialog,
                               QComboBox, QAbstractItemView)
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor

# Import hardware control modules
from caenhv import CaenHV, N1470
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

        # Initialize hardware connection and state variables
        self.hv = CaenHV()
        self.all_channels = []
        self.is_connected = False

        self.setup_ui()

        # Set up the monitoring timer (1-second interval)
        self.monitor_timer = QTimer(self)
        self.monitor_timer.timeout.connect(self.update_monitor)

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # --- Top Row: Connection & Group Control Area ---
        conn_layout = QHBoxLayout()

        self.ip_input = QLineEdit("192.168.0.152")
        self.ip_input.setFixedWidth(120)

        self.btn_connect = QPushButton("Connect")
        self.btn_connect.clicked.connect(self.toggle_connection)

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

        conn_layout.addWidget(QLabel("IP Address:"))
        conn_layout.addWidget(self.ip_input)
        conn_layout.addWidget(self.btn_connect)
        conn_layout.addStretch()
        conn_layout.addWidget(QLabel("Group Filter:"))
        conn_layout.addWidget(self.group_combo)
        conn_layout.addWidget(self.btn_on)
        conn_layout.addWidget(self.btn_off)
        layout.addLayout(conn_layout)

        # --- Second Row: File Selection Area ---
        file_layout = QHBoxLayout()
        self.file_input = QLineEdit("hv.table")
        self.file_input.setReadOnly(True)
        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.clicked.connect(self.browse_file)

        file_layout.addWidget(QLabel("Table File:"))
        file_layout.addWidget(self.file_input)
        file_layout.addWidget(self.btn_browse)
        layout.addLayout(file_layout)

        # --- Monitoring Table ---
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Group", "Name", "Slot", "Ch", "Set (V)", "VMon (V)", "IMon (uA)", "Status"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        # Disable editing for all cells
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        # Connect double click signal for power toggle
        self.table.itemDoubleClicked.connect(self.on_item_double_clicked)

        layout.addWidget(self.table)

        self.load_data(show_error=False)

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open HV Table File", "", "Table Files (*.table *.txt);;All Files (*)"
        )
        if file_path:
            self.file_input.setText(file_path)
            self.load_data()

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
                self.table.setItem(row, col, item)

            self.table.item(row, 0).setData(Qt.UserRole, ch)

    def toggle_connection(self):
        if not self.is_connected:
            if not self.all_channels:
                QMessageBox.warning(
                    self, "Warning", "No channels loaded.\nPlease load a valid table file first.")
                return

            ip = self.ip_input.text()
            try:
                self.hv.init_system(N1470, ip)
                self.is_connected = True

                # Update UI state
                self.btn_connect.setText("Disconnect")
                self.btn_on.setEnabled(True)
                self.btn_off.setEnabled(True)

                # Trigger an immediate update for better UI responsiveness before starting the timer
                self.update_monitor()
                self.monitor_timer.start(1000)

                QMessageBox.information(self, "Success", f"Connected to {ip}")
            except Exception as e:
                QMessageBox.critical(
                    self, "Connection Error", f"Failed to connect:\n{e}")
        else:
            self.monitor_timer.stop()
            self.hv.deinit_system()
            self.is_connected = False
            self.btn_connect.setText("Connect")
            self.btn_on.setEnabled(False)
            self.btn_off.setEnabled(False)

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
                current_pw = self.hv.get_ch_param(
                    ch.slot, ch.channel, "Pw", "int")
                if current_pw == 1:
                    self.hv.turn_off(ch.slot, ch.channel)
                else:
                    self.hv.turn_on(ch.slot, ch.channel)
                # Force immediate update to reflect the command response in UI
                self.update_monitor()
            except Exception as e:
                QMessageBox.warning(self, "Control Error",
                                    f"Failed to toggle power:\n{e}")

    def update_monitor(self):
        if not self.is_connected:
            return

        for row in range(self.table.rowCount()):
            ch = self.table.item(row, 0).data(Qt.UserRole)
            try:
                vcur = self.hv.get_vmon(ch.slot, ch.channel)
                icur = self.hv.get_imon(ch.slot, ch.channel)

                status_val = self.hv.get_ch_param(
                    ch.slot, ch.channel, "Status", "int")

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
            except Exception:
                pass

    def power_on_selected(self):
        if not self.is_connected:
            return
        selected_group = self.group_combo.currentText()
        for row in range(self.table.rowCount()):
            ch = self.table.item(row, 0).data(Qt.UserRole)
            if selected_group == "All" or ch.group == selected_group:
                self.hv.turn_on(ch.slot, ch.channel)
        self.update_monitor()

    def power_off_selected(self):
        if not self.is_connected:
            return
        selected_group = self.group_combo.currentText()
        for row in range(self.table.rowCount()):
            ch = self.table.item(row, 0).data(Qt.UserRole)
            if selected_group == "All" or ch.group == selected_group:
                self.hv.turn_off(ch.slot, ch.channel)
        self.update_monitor()

    def closeEvent(self, event):
        if self.is_connected:
            self.monitor_timer.stop()
            self.hv.deinit_system()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = HVControlApp()
    window.show()
    sys.exit(app.exec())
