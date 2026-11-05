import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QObject, QSize, QUrl
from PySide6.QtGui import (
    QAction, QKeySequence, QFont, QColor, QPalette, QIcon, QPainter,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QLabel,
    QMessageBox,
    QFileDialog,
    QStatusBar,
)

from app.editor import CodeEditor
from app.file_manager import FileTree
from app.history import HistoryManager
from app.runner import CodeRunner
from app.ai_client import AIClient, extract_file_ops


APP_DIR = Path(__file__).resolve().parent
ICONS_DIR = APP_DIR / "app" / "icons"
UI_DIR = APP_DIR / "app" / "ui"


def svg_icon(name: str) -> QIcon:
    path = ICONS_DIR / name
    renderer = QSvgRenderer(str(path))
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def png_icon(name: str) -> QIcon:
    return QIcon(str(ICONS_DIR / name))


class Worker(QObject):
    finished = Signal(object)
    error = Signal(str)
    chunk = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            result = self._fn(on_chunk=lambda c: self.chunk.emit(c))
            self.finished.emit(result)
        except Exception as e:
            import traceback
            self.error.emit(f"{e}\n{traceback.format_exc()}")


def run_in_thread(parent, fn, on_finished=None, on_error=None, on_chunk=None):
    thread = QThread(parent)
    worker = Worker(fn)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(lambda r: (on_finished(r) if on_finished else None, thread.quit()))
    worker.error.connect(lambda e: (on_error(e) if on_error else None, thread.quit()))
    worker.chunk.connect(lambda c: on_chunk(c) if on_chunk else None)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(lambda: parent._cleanup_thread(thread))
    thread.start()
    return thread


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Code Editor")
        self.resize(1200, 800)

        self.workdir = APP_DIR
        self.history = HistoryManager(self.workdir)
        self.runner = CodeRunner(self.workdir)
        self.ai = AIClient()

        self._threads: list[QThread] = []

        self._build_ui()
        self._build_menu()

    def _cleanup_thread(self, thread):
        if thread in self._threads:
            self._threads.remove(thread)
        thread.deleteLater()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)

        self.file_tree = FileTree(self.workdir, self.history)
        self.file_tree.setMinimumWidth(200)
        self.file_tree.file_requested.connect(self.open_file)
        self.file_tree.file_deleted.connect(self._on_file_deleted)
        self.file_tree.file_renamed.connect(self._on_file_renamed)
        splitter.addWidget(self.file_tree)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(2)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setMovable(True)
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        center_layout.addWidget(self.tabs)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumHeight(180)
        self.output.setFont(QFont("Consolas, monospace", 9))
        self.output.setStyleSheet("background:#1E1F29;color:#F8F8F2;border:none;padding:4px;")
        center_layout.addWidget(self.output)

        splitter.addWidget(center)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(6)

        ai_header_row = QHBoxLayout()
        ai_label = QLabel()
        ai_label.setPixmap(svg_icon("ai.svg").pixmap(QSize(24, 24)))
        ai_header_row.addWidget(ai_label)
        ai_header = QLabel("AI Chat")
        ai_header.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        ai_header_row.addWidget(ai_header)
        ai_header_row.addStretch()
        right_layout.addLayout(ai_header_row)

        self.chat_view = QWebEngineView()
        self.chat_view.setStyleSheet("""
            QWebEngineView {
                background: #1E1F29;
                border: 1px solid #44475A;
                border-radius: 6px;
            }
        """)
        chat_html_path = UI_DIR / "chat.html"
        self.chat_view.setUrl(QUrl.fromLocalFile(str(chat_html_path)))
        right_layout.addWidget(self.chat_view, 1)

        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Ask AI... (Enter to send)")
        self.chat_input.setStyleSheet("""
            QLineEdit {
                background: #1E1F29; color: #F8F8F2;
                border: 1px solid #44475A; border-radius: 6px;
                padding: 8px;
            }
        """)
        self.chat_input.returnPressed.connect(self._send_chat)
        right_layout.addWidget(self.chat_input)

        btn_row = QHBoxLayout()
        self.btn_send = QPushButton("Send")
        self.btn_apply = QPushButton("Apply Changes")
        self.btn_apply.setIcon(svg_icon("bolt.svg"))
        self.btn_apply.setIconSize(QSize(16, 16))
        self.btn_clear = QPushButton("Clear Chat")
        self.btn_send.clicked.connect(self._send_chat)
        self.btn_apply.clicked.connect(lambda: self._send_chat(apply=True))
        self.btn_clear.clicked.connect(lambda: self.chat_view.page().runJavaScript("clearAll()"))
        btn_row.addWidget(self.btn_send)
        btn_row.addWidget(self.btn_apply)
        btn_row.addWidget(self.btn_clear)
        right_layout.addLayout(btn_row)

        splitter.addWidget(right)
        splitter.setSizes([250, 650, 400])

        root_layout.addWidget(splitter)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready")

    def _build_menu(self):
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")
        a_new = QAction("&New", self)
        a_new.setShortcut(QKeySequence.New)
        a_new.triggered.connect(self._new_file)
        file_menu.addAction(a_new)

        a_open = QAction("&Open Folder...", self)
        a_open.setShortcut(QKeySequence.Open)
        a_open.triggered.connect(self._open_folder)
        file_menu.addAction(a_open)

        file_menu.addSeparator()
        a_save = QAction("&Save", self)
        a_save.setShortcut(QKeySequence.Save)
        a_save.triggered.connect(self._save_current)
        file_menu.addAction(a_save)

        a_save_all = QAction("Save &All", self)
        a_save_all.setShortcut("Ctrl+Shift+S")
        a_save_all.triggered.connect(self._save_all)
        file_menu.addAction(a_save_all)

        file_menu.addSeparator()
        a_exit = QAction("E&xit", self)
        a_exit.setShortcut(QKeySequence.Quit)
        a_exit.triggered.connect(self.close)
        file_menu.addAction(a_exit)

        edit_menu = mb.addMenu("&Edit")
        a_undo = QAction("&Undo Last Action", self)
        a_undo.setShortcut("Ctrl+Z")
        a_undo.triggered.connect(self._undo)
        edit_menu.addAction(a_undo)

        edit_menu.addSeparator()
        a_run = QAction("&Run", self)
        a_run.setShortcut("Ctrl+R")
        a_run.triggered.connect(self._run_current)
        edit_menu.addAction(a_run)

        view_menu = mb.addMenu("&View")
        a_refresh = QAction("Refresh &Files", self)
        a_refresh.triggered.connect(self.file_tree.refresh)
        view_menu.addAction(a_refresh)

    def _new_file(self):
        editor = CodeEditor()
        editor.set_dirty(True)
        idx = self.tabs.addTab(editor, "Untitled")
        self.tabs.setCurrentIndex(idx)
        self.tabs.setTabToolTip(idx, "Untitled")

    def _open_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Open Folder", str(self.workdir))
        if d:
            self.workdir = Path(d)
            self.history.base_dir = self.workdir
            self.file_tree.base_dir = self.workdir
            self.file_tree.refresh()
            self.setWindowTitle(f"AI Code Editor - {self.workdir}")

    def open_file(self, path: str):
        p = Path(path)
        if not p.exists() or not p.is_file():
            return
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, CodeEditor) and w.file_path() == path:
                self.tabs.setCurrentIndex(i)
                return

        content = p.read_text(encoding="utf-8", errors="replace")
        editor = CodeEditor()
        editor.set_file(path)
        editor.setPlainText(content)
        editor.textChanged.connect(lambda: editor.set_dirty(True))
        editor.set_dirty(False)

        tab_name = p.name
        idx = self.tabs.addTab(editor, tab_name)
        self.tabs.setTabToolTip(idx, path)
        self.tabs.setCurrentIndex(idx)

    def _close_tab(self, idx: int):
        editor = self.tabs.widget(idx)
        if isinstance(editor, CodeEditor) and editor.is_dirty():
            if QMessageBox.question(
                self, "Unsaved", "Save before closing?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            ) == QMessageBox.Yes:
                self._save_editor(editor)
        self.tabs.removeTab(idx)

    def _current_editor(self) -> CodeEditor | None:
        w = self.tabs.currentWidget()
        return w if isinstance(w, CodeEditor) else None

    def _save_editor(self, editor: CodeEditor) -> bool:
        path = editor.file_path()
        if path is None:
            p, _ = QFileDialog.getSaveFileName(self, "Save As", str(self.workdir))
            if not p:
                return False
            path = p
            editor.set_file(path)
            idx = self.tabs.currentIndex()
            self.tabs.setTabText(idx, Path(p).name)
            self.tabs.setTabToolTip(idx, p)

        old_content = ""
        if Path(path).exists():
            old_content = Path(path).read_text(encoding="utf-8", errors="replace")
        new_content = editor.toPlainText()

        if old_content != new_content:
            rel = str(Path(path).relative_to(self.workdir))
            self.history.record_modify(rel, old_content, new_content)

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(new_content, encoding="utf-8")
        editor.set_dirty(False)
        self.statusBar().showMessage(f"Saved: {Path(path).name}")
        self.file_tree.refresh()
        return True

    def _save_current(self):
        editor = self._current_editor()
        if editor:
            self._save_editor(editor)

    def _save_all(self):
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, CodeEditor):
                self._save_editor(w)

    def _on_file_deleted(self, path: str):
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, CodeEditor) and w.file_path() == path:
                self.tabs.removeTab(i)
                break

    def _on_file_renamed(self, old_path: str, new_path: str):
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, CodeEditor) and w.file_path() == old_path:
                w.set_file(new_path)
                self.tabs.setTabText(i, Path(new_path).name)
                self.tabs.setTabToolTip(i, new_path)
                break

    def _undo(self):
        entry = self.history.undo()
        if entry is None:
            self.statusBar().showMessage("Nothing to undo")
            return
        self.statusBar().showMessage(f"Undid: {entry.action} {entry.path}")
        self.file_tree.refresh()
        self._reopen_affected(entry.path)

    def _reopen_affected(self, rel_path: str):
        abs_path = str(self.workdir / rel_path)
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, CodeEditor) and w.file_path() == abs_path:
                p = Path(abs_path)
                if p.exists():
                    w.setPlainText(p.read_text(encoding="utf-8", errors="replace"))
                    w.set_dirty(False)
                break
        else:
            p = Path(abs_path)
            if p.exists() and p.is_file():
                self.open_file(abs_path)

    def _run_current(self):
        editor = self._current_editor()
        if editor is None or editor.file_path() is None:
            QMessageBox.information(self, "Run", "Open a file first")
            return
        self._save_editor(editor)
        self.output.clear()
        self._append_output(f"Running: {Path(editor.file_path()).name}\n", "#50FA7B")

        file_path = editor.file_path()

        def run_fn(on_chunk=None):
            return self.runner.run(
                file_path,
                on_stdout=lambda t: None,
                on_stderr=lambda t: None,
                on_exit=None,
            )

        def on_finished(code):
            self._append_output(f"\nExit code: {code}\n", "#6272A4")

        def on_err(err):
            self._append_output(f"Error: {err}\n", "#FF5555")

        t = run_in_thread(self, run_fn, on_finished=on_finished, on_error=on_err)
        self._threads.append(t)

        import threading
        def pump_output():
            self.runner.run(
                file_path,
                on_stdout=lambda t: self._append_output(t, "#F8F8F2"),
                on_stderr=lambda t: self._append_output(t, "#FF5555"),
                on_exit=lambda c: None,
            )
        threading.Thread(target=pump_output, daemon=True).start()

    def _append_output(self, text: str, color: str = "#F8F8F2"):
        self.output.append(f'<span style="color:{color}">{text}</span>')

    def _chat_js(self, js: str):
        self.chat_view.page().runJavaScript(js)

    def _js_str(self, s: str) -> str:
        return s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")

    def _send_chat(self, apply: bool = False):
        text = self.chat_input.text().strip()
        if not text:
            return
        self.chat_input.clear()

        self._chat_js(f"appendUser('{self._js_str(text)}')")
        self._chat_js("startAi()")

        current_editor = self._current_editor()
        context = ""
        if current_editor and current_editor.file_path():
            context = (
                f"\n\nCurrent file: {Path(current_editor.file_path()).name}\n"
                f"```\n{current_editor.toPlainText()}\n```"
            )

        messages = [
            {"role": "system", "content": (
                "You are an AI coding assistant. "
                "You can help write, modify, or explain Python and C++ code. "
                f"The working directory is {self.workdir}. "
                "If the user asks to create or modify files, respond with a JSON array of file operations in code blocks like:\n"
                "```json\n[{\"action\": \"create|modify|delete\", \"path\": \"relative/path\", \"content\": \"file contents\"}]\n```"
            )},
            {"role": "user", "content": text + context},
        ]

        def chat_fn(on_chunk=None):
            return self.ai.chat_stream(messages, on_chunk=on_chunk)

        def on_chunk(chunk: str):
            self._chat_js(f"appendChunk('{self._js_str(chunk)}')")

        def on_done(result: str):
            self._chat_js("finishAi()")
            if apply:
                self._apply_ai_changes(result)
            self.statusBar().showMessage("AI response complete")

        def on_err(err):
            self._chat_js("finishAi()")
            self._chat_js(f"appendError('{self._js_str(err)}')")
            self.statusBar().showMessage("AI error")

        t = run_in_thread(self, chat_fn, on_finished=on_done, on_error=on_err, on_chunk=on_chunk)
        self._threads.append(t)
        self.statusBar().showMessage("Waiting for AI...")

    def _apply_ai_changes(self, ai_response: str):
        ops = extract_file_ops(ai_response)
        if not ops:
            self.chat_display.append(
                '<span style="color:#FFB86C">No file operations found in AI response.</span>'
            )
            return
        self.chat_display.append(
            f'<span style="color:#50FA7B">Applying {len(ops)} change(s)...</span>'
        )
        for op in ops:
            action = op.get("action", "").lower()
            rel_path = op.get("path", "")
            content = op.get("content", "")
            abs_path = self.workdir / rel_path

            if action == "create":
                if abs_path.exists():
                    self.history.record_modify(
                        rel_path,
                        abs_path.read_text(encoding="utf-8", errors="replace"),
                        content,
                    )
                else:
                    self.history.record_create(rel_path)
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                abs_path.write_text(content, encoding="utf-8")
                self.chat_display.append(
                    f'  <span style="color:#50FA7B">[created]</span> {rel_path}'
                )
            elif action == "modify":
                if abs_path.exists():
                    self.history.record_modify(
                        rel_path,
                        abs_path.read_text(encoding="utf-8", errors="replace"),
                        content,
                    )
                else:
                    self.history.record_create(rel_path)
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                abs_path.write_text(content, encoding="utf-8")
                self.chat_display.append(
                    f'  <span style="color:#F1FA8C">[modified]</span> {rel_path}'
                )
            elif action == "delete":
                if abs_path.exists():
                    self.history.record_delete(
                        rel_path,
                        abs_path.read_text(encoding="utf-8", errors="replace"),
                    )
                    abs_path.unlink()
                self.chat_display.append(
                    f'  <span style="color:#FF5555">[deleted]</span> {rel_path}'
                )
            else:
                self.chat_display.append(
                    f'  <span style="color:#F1FA8C">[unknown action]</span> {action}'
                )

        self.file_tree.refresh()
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, CodeEditor) and w.file_path():
                fp = Path(w.file_path())
                if fp.exists() and fp.relative_to(self.workdir) == Path(rel_path):
                    w.setPlainText(fp.read_text(encoding="utf-8", errors="replace"))
                    w.set_dirty(False)
                    break

    def closeEvent(self, event):
        self._save_all()
        for t in self._threads:
            if t.isRunning():
                t.quit()
                t.wait(2000)
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    palette = app.palette()
    palette.setColor(QPalette.Window, QColor("#282A36"))
    palette.setColor(QPalette.Base, QColor("#21222C"))
    palette.setColor(QPalette.AlternateBase, QColor("#282A36"))
    palette.setColor(QPalette.ToolTipBase, QColor("#282A36"))
    palette.setColor(QPalette.ToolTipText, QColor("#F8F8F2"))
    palette.setColor(QPalette.Text, QColor("#F8F8F2"))
    palette.setColor(QPalette.Button, QColor("#44475A"))
    palette.setColor(QPalette.ButtonText, QColor("#F8F8F2"))
    palette.setColor(QPalette.BrightText, QColor("#FF5555"))
    palette.setColor(QPalette.Link, QColor("#8BE9FD"))
    palette.setColor(QPalette.Highlight, QColor("#6272A4"))
    palette.setColor(QPalette.HighlightedText, QColor("#F8F8F2"))
    app.setPalette(palette)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()