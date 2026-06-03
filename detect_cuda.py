import os
import subprocess
import sys
import re
import tempfile

CUDA_WHEEL_TARGETS = (
    (13.0, "cu130", "CUDA 13.0"),
    (12.8, "cu128", "CUDA 12.8"),
    (12.6, "cu126", "CUDA 12.6"),
    (12.4, "cu124", "CUDA 12.4"),
    (12.1, "cu121", "CUDA 12.1"),
    (11.8, "cu118", "CUDA 11.8"),
)

def get_cuda_info():
    # 1. Try running nvidia-smi (if it is in PATH)
    try:
        res = subprocess.run(['nvidia-smi'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0:
            m = re.search(r'CUDA Version:\s+(\d+\.\d+)', res.stdout)
            if m:
                return True, float(m.group(1))
    except Exception:
        pass

    # 2. Try running nvidia-smi by its absolute default path on Windows
    default_path = r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"
    if os.path.exists(default_path):
        try:
            res = subprocess.run([default_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                m = re.search(r'CUDA Version:\s+(\d+\.\d+)', res.stdout)
                if m:
                    return True, float(m.group(1))
        except Exception:
            pass

    # 3. Check for CUDA_PATH environment variable (set by CUDA Toolkit)
    cuda_path = os.environ.get("CUDA_PATH")
    if cuda_path and os.path.exists(cuda_path):
        m = re.search(r'v(\d+\.\d+)', cuda_path)
        if m:
            return True, float(m.group(1))
        return True, 12.1

    # 4. Check for core NVIDIA driver DLL in System32
    if os.path.exists(r"C:\Windows\System32\nvcuda.dll"):
        # nvcuda.dll indicates an NVIDIA driver is present and supports CUDA.
        # Fall back to 12.1 as a safe, broadly compatible modern target.
        return True, 12.1

    return False, 0.0

def ensure_temp_dir():
    candidates = [
        os.environ.get("TEMP"),
        os.environ.get("TMP"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Temp") if os.environ.get("LOCALAPPDATA") else None,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tmp"),
    ]

    for temp_dir in candidates:
        if not temp_dir:
            continue
        try:
            os.makedirs(temp_dir, exist_ok=True)
            fd, test_path = tempfile.mkstemp(prefix="omnivoice-temp-check-", dir=temp_dir)
            os.close(fd)
            os.unlink(test_path)
            os.environ["TEMP"] = temp_dir
            os.environ["TMP"] = temp_dir
            tempfile.tempdir = temp_dir
            return
        except OSError:
            continue

    print("[ERROR] No usable temporary directory was found for pip.")
    print("[ERROR] Create or fix %LOCALAPPDATA%\\Temp, then run this script again.")
    sys.exit(1)

def select_torch_index(has_nv, cuda_ver):
    override = os.environ.get("TORCH_CUDA_WHEEL", "auto").strip().lower()
    if override and override != "auto":
        if override in ("cpu", "none"):
            return "https://download.pytorch.org/whl/cpu", "CPU-only override"
        if re.fullmatch(r"cu\d{3}", override):
            return f"https://download.pytorch.org/whl/{override}", f"manual {override} override"
        if override in ("default", "pypi"):
            return None, "default PyPI torch packages"
        print(f"[WARN] Ignoring invalid TORCH_CUDA_WHEEL value: {override}")

    if not has_nv:
        return "https://download.pytorch.org/whl/cpu", "CPU-only PyTorch"

    for min_ver, wheel, label in CUDA_WHEEL_TARGETS:
        if cuda_ver >= min_ver:
            return f"https://download.pytorch.org/whl/{wheel}", f"PyTorch {label} wheels ({wheel})"

    return None, "standard compiled PyTorch"

def verify_torch_install(has_nv):
    verify_code = (
        "import torch\n"
        "print(f'[Verify] torch: {torch.__version__}')\n"
        "print(f'[Verify] torch CUDA runtime: {torch.version.cuda}')\n"
        "print(f'[Verify] torch.cuda.is_available(): {torch.cuda.is_available()}')\n"
        "if torch.cuda.is_available():\n"
        "    print(f'[Verify] GPU: {torch.cuda.get_device_name(0)}')\n"
        "    print(f'[Verify] capability: {torch.cuda.get_device_capability(0)}')\n"
    )
    res = subprocess.run([sys.executable, "-c", verify_code])
    if res.returncode != 0:
        print("[ERROR] PyTorch installed, but verification failed.")
        sys.exit(res.returncode)
    if has_nv and res.returncode == 0:
        # The verification process printed the detailed CUDA state. Keep this
        # warning here because laptops can expose NVIDIA drivers while policy
        # or driver state still prevents CUDA from initializing.
        check = subprocess.run(
            [sys.executable, "-c", "import torch; raise SystemExit(0 if torch.cuda.is_available() else 1)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if check.returncode != 0:
            print("[WARN] NVIDIA hardware was detected, but PyTorch cannot access CUDA yet.")
            print("[WARN] Update the NVIDIA driver, reboot, then run reinstall_gpu_torch.bat again.")

def main():
    ensure_temp_dir()
    print("[System] Running advanced GPU/CUDA detection...")
    has_nv, cuda_ver = get_cuda_info()

    torch_packages = os.environ.get("TORCH_PACKAGES", "torch torchaudio").split()
    cmd = [sys.executable, '-m', 'pip', 'install', '--upgrade', *torch_packages]
    index_url, target_label = select_torch_index(has_nv, cuda_ver)

    if has_nv:
        print(f"[System] NVIDIA GPU detected with driver CUDA {cuda_ver}.")
    else:
        print("[System] No NVIDIA GPU detected.")

    print(f"[System] Installing {target_label}...")
    if index_url:
        cmd.extend(['--index-url', index_url])

    # We must uninstall any existing cpu-only torch before installing GPU torch to prevent conflicts
    if has_nv:
        print("[System] Uninstalling existing CPU PyTorch instances (if any) to prevent conflicts...")
        try:
            subprocess.run([sys.executable, '-m', 'pip', 'uninstall', '-y', *torch_packages], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    try:
        subprocess.run(cmd, check=True)
        print("[System] PyTorch and Torchaudio installed successfully.")
        verify_torch_install(has_nv)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] PyTorch installation failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
