import sys
from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton


class AudioPlayerApp(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PySide6 Audio Player")
        self.resize(300, 100)

        # Initialize the sound effect player
        self.effect = QSoundEffect()

        # Load your local audio file (WAV format is best supported)
        self.effect.setSource(QUrl.fromLocalFile("sound.wav"))

        # Optional: Set configurations
        self.effect.setVolume(0.75)  # Range from 0.0 to 1.0
        # self.effect.setLoopCount(QSoundEffect.Infinite) # Uncomment to loop

        # Create a trigger button
        self.button = QPushButton("Play Sound", self)
        self.button.setGeometry(50, 30, 200, 40)
        self.button.clicked.connect(self.play_sound)

    def play_sound(self):
        # Play the audio file
        if self.effect.isLoaded():
            self.effect.play()
        else:
            print("Audio file is still loading or could not be found.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AudioPlayerApp()
    window.show()
    sys.exit(app.exec())
