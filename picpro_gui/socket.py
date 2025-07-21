import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QVBoxLayout, QHBoxLayout,
    QWidget, QPushButton, QComboBox, QLabel, QMenuBar, QMenu, QFileDialog, QSplitter,
    QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsTextItem, QGraphicsEllipseItem
)
from PyQt6.QtGui import QIcon, QAction, QBrush, QFont
from PyQt6.QtCore import Qt, QRectF


class SocketPreviewWidget(QGraphicsView):
    def __init__(self, chip_pins=14, socket_position=1, parent=None):
        super().__init__(parent)
        self.dpi = self.viewport().logicalDpiX()
        self.chip_pins = chip_pins
        self.socket_position = socket_position
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.scene.clear()
        self.draw_socket()
        self.draw_chip()

    def mm_to_px(self, mm: float) -> float:
        return (mm / 25.4) * self.dpi

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_socket_to_view()

    def fit_socket_to_view(self):
        items_bbox = self.scene.itemsBoundingRect()
        padding_ratio = 0.1
        pad_w = items_bbox.width() * padding_ratio
        pad_h = items_bbox.height() * padding_ratio
        padded_bbox = items_bbox.adjusted(-pad_w, -pad_h, pad_w, pad_h)
        self.fitInView(padded_bbox, Qt.AspectRatioMode.KeepAspectRatio)

    def draw_socket(self):
        start_x = 50
        start_y = 20


        number_of_pins_in_row = 20
        number_of_rows = 2
        pin_height = self.mm_to_px(1.3)
        pin_width = self.mm_to_px(7)
        vertical_spacing = self.mm_to_px(1.1)
        horizontal_spacing = self.mm_to_px(4)
        horizontal_padding = self.mm_to_px(2.1)
        bottom_padding = self.mm_to_px(6.5)
        top_padding = self.mm_to_px(8.5)
        leaver_length = self.mm_to_px(17)
        leaver_thickens = self.mm_to_px(1.5)
        leaver_top_offset = self.mm_to_px(11)

        # Drawn socket body
        socket_width = pin_width * number_of_rows + horizontal_spacing + (horizontal_padding * 2)
        socket_height = (pin_height + vertical_spacing) * number_of_pins_in_row - vertical_spacing
        socket = QGraphicsRectItem(start_x, start_y+leaver_top_offset, socket_width, socket_height + top_padding + bottom_padding)
        socket.setBrush(QBrush(Qt.GlobalColor.darkGreen))
        self.scene.addItem(socket)

        # Drawn leaver
        leaver = QGraphicsRectItem(start_x, start_y, leaver_thickens, leaver_length)
        leaver.setBrush(QBrush(Qt.GlobalColor.lightGray))
        self.scene.addItem(leaver)


        for i in range(number_of_pins_in_row):
            for col in range(number_of_rows):
                pin_num = i + 1 + (col * number_of_pins_in_row)
                x = start_x + col * (pin_width + horizontal_spacing) + horizontal_padding
                y = start_y + top_padding + leaver_top_offset + i * (pin_height + vertical_spacing)
                pin = QGraphicsRectItem(x, y, pin_width, pin_height)
                pin.setBrush(QBrush(Qt.GlobalColor.lightGray))
                self.scene.addItem(pin)

                label = QGraphicsTextItem(str(pin_num))
                font = QFont()
                font.setPointSize(round(self.mm_to_px(1.8)))  # Set desired point size
                label.setFont(font)
                text_rect = label.boundingRect()
                if col == 0:
                    x_pos = x - text_rect.width() - horizontal_padding
                else:
                    x_pos = x + pin_width + horizontal_padding
                label.setPos(x_pos, y + (pin_height - text_rect.height()) / 2)
                self.scene.addItem(label)

        # After setting up your scene:
        self.fit_socket_to_view()

    def draw_chip(self):
        number_of_rows = 2 # @TODO make self. it is duplicit from drawn_socket
        pin_width = self.mm_to_px(7) # @TODO make self. it is duplicit from drawn_socket
        pin_height = self.mm_to_px(1.3)
        horizontal_spacing = self.mm_to_px(4) # @TODO make self. it is duplicit from drawn_socket
        horizontal_padding = self.mm_to_px(2.1) # @TODO make self. it is duplicit from drawn_socket
        vertical_spacing = self.mm_to_px(1.1) # @TODO make self. it is duplicit from drawn_socket
        leaver_top_offset = self.mm_to_px(11) # @TODO make self. it is duplicit from drawn_socket
        top_padding = self.mm_to_px(8.5) # @TODO make self. it is duplicit from drawn_socket
        chip_key_size = self.mm_to_px(1)
        chip_key_padding = self.mm_to_px(0.5)
        socket_width = pin_width * number_of_rows + horizontal_spacing + (horizontal_padding * 2) # @TODO make self. it is duplicit from drawn_socket

        # DIP 8
        #chip_height = self.mm_to_px(9.02)
        # Calculate instead
        pins_per_side = self.chip_pins // 2
        chip_height = (pin_height + vertical_spacing) * pins_per_side

        chip_width = self.mm_to_px(6.15)  # @TODO this needs to be defined by chip package...



        start_pin = self.socket_position


        start_x = 50
        start_y = 20

        # Calculate vertical offset based on socket pin alignment
        # We offset by vertical_spacing / 2 to top since chip_height have 1* vertical_spacing more and this is a good
        # way to render chip body overlying pins
        chip_offset = ((start_pin - 1) % 20) * (pin_height + vertical_spacing) + leaver_top_offset + top_padding - vertical_spacing / 2

        # Set chip on center of socket in X dimension
        x_position = start_x + (socket_width / 2) - (chip_width / 2)

        chip_rect = QGraphicsRectItem(x_position, start_y + chip_offset, chip_width, chip_height)
        chip_rect.setBrush(QBrush(Qt.GlobalColor.black))
        self.scene.addItem(chip_rect)

        # Render chip pin 1 key
        chip_rect = QGraphicsEllipseItem(x_position + chip_key_padding, start_y + chip_offset + chip_key_padding, chip_key_size, chip_key_size)
        chip_rect.setBrush(QBrush(Qt.GlobalColor.gray))
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
        self.socket_preview = SocketPreviewWidget(chip_pins=8, socket_position=13)
        #self.socket_preview = SocketPreviewWidget(chip_pins=40, socket_position=1)
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
