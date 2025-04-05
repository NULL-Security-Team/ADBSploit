import os
import subprocess
import sys
import random
import platform
import patoolib
import threading
import time
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QProgressBar, QFileDialog, QTextEdit,
                             QFrame, QGridLayout, QSplashScreen, QDockWidget, QToolBar, QListWidget,
                             QDialog, QComboBox, QScrollArea, QInputDialog)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QFont

class WorkerThread(QThread):
    result = pyqtSignal(str, str, bool)  # message, status, success
    output = pyqtSignal(str)

    def __init__(self, adb_path, command, success_msg, error_msg, output_to_text=False):
        super().__init__()
        self.adb_path = adb_path
        self.command = command
        self.success_msg = success_msg
        self.error_msg = error_msg
        self.output_to_text = output_to_text

    def run(self):
        try:
            if self.adb_path is None and "adb" not in self.command[0]:  # Skip ADB-specific commands if adb_path is None
                result = subprocess.run(self.command, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
            elif self.adb_path:
                if isinstance(self.command[0], list):
                    result = ""
                    for cmd in self.command:
                        cmd[0] = self.adb_path
                        result += subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
                else:
                    self.command[0] = self.adb_path
                    result = subprocess.run(self.command, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
            else:
                raise ValueError("ADB path not set and command requires ADB")
            self.result.emit(f"{self.success_msg}: {result}", self.success_msg, True)
            if self.output_to_text:
                self.output.emit(result)
        except subprocess.CalledProcessError as e:
            self.result.emit(f"{self.error_msg}: {e.stderr}", self.error_msg, False)
        except Exception as e:
            self.result.emit(f"Error: {str(e)}", "Error", False)

class MirrorThread(QThread):
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str, str)
    output_signal = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, adb_path, connected_ip):
        super().__init__()
        self.adb_path = adb_path
        self.connected_ip = connected_ip
        self.scrcpy_process = None

    def run(self):
        self.log_signal.emit("Starting screen mirroring thread...")
        report = ["Screen Mirroring Diagnostic Report:"]
        try:
            scrcpy_path = "scrcpy"
            if hasattr(sys, '_MEIPASS'):
                scrcpy_path = os.path.join(sys._MEIPASS, "scrcpy.exe")
            version_check = subprocess.run([scrcpy_path, "--version"], capture_output=True, text=True, encoding='utf-8', errors='replace')
            if version_check.returncode != 0:
                raise FileNotFoundError(f"scrcpy not found: {version_check.stderr}")
            report.append(f"scrcpy version: {version_check.stdout.strip()}")

            devices = subprocess.run([self.adb_path, "devices", "-l"], capture_output=True, text=True, encoding='utf-8', errors='replace')
            report.append(f"ADB devices: {devices.stdout}")
            if f"{self.connected_ip}:5555" not in devices.stdout or "unauthorized" in devices.stdout.lower():
                raise ValueError("Device not connected or unauthorized. Check USB debugging and authorization prompt.")

            screencap_test = subprocess.run([self.adb_path, "-s", f"{self.connected_ip}:5555", "shell", "screencap", "/sdcard/test.png"], capture_output=True, text=True, encoding='utf-8', errors='replace')
            if screencap_test.returncode != 0:
                report.append(f"Screen capture failed: {screencap_test.stderr}")
                report.append("Issue: Device may not support screen capture without root or additional setup.")
            else:
                report.append("Screen capture test: Success")

            logcat = subprocess.run([self.adb_path, "-s", f"{self.connected_ip}:5555", "logcat", "-d"], capture_output=True, text=True, encoding='utf-8', errors='replace')
            scrcpy_log = "\n".join(line for line in logcat.stdout.splitlines() if "scrcpy" in line.lower())
            if scrcpy_log:
                report.append(f"Logcat (pre-run, scrcpy-related):\n{scrcpy_log}")
                if "avc: denied" in scrcpy_log.lower():
                    report.append("Warning: SELinux denials detected.")
                if "killed" in scrcpy_log.lower():
                    report.append("Warning: Previous scrcpy server was killed.")

            cmd = [scrcpy_path, "-s", f"{self.connected_ip}:5555", "--verbosity=debug"]
            self.log_signal.emit(f"Launching scrcpy with command: {' '.join(cmd)}")
            self.scrcpy_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
            time.sleep(2)
            if self.scrcpy_process.poll() is None:
                self.log_signal.emit("Screen mirroring started successfully")
                self.status_signal.emit("Mirroring started", "green")
                report.append("Result: Success (scrcpy running in background)")
            else:
                self.log_signal.emit("Screen mirroring failed to start")
                self.status_signal.emit("Error: Mirroring failed!", "red")
                report.append(f"scrcpy failed to start (exit code: {self.scrcpy_process.returncode})")
                report.append("Result: Failed - scrcpy did not launch properly")
        except FileNotFoundError as e:
            self.log_signal.emit(f"scrcpy not installed: {str(e)}")
            self.status_signal.emit("Error: scrcpy not installed!", "red")
            report.append(f"Error: {str(e)}. Install scrcpy from https://github.com/Genymobile/scrcpy/releases")
        except ValueError as e:
            self.log_signal.emit(f"Device connection issue: {str(e)}")
            self.status_signal.emit("Error: Connection issue!", "red")
            report.append(f"Error: {str(e)}")
        except Exception as e:
            self.log_signal.emit(f"Unexpected error: {str(e)}")
            self.status_signal.emit("Error: Unknown failure!", "red")
            report.append(f"Error: Unexpected failure - {str(e)}")
        
        self.output_signal.emit("\n".join(report))
        self.finished.emit()

class PleaseWaitDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Please Wait")
        self.setModal(True)
        self.setFixedSize(300, 100)
        layout = QVBoxLayout()
        self.label = QLabel("Initializing screen mirroring...", self)
        layout.addWidget(self.label)
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0)
        layout.addWidget(self.progress)
        self.setLayout(layout)

