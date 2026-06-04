#!/usr/bin/env python3
"""Test manual DLL loading for PyTorch"""
import ctypes
from importlib.util import find_spec
import os

print("Attempting manual DLL load...")
spec = find_spec("torch")
if spec and spec.origin:
    dll_path = os.path.join(os.path.dirname(spec.origin), "lib", "c10.dll")
    print(f"DLL path: {dll_path}")
    try:
        ctypes.CDLL(os.path.normpath(dll_path))
        print("✓ DLL loaded successfully")
    except Exception as e:
        print(f"✗ Failed to load DLL: {e}")

try:
    import torch
    print(f"✓ PyTorch imported successfully: {torch.__version__}")
    print(f"✓ CUDA available: {torch.cuda.is_available()}")
except Exception as e:
    print(f"✗ PyTorch import failed: {e}")
