"""
main.py — Entry point for the Behavioral Auth system
-----------------------------------------------------
Run:
    python3 main.py                        # prompts for user_id
    python3 main.py --user alice           # skip the prompt
    python3 main.py --user alice --no-shell  # skip shell monitoring

First-time setup (install zshrc hook for shell capture):
    python3 main.py --install-hook
"""

import argparse
import signal
import sys
import time

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

from storage.database import Database
from session_manager import SessionManager
from capture.shell_monitor import ShellMonitor


def run_session(user_id: str, enable_shell: bool):
    db = Database()
    session = SessionManager(user_id=user_id, db=db, enable_shell=enable_shell)

    # Graceful shutdown on Ctrl+C or SIGTERM
    def _shutdown(sig=None, frame=None):
        print("\n[main] Stopping session …")
        summary = session.summary()
        session.stop()
        db.close()

        print("\n--- Session Summary ---")
        for k, v in summary.items():
            print(f"  {k:<22} {v}")
        print("-----------------------\n")
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    session.start()

    # Keep the main thread alive; monitors run in background threads
    try:
        while True:
            time.sleep(10)
            s = session.summary()
            print(
                f"[main] alive — "
                f"keystrokes={s['keystroke_events']}  "
                f"mouse={s['mouse_events']}  "
                f"shell={s['shell_events']}  "
                f"idle={session.idle_seconds():.0f}s"
            )
    except KeyboardInterrupt:
        _shutdown()


def main():
    parser = argparse.ArgumentParser(
        description="Behavioral Auth — Phase 1 capture"
    )
    parser.add_argument("--user", type=str, default=None, help="User ID / name")
    parser.add_argument(
        "--no-shell",
        action="store_true",
        help="Disable shell command monitoring",
    )
    parser.add_argument(
        "--install-hook",
        action="store_true",
        help="Install zshrc hook for shell capture then exit",
    )
    parser.add_argument(
        "--remove-hook",
        action="store_true",
        help="Remove zshrc hook then exit",
    )

    args = parser.parse_args()

    if args.install_hook:
        ShellMonitor.install_hook(shell="zsh")
        sys.exit(0)

    if args.remove_hook:
        ShellMonitor.remove_hook(shell="zsh")
        sys.exit(0)

    user_id = args.user
    if not user_id:
        user_id = input("Enter user ID (your name or any identifier): ").strip()
        if not user_id:
            print("User ID cannot be empty.")
            sys.exit(1)

    enable_shell = not args.no_shell

    print("\n" + "=" * 50)
    print("  Behavioral Auth — Capture (Phase 1)")
    print("=" * 50)
    if enable_shell:
        print("  Shell monitoring ON  (make sure hook is installed)")
        print("  Run: python main.py --install-hook   (first time only)")
    else:
        print("  Shell monitoring OFF")
    print("=" * 50 + "\n")

    run_session(user_id=user_id, enable_shell=enable_shell)


if __name__ == "__main__":
    main()
