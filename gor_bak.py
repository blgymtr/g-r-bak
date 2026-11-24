"""gör-bak başlatıcı (PyInstaller giriş noktası)."""
import sys

from gorbak.arayuz import calistir

if __name__ == "__main__":
    sys.exit(calistir())
