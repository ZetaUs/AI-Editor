import sys
import threading
from PySide6.QtCore import QThread, QObject, Signal, QTimer
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)

class MainWindow:
    def __init__(self):
        self.name = "TestWin"

class Worker(QObject):
    finished = Signal(object)
    error = Signal(str)
    chunk = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn
        print(f"Worker.__init__ ok")

    def run(self):
        print(f"Worker.run CALLED!")
        try:
            self._fn()
            self.finished.emit("DONE")
        except Exception as e:
            import traceback
            print(f"error: {e}\n{traceback.format_exc()}")
            self.error.emit(str(e))

mw = MainWindow()

def outer():
    # chat_fn captures mw (like self in main.py)
    def chat_fn():
        print(f"chat_fn running, mw.name={mw.name}")
        import time; time.sleep(0.5)
        print("chat_fn done")
    return chat_fn

fn = outer()
print(f"fn = {fn}")
print(f"fn.__closure__ = {fn.__closure__}")

thread = QThread()
worker = Worker(fn)
worker.moveToThread(thread)
print(f"worker.thread() = {worker.thread()}")

thread.started.connect(worker.run)
worker.finished.connect(lambda r: (print(f"on_finished: {r}"), thread.quit()))

print("starting...")
thread.start()
print(f"isRunning={thread.isRunning()}")

QTimer.singleShot(4000, app.quit)
app.exec()
print("exit")