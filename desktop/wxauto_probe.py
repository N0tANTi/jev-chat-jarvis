"""Installed-package/auth diagnostics only: never open/read/send WeChat messages."""
import importlib.metadata
import json
import subprocess
import sys


def main():
    result = {"message_reading_tested": False}
    for name in ("wxautox4", "wxauto-mcp", "mcp"):
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = "not_installed"
    if result["wxautox4"] != "not_installed":
        try:
            process = subprocess.run([sys.executable, "-m", "wxautox4", "--json", "auth", "check"],
                                     capture_output=True, timeout=30)
            status = json.loads(process.stdout.decode("utf-8"))
            result["active"] = status.get("active") is True
        except (subprocess.TimeoutExpired, UnicodeError, ValueError, OSError):
            result["active"] = None
    print(json.dumps(result))


if __name__ == "__main__":
    main()
