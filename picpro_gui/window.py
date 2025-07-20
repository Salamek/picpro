import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QVBoxLayout, QHBoxLayout,
    QWidget, QPushButton, QComboBox, QLabel, QMenuBar, QMenu,
    QFileDialog, QSplitter
)
from PyQt6.QtGui import QAction

from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt


class PicProGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PicPro GUI")
        self.setGeometry(100, 100, 1000, 700)
        self.init_ui()

    def init_ui(self):
        self.create_menu_bar()
        self.setup_main_layout()

    def create_menu_bar(self):
        menu_bar = self.menuBar()

        # File Menu
        file_menu = menu_bar.addMenu("File")
        open_action = QAction("Open", self)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Settings Menu
        settings_menu = menu_bar.addMenu("Settings")
        preferences_action = QAction("Preferences", self)
        settings_menu.addAction(preferences_action)

        # Help Menu
        help_menu = menu_bar.addMenu("Help")
        about_action = QAction("About", self)
        help_menu.addAction(about_action)

    def setup_main_layout(self):
        main_widget = QWidget()
        main_layout = QVBoxLayout()

        # Top section: Controls
        control_layout = QHBoxLayout()

        self.chip_selector = QComboBox()
        self.chip_selector.addItems(["Select Chip", "PIC16F84A", "PIC18F2550", "PIC32MX"])  # Example list
        control_layout.addWidget(QLabel("Chip Type:"))
        control_layout.addWidget(self.chip_selector)

        self.socket_position_label = QLabel("[Socket Position Preview Placeholder]")
        control_layout.addWidget(self.socket_position_label)

        main_layout.addLayout(control_layout)

        # Middle section: Hex editor (placeholder for now)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.hex_editor = QTextEdit()
        self.hex_editor.setReadOnly(True)
        self.hex_editor.setPlaceholderText("Hexdump preview of loaded/dumped file")
        splitter.addWidget(self.hex_editor)
        main_layout.addWidget(splitter)

        # Bottom section: Buttons
        button_layout = QHBoxLayout()
        self.read_button = QPushButton("Read")
        self.flash_button = QPushButton("Flash")
        self.verify_button = QPushButton("Verify")
        self.wipe_button = QPushButton("Wipe")
        self.set_fuses_button = QPushButton("Set Fuses")

        for btn in [self.read_button, self.flash_button, self.verify_button, self.wipe_button, self.set_fuses_button]:
            button_layout.addWidget(btn)

        main_layout.addLayout(button_layout)

        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

    def open_file(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Open File", "", "Hex Files (*.hex);;All Files (*)")
        if file_name:
            with open(file_name, 'r') as f:
                content = f.read()
                self.hex_editor.setPlainText(content)


def main():
    app = QApplication(sys.argv)
    window = PicProGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
