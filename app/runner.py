import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable


class CodeRunner:
    def __init__(self, workdir: Path):
        self.workdir = workdir

    def run(
        self,
        file_path: str,
        on_stdout: Callable[[str], None] | None = None,
        on_stderr: Callable[[str], None] | None = None,
        on_exit: Callable[[int], None] | None = None,
    ) -> int:
        p = Path(file_path)
        if not p.exists():
            if on_stderr:
                on_stderr(f"File not found: {file_path}\n")
            return -1

        ext = p.suffix.lower()
        cmd = self._build_command(p, ext)
        if cmd is None:
            if on_stderr:
                on_stderr(f"Unsupported file type: {ext}\n")
            return -1

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(self.workdir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            def read_stream(stream, callback):
                if stream is None:
                    return
                for line in stream:
                    if callback:
                        callback(line)

            import threading
            t1 = threading.Thread(target=read_stream, args=(proc.stdout, on_stdout), daemon=True)
            t2 = threading.Thread(target=read_stream, args=(proc.stderr, on_stderr), daemon=True)
            t1.start()
            t2.start()
            code = proc.wait()
            t1.join()
            t2.join()
            if on_exit:
                on_exit(code)
            return code
        except FileNotFoundError as e:
            if on_stderr:
                on_stderr(f"Command not found: {e}\n")
            return -1
        except Exception as e:
            if on_stderr:
                on_stderr(f"Error: {e}\n")
            return -1

    def _build_command(self, path: Path, ext: str) -> list[str] | None:
        if ext == ".py":
            py = self._find_python()
            return [py, str(path)]
        if ext in (".cpp", ".cxx", ".cc", ".c++"):
            compiler = self._find_cpp_compiler()
            if compiler is None:
                return None
            out = path.with_suffix(".exe") if os.name == "nt" else Path(str(path) + "_out")
            return [compiler, str(path), "-o", str(out)]
        if ext == ".c":
            compiler = self._find_c_compiler()
            if compiler is None:
                return None
            out = path.with_suffix(".exe") if os.name == "nt" else Path(str(path) + "_out")
            return [compiler, str(path), "-o", str(out)]
        return None

    @staticmethod
    def _find_python() -> str:
        for name in ("python", "python3", "py"):
            path = shutil.which(name)
            if path:
                return path
        return "python"

    @staticmethod
    def _find_cpp_compiler() -> str | None:
        for name in ("g++", "clang++", "cl"):
            path = shutil.which(name)
            if path:
                return path
        return None

    @staticmethod
    def _find_c_compiler() -> str | None:
        for name in ("gcc", "clang", "cl"):
            path = shutil.which(name)
            if path:
                return path
        return None