class ScreenshotViewer(QDialog):
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Screenshot Viewer")
        layout = QVBoxLayout()
        scroll = QScrollArea()
        image_label = QLabel()
        pixmap = QPixmap(image_path)
        image_label.setPixmap(pixmap.scaled(800, 600, Qt.AspectRatioMode.KeepAspectRatio))
        scroll.setWidget(image_label)
        layout.addWidget(scroll)
        self.setLayout(layout)
        self.resize(800, 600)

class ADBSploitApp(QMainWindow):
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str, str)
    output_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ADBSploit")
        self.setGeometry(100, 100, 800, 600)

        splash_pix = QPixmap(300, 150)
        splash_pix.fill(Qt.GlobalColor.darkGray)
        self.splash = QSplashScreen(splash_pix)
        self.splash.showMessage("Initializing...", Qt.AlignmentFlag.AlignCenter, Qt.GlobalColor.white)
        self.splash.show()
        QApplication.processEvents()

        self.log_entries = []
        self.device_name = ""
        self.adb_path = None
        self.connected_ip = ""
        self.output_dir = "output"
        os.makedirs(self.output_dir, exist_ok=True)
        self.scrcpy_process = None
        self.mirror_thread = None

        self.logo_designs = [
            r'''
   ___ ____________  ___________ _     _____ _____ _____ 
   / _ \|  _  \ ___ \/  ___| ___ \ |   |  _  |_   _|_   _|
/ /_\ \ | | | |_/ /\ `--.| |_/ / |   | | | | | |   | |  
|  _  | | | | ___ \ `--. \  __/| |   | | | | | |   | |  
| | | | |/ /| |_/ //\__/ / |   | |___\ \_/ /_| |_  | |  
 \_| |_/___/ \____/ \____/\_|   \_____/\___/ \___/  \_/  
                                                        ''',
            r''' 
⠀⠀⠀⠀⢀⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⡀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠙⢷⣤⣤⣴⣶⣶⣦⣤⣤⡾⠋⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⣴⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣦⠀⠀⠀⠀⠀
⠀⠀⠀⠀⣼⣿⣿⣉⣹⣿⣿⣿⣿⣏⣉⣿⣿⣧⠀⠀⠀⠀
⠀⠀⠀⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⠀⠀⠀
⣠⣄⠀⢠⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⡄⠀⣠⣄
⣿⣿⡇⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⢸⣿⣿
⣿⣿⡇⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⢸⣿⣿
⣿⣿⡇⢸⣿⣿ ADBSPLOIT  ⣿⣿⡇⢸⣿⣿
⣿⣿⡇⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⢸⣿⣿
⠻⠟⠁⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⠈⠻⠟
⠀⠀⠀⠀⠉⠉⣿⣿⣿⡏⠉⠉⢹⣿⣿⣿⠉⠉⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⣿⣿⣿⡇⠀⠀⢸⣿⣿⣿⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⣿⣿⣿⡇⠀⠀⢸⣿⣿⣿⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠈⠉⠉⠀⠀⠀⠀⠉⠉⠁⠀⠀⠀⠀⠀⠀''',
            r'''

⠀⠀⠀⠀⠀⠀⠀⣀⣤⣶⣿⠷⠾⠛⠛⠛⠛⠷⠶⢶⣶⣤⣄⡀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⣀⣴⡾⠛⠉⠁⠀⣰⡶⠶⠶⠶⠶⠶⣶⡄⠀⠉⠛⠿⣷⣄⡀⠀⠀⠀
⠀⠀⣠⣾⠟⠁⠀⠀⠀⠀⠀⢸⡇⠀⠀⠀⠀⠀⣼⠃⠀⠀⠀⠀⠈⠛⢿⣦⡀⠀
⢠⣼⠟⠁⠀⠀⠀⠀⣠⣴⣶⣿⡇⠀⠀⠀⠀⠀⣿⣷⣦⣄⠀⠀⠀⠀⠀⠙⣧⡀
⣿⡇⠀⠀⠀⢀⣴⣾⣿⣿⣿⣿⣇⠀⠀⠀⠀⠸⣿⣿⣿⣿⣿⣦⡀⠀⠀⠀⢈⣷
⣿⣿⣦⡀⣠⣾⣿⣿⣿⡿⠟⢻⣿⠀⠀⠀⠀⢠⣿⠻⢿⣿⣿⣿⣿⣆⣀⣠⣾⣿
⠉⠻⣿⣿⣿⣿⣽⡿⠋⠀⠀⠸⣿⠀⠀⠀⠀⢸⡿⠀⠀⠉⠻⣿⣿⣿⣿⣿⠟⠁
⠀⠀⠈⠙⠛⣿⣿⠀⠀⠀⠀⢀⣿⠀⠀⠀⠀⢸⣇⠀⠀⠀⠀⣹⣿⡟⠋⠁⠀⠀
⠀⠀⠀⠀⠀⢿⣿⣷⣄⣀⣴⣿⣿⣤⣤⣤⣤⣼⣿⣷⣀⣀⣾⣿⣿⠇⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠈⠻⢿⣿⣿⣿⣿⣿⠟⠛⠛⠻⣿⣿⣿⣿⣿⡿⠛⠉⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠉⠉⠁⣿⡇⠀⠀⠀⠀⢸⣿⡏⠙⠋⠁⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣷⣄⠀⠀⣀⣾⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⢿⣿⣿⣿⣿⣿⣏⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀

⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀ADBSploit⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀''',
        ]

        self.log_signal.connect(self._log)
        self.status_signal.connect(self._set_status)
        self.output_signal.connect(self._set_output)

        self.threads = []
        self.log_dock = None

        self.init_thread = WorkerThread(None, ["echo", "Initializing"], "Initialization started", "Initialization failed")
        self.init_thread.finished.connect(self.setup_ui)
        self.init_thread.start()
        self.threads.append(self.init_thread)

    def closeEvent(self, event):
        if self.scrcpy_process and self.scrcpy_process.poll() is None:
            self.scrcpy_process.terminate()
            self.scrcpy_process.wait()
            self.log_signal.emit("scrcpy process terminated on app close")
        for thread in self.threads:
            if thread.isRunning():
                thread.quit()
                thread.wait()
        event.accept()

    def setup_ui(self):
        self.set_icon()
        self.create_widgets()
        self.check_adb()
        self.create_log_dock()
        self.update_log_display()
        self.splash.finish(self)
        self.show()

    def set_icon(self):
        try:
            if hasattr(sys, '_MEIPASS'):
                icon_path = os.path.join(sys._MEIPASS, "app_icon.ico")
            else:
                icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_icon.ico")
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except Exception as e:
            self.log_signal.emit(f"Could not load icon: {e}")

    def check_adb(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        try:
            result = subprocess.run(["adb", "--version"], capture_output=True, check=True, text=True, encoding='utf-8', errors='replace')
            self.adb_path = "adb"
            self.log_signal.emit(f"Using system-wide ADB: {result.stdout}")
            devices = subprocess.run(["adb", "devices"], capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
            if "device" in devices.splitlines()[1:]:
                subprocess.run([self.adb_path, "tcpip", "5555"], capture_output=True, check=True, text=True, encoding='utf-8', errors='replace')
                self.log_signal.emit("TCP/IP mode enabled")
            self.check_device_authorization(devices)
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        rar_path = os.path.join(current_dir, "adb.rar")
        if os.path.exists(rar_path):
            try:
                extract_dir = os.path.join(current_dir, "platform-tools")
                patoolib.extract_archive(rar_path, outdir=extract_dir)
                self.adb_path = os.path.join(extract_dir, "adb.exe")
                result = subprocess.run([self.adb_path, "--version"], capture_output=True, check=True, text=True, encoding='utf-8', errors='replace')
                self.log_signal.emit(f"ADB extracted from adb.rar: {result.stdout}")
                devices = subprocess.run([self.adb_path, "devices"], capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
                if "device" in devices.splitlines()[1:]:
                    subprocess.run([self.adb_path, "tcpip", "5555"], capture_output=True, check=True, text=True, encoding='utf-8', errors='replace')
                    self.log_signal.emit("TCP/IP mode enabled")
                self.check_device_authorization(devices)
                return
            except Exception as e:
                self.log_signal.emit(f"Failed to extract or use adb.rar: {e}")
                return

        self.log_signal.emit("ADB not found. Please place adb.exe in the script directory or install it manually.")

    def check_device_authorization(self, devices_output):
        if "unauthorized" in devices_output.lower():
            self.log_signal.emit("Device unauthorized. Please check your device for an authorization prompt or revoke USB debugging authorizations in Developer Options.")
        self.update_device_dropdown(devices_output)

    def _log(self, message):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.log_entries.append(f"{timestamp} - {message}")
        self.update_log_display()

    def update_log_display(self):
        if hasattr(self, 'log_text'):
            self.log_text.setPlainText("\n".join(self.log_entries))
            self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def clear_log(self):
        self.log_entries.clear()
        self.update_log_display()

    def save_log(self):
        file_name, _ = QFileDialog.getSaveFileName(self, "Save Log", "", "Text Files (*.txt);;All Files (*)")
        if file_name:
            with open(file_name, 'w', encoding='utf-8') as f:
                f.write("\n".join(self.log_entries))
            self.log_signal.emit(f"Log saved to {file_name}")

    def _set_status(self, message, color):
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {color}")

    def _set_output(self, text):
        self.output_text.setPlainText(text)
        self.output_text.verticalScrollBar().setValue(self.output_text.verticalScrollBar().maximum())

    def browse_file(self, entry):
        file_name, _ = QFileDialog.getOpenFileName(self, "Select File")
        if file_name:
            entry.setText(file_name)

    def browse_save(self, entry):
        file_name, _ = QFileDialog.getSaveFileName(self, "Save File As")
        if file_name:
            entry.setText(file_name)

    def connect_device(self):
        self.device_name = self.connect_entry.text().strip()
        if not self.device_name:
            self.status_signal.emit("Error: Enter a device IP!", "red")
            return
        if not self.adb_path:
            self.status_signal.emit("Error: ADB not configured!", "red")
            return
        threading.Thread(target=self._connect_device_thread, daemon=True).start()

    def _connect_device_thread(self):
        try:
            result = subprocess.run([self.adb_path, "connect", f"{self.device_name}:5555"], check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.log_signal.emit(f"Connected to {self.device_name}: {result.stdout}")
            self.status_signal.emit(f"Connected to {self.device_name}", "green")
            self.connected_ip = self.device_name
            self.connection_status.setText(f"Connected to: {self.connected_ip}")
            devices = subprocess.run([self.adb_path, "devices"], capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
            self.check_device_authorization(devices)
        except subprocess.CalledProcessError as e:
            self.log_signal.emit(f"Connection failed: {e.stderr}")
            self.status_signal.emit("Error: Connection failed!", "red")

    def disconnect_device(self):
        if not self.adb_path or not self.connected_ip:
            self.status_signal.emit("Error: No device connected!", "red")
            return
        threading.Thread(target=self._disconnect_device_thread, daemon=True).start()

    def _disconnect_device_thread(self):
        try:
            result = subprocess.run([self.adb_path, "disconnect", self.connected_ip], check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.log_signal.emit(f"Disconnected from {self.connected_ip}: {result.stdout}")
            self.status_signal.emit("Disconnected", "green")
            self.connected_ip = ""
            self.connection_status.setText("Connected to: None")
            devices = subprocess.run([self.adb_path, "devices"], capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
            self.update_device_dropdown(devices)
        except subprocess.CalledProcessError as e:
            self.log_signal.emit(f"Disconnect failed: {e.stderr}")
            self.status_signal.emit("Error: Disconnect failed!", "red")

    def open_shell(self):
        if not self.adb_path or not self.connected_ip:
            self.status_signal.emit("Error: No device connected!", "red")
            self.log_signal.emit("Shell access failed: No device connected")
            return
        try:
            os_name = platform.system()
            if os_name == "Windows":
                shell_cmd = f'cmd.exe /K "{self.adb_path}" -s {self.connected_ip} shell'
                subprocess.Popen(shell_cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
            elif os_name == "Linux":
                shell_cmd = [self.adb_path, "-s", self.connected_ip, "shell"]
                subprocess.Popen(["gnome-terminal", "--", "bash", "-c", f"{' '.join(shell_cmd)}; exec bash"])
            else:
                self.log_signal.emit(f"Shell access not supported on {os_name}")
                self.status_signal.emit("Error: OS not supported!", "red")
                return
            self.log_signal.emit(f"Opened shell for {self.connected_ip}")
            self.status_signal.emit("Shell opened", "green")
        except Exception as e:
            self.log_signal.emit(f"Failed to open shell: {str(e)}")
            self.status_signal.emit("Error: Shell failed!", "red")

    def run_command(self, command, success_msg, error_msg, output_to_text=False):
        if not self.adb_path and "adb" in command[0]:
            self.status_signal.emit("Error: ADB not configured!", "red")
            return
        self.status_signal.emit("Processing...", "yellow")
        self.progress.setVisible(True)
        thread = WorkerThread(self.adb_path, command, success_msg, error_msg, output_to_text)
        thread.result.connect(self._handle_command_result)
        thread.output.connect(self._set_output)
        thread.finished.connect(lambda: self.progress.setVisible(False))
        thread.start()
        self.threads.append(thread)

    def run_custom_command(self):
        cmd = self.custom_cmd_entry.text().strip()
        if not cmd:
            self.status_signal.emit("Error: Enter a command!", "red")
            return
        self.run_command(["adb", "-s", self.device_name, "shell", cmd], "Command executed", "Command failed", True)

    def _handle_command_result(self, message, status, success):
        self.log_signal.emit(message)
        self.status_signal.emit(status, "green" if success else "red")

    def start_screen_mirror(self):
        if not self.adb_path or not self.connected_ip:
            self.status_signal.emit("Error: No device connected!", "red")
            self.log_signal.emit("Screen mirroring failed: No device connected")
            self.output_signal.emit("Screen Mirroring Failed: No device connected.")
            return

        wait_dialog = PleaseWaitDialog(self)
        wait_dialog.show()

        self.mirror_thread = MirrorThread(self.adb_path, self.connected_ip)
        self.mirror_thread.log_signal.connect(self.log_signal)
        self.mirror_thread.status_signal.connect(self.status_signal)
        self.mirror_thread.output_signal.connect(self._set_output)
        self.mirror_thread.finished.connect(wait_dialog.close)
        self.mirror_thread.start()
        self.scrcpy_process = self.mirror_thread.scrcpy_process
        self.threads.append(self.mirror_thread)
        self.log_signal.emit("Screen mirroring thread started")

    def stop_screen_mirror(self):
        if self.scrcpy_process and self.scrcpy_process.poll() is None:
            self.scrcpy_process.terminate()
            self.scrcpy_process.wait()
            self.log_signal.emit("Screen mirroring stopped")
            self.status_signal.emit("Mirroring stopped", "green")
        else:
            self.status_signal.emit("No mirroring active", "yellow")

    def update_device_dropdown(self, devices_output):
        self.device_dropdown.clear()
        devices = [line.split()[0] for line in devices_output.splitlines()[1:] if line.strip() and "device" in line]
        self.device_dropdown.addItems(devices if devices else ["No devices detected"])
        if self.connected_ip in devices:
            self.device_dropdown.setCurrentText(self.connected_ip)

    def select_device(self, device):
        self.connected_ip = device
        self.device_name = device
        self.connection_status.setText(f"Connected to: {self.connected_ip}")
        self.log_signal.emit(f"Selected device: {self.connected_ip}")

    def toggle_wifi_adb(self):
        if not self.adb_path or not self.connected_ip:
            self.status_signal.emit("Error: No device connected!", "red")
            return
        self.run_command([self.adb_path, "-s", self.connected_ip, "tcpip", "5555"], "Wi-Fi ADB enabled", "Failed to enable Wi-Fi ADB")

    def check_root(self):
        if not self.adb_path or not self.connected_ip:
            self.status_signal.emit("Error: No device connected!", "red")
            return
        self.run_command(["adb", "-s", self.connected_ip, "shell", "su", "-c", "whoami"], "Root check: root", "Root check: not rooted", True)

    def open_front_camera(self):
        if not self.adb_path or not self.connected_ip:
            self.status_signal.emit("Error: No device connected!", "red")
            self.log_signal.emit("Camera open failed: No device connected")
            return
        self.run_command(
            ["adb", "-s", self.device_name, "shell", "am", "start", "-a", "android.media.action.IMAGE_CAPTURE", "--ei", "android.intent.extras.CAMERA_FACING", "1"],
            "Front camera opened", "Failed to open front camera"
        )

    def record_audio(self):
        if not self.adb_path or not self.connected_ip:
            self.status_signal.emit("Error: No device connected!", "red")
            self.log_signal.emit("Audio recording failed: No device connected")
            return
        duration = self.audio_time.text().strip() or "10"
        output_file = os.path.join(self.output_dir, f"audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav")
        self.run_command(
            [["adb", "-s", self.device_name, "shell", "arecord", "-d", duration, "-f", "cd", "/sdcard/audio.wav"],
             ["adb", "-s", self.device_name, "pull", "/sdcard/audio.wav", output_file]],
            f"Audio recorded ({duration}s)", "Audio recording failed - device may not support audio recording via ADB without root or custom app"
        )

    def get_gps_info(self):
        if not self.adb_path or not self.connected_ip:
            self.status_signal.emit("Error: No device connected!", "red")
            self.log_signal.emit("GPS info failed: No device connected")
            return
        self.run_command(
            ["adb", "-s", self.device_name, "shell", "dumpsys", "location"],
            "GPS info retrieved", "Failed to get GPS info", True
        )

    def update_screenshot_gallery(self):
        self.screenshot_list.clear()
        for file in os.listdir(self.output_dir):
            if file.startswith("screenshot_") and file.endswith(".png"):
                self.screenshot_list.addItem(file)

    def show_screenshot(self, item):
        file_path = os.path.join(self.output_dir, item.text())
        viewer = ScreenshotViewer(file_path, self)
        viewer.exec()

    def flash_partition(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Select Image File", "", "Image Files (*.img);;All Files (*)")
        if file_name:
            partition, ok = QInputDialog.getText(self, "Partition Name", "Enter partition name (e.g., boot, system):")
            if ok and partition:
                self.run_command(
                    ["fastboot", "flash", partition, file_name],
                    f"Partition {partition} flashed", "Failed to flash partition"
                )

    def create_log_dock(self):
        self.log_dock = QDockWidget("Log", self)
        self.log_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)

        log_toolbar = QToolBar()
        clear_action = log_toolbar.addAction("Clear", self.clear_log)
        clear_action.setToolTip("Clear the log display")
        save_action = log_toolbar.addAction("Save", self.save_log)
        save_action.setToolTip("Save log to a file")
        log_layout.addWidget(log_toolbar)

        self.log_dock.setWidget(log_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.log_dock)

    def show_log_dock(self):
        if self.log_dock is None:
            self.create_log_dock()
        elif not self.log_dock.isVisible():
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.log_dock)
            self.log_dock.show()
        self.update_log_display()

    def create_widgets(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)

        tabs = QTabWidget()
        tabs.setTabPosition(QTabWidget.TabPosition.West)
        main_layout.addWidget(tabs)

        # Connect Tab
        connect_tab = QWidget()
        connect_layout = QVBoxLayout(connect_tab)
        banner_label = QLabel(random.choice(self.logo_designs))
        banner_label.setFont(QFont("Courier", 8))
        banner_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        connect_layout.addWidget(banner_label)
        connect_frame = QWidget()
        connect_frame_layout = QVBoxLayout(connect_frame)
        connect_frame_layout.setSpacing(5)

        ip_frame = QHBoxLayout()
        ip_label = QLabel("IP:")
        ip_label.setFixedWidth(30)
        ip_frame.addWidget(ip_label)
        self.connect_entry = QLineEdit()
        self.connect_entry.setToolTip("Enter device IP (e.g., 192.168.1.100)")
        self.connect_entry.setMaximumWidth(150)
        ip_frame.addWidget(self.connect_entry)
        connect_btn = QPushButton("Connect", clicked=self.connect_device)
        connect_btn.setToolTip("Connect to device via IP")
        ip_frame.addWidget(connect_btn)
        disconnect_btn = QPushButton("Disconnect", clicked=self.disconnect_device)
        disconnect_btn.setToolTip("Disconnect from current device")
        ip_frame.addWidget(disconnect_btn)
        connect_frame_layout.addLayout(ip_frame)

        device_frame = QHBoxLayout()
        device_label = QLabel("Select Device:")
        device_frame.addWidget(device_label)
        self.device_dropdown = QComboBox()
        self.device_dropdown.setToolTip("Select a connected device")
        self.device_dropdown.currentTextChanged.connect(self.select_device)
        device_frame.addWidget(self.device_dropdown)
        wifi_btn = QPushButton("Enable Wi-Fi ADB", clicked=self.toggle_wifi_adb)
        wifi_btn.setToolTip("Enable ADB over Wi-Fi")
        device_frame.addWidget(wifi_btn)
        connect_frame_layout.addLayout(device_frame)

        connect_layout.addWidget(connect_frame)
        connect_layout.addStretch()
        tabs.addTab(connect_tab, "🔗")
        tabs.setTabToolTip(0, "Connect to devices via IP or USB")

        # Device Tab
        device_tab = QWidget()
        device_layout = QVBoxLayout(device_tab)
        device_grid = QGridLayout()
        device_grid.setHorizontalSpacing(5)
        device_grid.addWidget(QLabel("Cmd:"), 0, 0)
        self.custom_cmd_entry = QLineEdit()
        self.custom_cmd_entry.setToolTip("Enter custom ADB shell command")
        self.custom_cmd_entry.setMaximumWidth(150)
        device_grid.addWidget(self.custom_cmd_entry, 0, 1)
        run_cmd_btn = QPushButton("Run", clicked=self.run_custom_command)
        run_cmd_btn.setToolTip("Execute custom command")
        device_grid.addWidget(run_cmd_btn, 0, 2)
        devices_btn = QPushButton("Devices", clicked=lambda: self.run_command(
            ["adb", "devices", "-l"], "Devices listed", "Failed to list devices", True))
        devices_btn.setToolTip("List connected devices")
        device_grid.addWidget(devices_btn, 1, 0)
        shell_btn = QPushButton("Shell", clicked=self.open_shell)
        shell_btn.setToolTip("Open ADB shell terminal")
        device_grid.addWidget(shell_btn, 1, 1)
        restart_btn = QPushButton("Restart", clicked=lambda: self.run_command(
            [["adb", "kill-server"], ["adb", "start-server"]], "Server restarted", "Server restart failed"))
        restart_btn.setToolTip("Restart ADB server")
        device_grid.addWidget(restart_btn, 1, 2)
        off_btn = QPushButton("Off", clicked=lambda: self.run_command(
            ["adb", "-s", self.device_name, "reboot"], "Device turned off", "Failed to turn off"))
        off_btn.setToolTip("Power off device")
        device_grid.addWidget(off_btn, 2, 0)
        battery_btn = QPushButton("Battery", clicked=lambda: self.run_command(
            ["adb", "-s", self.device_name, "shell", "dumpsys", "battery"], "Battery status retrieved", "Failed to get battery status", True))
        battery_btn.setToolTip("Get battery status")
        device_grid.addWidget(battery_btn, 2, 1)
        dump_btn = QPushButton("Dump", clicked=lambda: self.run_command(
            [["adb", "-s", self.device_name, "shell", "dumpsys", "meminfo"],
             ["adb", "-s", self.device_name, "shell", "cat", "/proc/meminfo"]],
            "System info dumped", "Failed to dump system info", True))
        dump_btn.setToolTip("Dump system memory info")
        device_grid.addWidget(dump_btn, 2, 2)
        recovery_btn = QPushButton("Recovery", clicked=lambda: self.run_command(
            ["adb", "-s", self.device_name, "reboot", "recovery"], "Rebooted to recovery", "Failed to reboot to recovery"))
        recovery_btn.setToolTip("Reboot to recovery mode")
        device_grid.addWidget(recovery_btn, 3, 0)
        bootloader_btn = QPushButton("Bootloader", clicked=lambda: self.run_command(
            ["adb", "-s", self.device_name, "reboot", "bootloader"], "Rebooted to bootloader", "Failed to reboot to bootloader"))
        bootloader_btn.setToolTip("Reboot to bootloader/fastboot mode")
        device_grid.addWidget(bootloader_btn, 3, 1)
        get_ip_btn = QPushButton("Get IP", clicked=lambda: self.run_command(
            ["adb", "-s", self.device_name, "shell", "ip", "addr"], "IP retrieved", "Failed to get IP", True))
        get_ip_btn.setToolTip("Get device IP address")
        device_grid.addWidget(get_ip_btn, 3, 2)
        logcat_btn = QPushButton("Logcat", clicked=lambda: self.run_command(
            ["adb", "-s", self.device_name, "logcat", "-d"], "Logcat retrieved", "Failed to get logcat", True))
        logcat_btn.setToolTip("Dump device logs")
        device_grid.addWidget(logcat_btn, 4, 0)
        vol_up_btn = QPushButton("Vol Up", clicked=lambda: self.run_command(
            ["adb", "-s", self.device_name, "shell", "input", "keyevent", "24"], "Volume up sent", "Failed to send volume up"))
        vol_up_btn.setToolTip("Increase volume")
        device_grid.addWidget(vol_up_btn, 4, 1)
        vol_down_btn = QPushButton("Vol Down", clicked=lambda: self.run_command(
            ["adb", "-s", self.device_name, "shell", "input", "keyevent", "25"], "Volume down sent", "Failed to send volume down"))
        vol_down_btn.setToolTip("Decrease volume")
        device_grid.addWidget(vol_down_btn, 4, 2)
        power_btn = QPushButton("Key Power", clicked=lambda: self.run_command(
            ["adb", "-s", self.device_name, "shell", "input", "keyevent", "26"], "Power key sent", "Failed to send power key"))
        power_btn.setToolTip("Simulate power button")
        device_grid.addWidget(power_btn, 5, 0)
        dev_info_btn = QPushButton("Device Info", clicked=lambda: self.run_command(
            ["adb", "-s", self.device_name, "shell", "cat", "/system/build.prop"], "Device info retrieved", "Failed to get device info", True))
        dev_info_btn.setToolTip("Get device properties")
        device_grid.addWidget(dev_info_btn, 5, 1)
        root_btn = QPushButton("Check Root", clicked=self.check_root)
        root_btn.setToolTip("Check if device is rooted")
        device_grid.addWidget(root_btn, 5, 2)
        device_layout.addLayout(device_grid)
        device_layout.addStretch()
        tabs.addTab(device_tab, "📱")
        tabs.setTabToolTip(1, "Control and manage device settings")

        # Apps Tab
        apps_tab = QWidget()
        apps_layout = QVBoxLayout(apps_tab)
        apps_grid = QGridLayout()
        apps_grid.setHorizontalSpacing(5)
        apps_grid.addWidget(QLabel("APK:"), 0, 0)
        self.apk_entry = QLineEdit()
        self.apk_entry.setToolTip("Path to APK file")
        self.apk_entry.setMaximumWidth(150)
        apps_grid.addWidget(self.apk_entry, 0, 1)
        apk_browse_btn = QPushButton("Browse", clicked=lambda: self.browse_file(self.apk_entry))
        apk_browse_btn.setToolTip("Select APK file")
        apps_grid.addWidget(apk_browse_btn, 0, 2)
        install_btn = QPushButton("Install", clicked=lambda: self.run_command(
            ["adb", "-s", self.device_name, "install", self.apk_entry.text()], "APK installed", "APK install failed"))
        install_btn.setToolTip("Install APK on device")
        apps_grid.addWidget(install_btn, 0, 3)
        apps_grid.addWidget(QLabel("Pkg:"), 1, 0)
        self.package_entry = QLineEdit()
        self.package_entry.setToolTip("e.g., com.snapchat.android")
        self.package_entry.setMaximumWidth(150)
        apps_grid.addWidget(self.package_entry, 1, 1)
        uninstall_btn = QPushButton("Uninstall", clicked=lambda: self.run_command(
            ["adb", "-s", self.device_name, "uninstall", self.package_entry.text()], "App uninstalled", "Uninstall failed"))
        uninstall_btn.setToolTip("Uninstall app by package name")
        apps_grid.addWidget(uninstall_btn, 1, 2)
        run_app_btn = QPushButton("Run", clicked=lambda: self.run_command(
            ["adb", "-s", self.device_name, "shell", "monkey", "-p", self.package_entry.text(), "-v", "500"], "App launched", "App launch failed"))
        run_app_btn.setToolTip("Launch app by package name")
        apps_grid.addWidget(run_app_btn, 1, 3)
        list_apps_btn = QPushButton("List", clicked=lambda: self.run_command(
            ["adb", "-s", self.device_name, "shell", "pm", "list", "packages", "-f"], "Apps listed", "Failed to list apps", True))
        list_apps_btn.setToolTip("List installed apps")
        apps_grid.addWidget(list_apps_btn, 2, 0)
        perms_btn = QPushButton("Permissions", clicked=lambda: self.run_command(
            ["adb", "-s", self.device_name, "shell", "dumpsys", "package", self.package_entry.text()], "Permissions listed", "Failed to list permissions", True))
        perms_btn.setToolTip("List app permissions")
        apps_grid.addWidget(perms_btn, 2, 1)
        apps_layout.addLayout(apps_grid)
        apps_layout.addStretch()
        tabs.addTab(apps_tab, "📲")
        tabs.setTabToolTip(2, "Manage and install applications")

        # Media Tab
        media_tab = QWidget()
        media_layout = QVBoxLayout(media_tab)
        media_grid = QGridLayout()
        media_grid.setHorizontalSpacing(5)
        media_grid.addWidget(QLabel("Save:"), 0, 0)
        self.media_entry = QLineEdit()
        self.media_entry.setToolTip("Save location (default: output folder)")
        self.media_entry.setMaximumWidth(150)
        media_grid.addWidget(self.media_entry, 0, 1)
        media_browse_btn = QPushButton("Browse", clicked=lambda: self.browse_save(self.media_entry))
        media_browse_btn.setToolTip("Select save location")
        media_grid.addWidget(media_browse_btn, 0, 2)
        screenshot_btn = QPushButton("Screenshot", clicked=lambda: self.run_command(
            [["adb", "-s", self.device_name, "shell", "screencap", "/sdcard/screen.png"],
             ["adb", "-s", self.device_name, "pull", "/sdcard/screen.png", self.media_entry.text() or os.path.join(self.output_dir, f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")]],
            "Screenshot saved", "Screenshot failed") and self.update_screenshot_gallery())
        screenshot_btn.setToolTip("Capture device screenshot")
        media_grid.addWidget(screenshot_btn, 0, 3)
        media_grid.addWidget(QLabel("Vid Time(s):"), 1, 0)
        self.record_time = QLineEdit("180")
        self.record_time.setToolTip("Video recording duration in seconds (max 180)")
        self.record_time.setMaximumWidth(50)
        media_grid.addWidget(self.record_time, 1, 1)
        record_video_btn = QPushButton("Record Video", clicked=lambda: self.run_command(
            [["adb", "-s", self.device_name, "shell", "screenrecord", f"--time-limit={self.record_time.text()}", "/sdcard/demo.mp4"],
             ["adb", "-s", self.device_name, "pull", "/sdcard/demo.mp4", self.media_entry.text() or os.path.join(self.output_dir, f"recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")]],
            f"Video recorded ({self.record_time.text()}s)", "Video recording failed"))
        record_video_btn.setToolTip("Record device screen")
        media_grid.addWidget(record_video_btn, 1, 3)
        media_grid.addWidget(QLabel("Aud Time(s):"), 2, 0)
        self.audio_time = QLineEdit("10")
        self.audio_time.setToolTip("Audio recording duration in seconds")
        self.audio_time.setMaximumWidth(50)
        media_grid.addWidget(self.audio_time, 2, 1)
        record_audio_btn = QPushButton("Record Audio", clicked=self.record_audio)
        record_audio_btn.setToolTip("Record audio from microphone")
        media_grid.addWidget(record_audio_btn, 2, 3)
        mirror_btn = QPushButton("Mirror", clicked=self.start_screen_mirror)
        mirror_btn.setToolTip("Start screen mirroring (requires scrcpy)")
        media_grid.addWidget(mirror_btn, 3, 0)
        stop_mirror_btn = QPushButton("Stop Mirror", clicked=self.stop_screen_mirror)
        stop_mirror_btn.setToolTip("Stop screen mirroring")
        media_grid.addWidget(stop_mirror_btn, 3, 1)
        front_cam_btn = QPushButton("Front Cam", clicked=self.open_front_camera)
        front_cam_btn.setToolTip("Open front camera if available")
        media_grid.addWidget(front_cam_btn, 3, 2)
        gps_btn = QPushButton("GPS Info", clicked=self.get_gps_info)
        gps_btn.setToolTip("Get GPS location data")
        media_grid.addWidget(gps_btn, 3, 3)
        self.screenshot_list = QListWidget()
        self.screenshot_list.setToolTip("Recent screenshots - click to view")
        self.screenshot_list.itemClicked.connect(self.show_screenshot)
        media_grid.addWidget(self.screenshot_list, 4, 0, 1, 4)
        self.update_screenshot_gallery()
        media_layout.addLayout(media_grid)
        media_layout.addStretch()
        tabs.addTab(media_tab, "📸")
        tabs.setTabToolTip(3, "Capture media and mirror screen")

        # File Tab
        file_tab = QWidget()
        file_layout = QVBoxLayout(file_tab)
        file_grid = QGridLayout()
        file_grid.setHorizontalSpacing(5)
        file_grid.addWidget(QLabel("Path:"), 0, 0)
        self.file_entry = QLineEdit()
        self.file_entry.setToolTip("e.g., /sdcard/file.txt")
        self.file_entry.setMaximumWidth(150)
        file_grid.addWidget(self.file_entry, 0, 1)
        list_files_btn = QPushButton("List", clicked=lambda: self.run_command(
            ["adb", "-s", self.device_name, "shell", "ls", self.file_entry.text() or "/sdcard"], "Files listed", "Failed to list files", True))
        list_files_btn.setToolTip("List files in directory")
        file_grid.addWidget(list_files_btn, 0, 2)
        pull_btn = QPushButton("Pull", clicked=lambda: self.run_command(
            ["adb", "-s", self.device_name, "pull", self.file_entry.text(), os.path.join(self.output_dir, os.path.basename(self.file_entry.text()))],
            "File pulled", "Failed to pull file"))
        pull_btn.setToolTip("Download file from device")
        file_grid.addWidget(pull_btn, 0, 3)
        file_grid.addWidget(QLabel("Push:"), 1, 0)
        self.push_entry = QLineEdit()
        self.push_entry.setToolTip("Local file to push to device")
        self.push_entry.setMaximumWidth(150)
        file_grid.addWidget(self.push_entry, 1, 1)
        push_browse_btn = QPushButton("Browse", clicked=lambda: self.browse_file(self.push_entry))
        push_browse_btn.setToolTip("Select local file to push")
        file_grid.addWidget(push_browse_btn, 1, 2)
        push_btn = QPushButton("Push", clicked=lambda: self.run_command(
            ["adb", "-s", self.device_name, "push", self.push_entry.text(), self.file_entry.text() or "/sdcard/"],
            "File pushed", "Failed to push file"))
        push_btn.setToolTip("Upload file to device")
        file_grid.addWidget(push_btn, 1, 3)
        file_layout.addLayout(file_grid)
        file_layout.addStretch()
        tabs.addTab(file_tab, "📁")
        tabs.setTabToolTip(4, "Transfer files to/from device")

        # Fastboot Tab
        fastboot_tab = QWidget()
        fastboot_layout = QVBoxLayout(fastboot_tab)
        fastboot_grid = QGridLayout()
        fastboot_grid.setHorizontalSpacing(5)

        fastboot_devices_btn = QPushButton("Devices", clicked=lambda: self.run_command(
            ["fastboot", "devices"], "Fastboot devices listed", "Failed to list fastboot devices", True))
        fastboot_devices_btn.setToolTip("List devices in fastboot mode")
        fastboot_grid.addWidget(fastboot_devices_btn, 0, 0)

        fastboot_reboot_btn = QPushButton("Restart Device", clicked=lambda: self.run_command(
            ["fastboot", "reboot"], "Device rebooted", "Failed to reboot device"))
        fastboot_reboot_btn.setToolTip("Restart the device to normal mode")
        fastboot_grid.addWidget(fastboot_reboot_btn, 0, 1)

        recovery_btn = QPushButton("Recovery", clicked=lambda: self.run_command(
            ["fastboot", "reboot", "recovery"], "Rebooted to recovery", "Failed to reboot to recovery"))
        recovery_btn.setToolTip("Reboot device to recovery mode")
        fastboot_grid.addWidget(recovery_btn, 0, 2)

        bootloader_btn = QPushButton("Bootloader", clicked=lambda: self.run_command(
            ["fastboot", "reboot-bootloader"], "Rebooted to bootloader", "Failed to reboot to bootloader"))
        bootloader_btn.setToolTip("Reboot device to bootloader mode")
        fastboot_grid.addWidget(bootloader_btn, 1, 0)

        flash_btn = QPushButton("Flash Partition", clicked=self.flash_partition)
        flash_btn.setToolTip("Flash a partition with an image file")
        fastboot_grid.addWidget(flash_btn, 1, 1)

        getvar_btn = QPushButton("Getvar", clicked=lambda: self.run_command(
            ["fastboot", "getvar", "all"], "Device variables retrieved", "Failed to get variables", True))
        getvar_btn.setToolTip("Get all fastboot variables")
        fastboot_grid.addWidget(getvar_btn, 1, 2)

        oem_unlock_btn = QPushButton("OEM Unlock", clicked=lambda: self.run_command(
            ["fastboot", "oem", "unlock"], "OEM unlocked", "Failed to unlock OEM (may already be unlocked or not supported)"))
        oem_unlock_btn.setToolTip("Unlock the bootloader (warning: wipes data)")
        fastboot_grid.addWidget(oem_unlock_btn, 2, 0)

        fastboot_layout.addLayout(fastboot_grid)
        fastboot_layout.addStretch()
        tabs.addTab(fastboot_tab, "⚡")
        tabs.setTabToolTip(5, "Fastboot mode controls")

        # Output Tab
        output_tab = QWidget()
        output_layout = QVBoxLayout(output_tab)
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMinimumHeight(150)
        output_layout.addWidget(QLabel("Output:"))
        output_layout.addWidget(self.output_text)
        tabs.addTab(output_tab, "📋")
        tabs.setTabToolTip(6, "View command outputs")

        # Status and Progress
        status_layout = QHBoxLayout()
        self.status_label = QLabel("Ready!")
        status_layout.addWidget(self.status_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress.setMaximumWidth(100)
        status_layout.addWidget(self.progress)
        show_log_btn = QPushButton("Show Log", clicked=self.show_log_dock)
        show_log_btn.setToolTip("Re-open the log window if closed")
        status_layout.addWidget(show_log_btn)
        main_layout.addLayout(status_layout)

        # Footer
        footer_layout = QHBoxLayout()
        self.connection_status = QLabel("Connected to: None")
        footer_layout.addWidget(self.connection_status)
        footer_layout.addStretch()
        footer_layout.addWidget(QLabel("v2.0 by SirCryptic"))
        main_layout.addLayout(footer_layout)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = ADBSploitApp()
    sys.exit(app.exec())