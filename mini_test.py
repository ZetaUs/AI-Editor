import sys
import threading
from PySide6.QtCore import QThread, QObject, Signal, QTimer
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)

class Worker(QObject):
    finished = Signal(object)
    error = Signal(str)
    chunk = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn
        print(f"Worker.__init__ ok")

    def do_work(self):
        print(f"Worker.do_work CALLED! thread={threading.current_thread().name}")
        try:
            def _emit(c):
                print(f"emit chunk: {repr(c)}")
                self.chunk.emit(c)
            result = self._fn(on_chunk=_emit)
            print(f"Worker.do_work finished")
            self.finished.emit(result)
        except Exception as e:
            import traceback
            print(f"Worker error: {e}\n{traceback.format_exc()}")
            self.error.emit(str(e))

def run_in_thread(fn, on_finished=None, on_error=None, on_chunk=None):
    print("run_in_thread called")
    thread = QThread()
    worker = Worker(fn)
    worker.moveToThread(thread)
    print(f"worker.thread() = {worker.thread()}")
    thread.started.connect(worker.do_work)
    worker.finished.connect(lambda r: (on_finished(r) if on_finished else None, thread.quit()))
    worker.error.connect(lambda e: (on_error(e) if on_error else None, thread.quit()))
    worker.chunk.connect(lambda c: on_chunk(c) if on_chunk else None)
    thread.finished.connect(worker.deleteLater)
    print("starting thread...")
    thread.start()
    print(f"thread.isRunning={thread.isRunning()}")
    return thread

def my_fn(on_chunk=None):
    print("my_fn running!")
    if on_chunk:
        on_chunk("hello chunk 1")
        on_chunk("hello chunk 2")
    import time
    time.sleep(1)
    return "DONE"

def on_finished(r):
    print(f"on_finished: {r}")

t = run_in_thread(my_fn, on_finished=on_finished, on_error=lambda e: print(f"ERR: {e}"), on_chunk=lambda c: print(f"MAIN got chunk: {c}"))

QTimer.singleShot(4000, app.quit)
app.exec()
print("exit")