import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QVBoxLayout, QHBoxLayout,
    QWidget, QPushButton, QComboBox, QLabel, QMenuBar, QMenu, QFileDialog, QSplitter,
    QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsTextItem
)
from PyQt6.QtGui import QIcon, QAction, QBrush, QColor
from PyQt6.QtCore import Qt, QRectF


class SocketPreviewWidget(QGraphicsView):
    def __init__(self, chip_pins=14, socket_position=1, parent=None):
        super().__init__(parent)
        self.chip_pins = chip_pins
        self.socket_position = socket_position
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.draw_socket()
        self.draw_chip()

    def draw_socket(self):
        self.scene.clear()
        pin_size = 10
        spacing = 5
        start_x = 50
        start_y = 20

        for i in range(20):
            for col in range(2):
                pin_num = i + 1 + (col * 20)
                x = start_x + col * (pin_size + 60)
                y = start_y + i * (pin_size + spacing)
                pin = QGraphicsRectItem(x, y, pin_size, pin_size)
                pin.setBrush(QBrush(Qt.GlobalColor.lightGray))
                self.scene.addItem(pin)

                label = QGraphicsTextItem(str(pin_num))
                label.setPos(x + pin_size + 2, y - 2)
                self.scene.addItem(label)

    def draw_chip(self):
        chip_pin_count = self.chip_pins
        start_pin = self.socket_position
        pins_per_side = chip_pin_count // 2

        pin_size = 10
        spacing = 5
        start_x = 50
        col_spacing = pin_size + 60
        start_y = 20

        # Calculate vertical offset based on socket pin alignment
        chip_offset = ((start_pin - 1) % 20) * (pin_size + spacing)

        chip_width = col_spacing
        chip_height = (pin_size + spacing) * pins_per_side - spacing

        chip_rect = QGraphicsRectItem(start_x, start_y + chip_offset, chip_width, chip_height)
        chip_rect.setBrush(QBrush(QColor(0, 100, 200, 100)))
        self.scene.addItem(chip_rect)


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

        file_menu = menu_bar.addMenu("File")
        open_action = QAction("Open", self)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        settings_menu = menu_bar.addMenu("Settings")
        preferences_action = QAction("Preferences", self)
        settings_menu.addAction(preferences_action)

        help_menu = menu_bar.addMenu("Help")
        about_action = QAction("About", self)
        help_menu.addAction(about_action)

    def setup_main_layout(self):
        main_widget = QWidget()
        main_layout = QVBoxLayout()

        control_layout = QHBoxLayout()

        self.chip_selector = QComboBox()
        self.chip_selector.addItems(["Select Chip", "PIC16F84A", "PIC18F2550", "PIC32MX"])
        control_layout.addWidget(QLabel("Chip Type:"))
        control_layout.addWidget(self.chip_selector)

        # Replace label with graphics widget
        self.socket_preview = SocketPreviewWidget(chip_pins=14, socket_position=10)
        self.socket_preview.setFixedHeight(500)
        control_layout.addWidget(self.socket_preview)

        main_layout.addLayout(control_layout)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.hex_editor = QTextEdit()
        self.hex_editor.setReadOnly(True)
        self.hex_editor.setPlaceholderText("Hexdump preview of loaded/dumped file")
        splitter.addWidget(self.hex_editor)
        main_layout.addWidget(splitter)

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
