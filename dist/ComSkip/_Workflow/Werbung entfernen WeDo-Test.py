"""Opt-in test entry point. The regular workflow and stable EXE stay intact."""
from pathlib import Path
import runpy


def main():
    workflow_dir = Path(__file__).resolve().parent
    experimental = workflow_dir.parent / "comskip-wedo-test.exe"
    if not experimental.is_file():
        raise FileNotFoundError(f"WeDo-Testbuild fehlt: {experimental}")
    workflow = runpy.run_path(str(workflow_dir / "Werbung entfernen.py"))
    run_session = workflow["run_session"]
    original = run_session.__globals__["run_comskip_compact"]

    def run_comskip(comskip, video, downloads, idx, total):
        selected = experimental if "wedo-movies" in video.name else comskip
        return original(selected, video, downloads, idx, total)

    run_session.__globals__["run_comskip_compact"] = run_comskip
    print("WEDO-TESTBRANCH: Nur WeDo Movies verwendet den experimentellen Scanner.")
    print("Bereits analysierte Filme im Menü mit [R] gezielt neu analysieren.")
    return workflow["main"]()


if __name__ == "__main__":
    raise SystemExit(main())
