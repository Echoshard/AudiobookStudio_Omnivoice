import os
import subprocess
import sys
import re
import tempfile

# Ordered list of supported PyTorch CUDA wheel targets (min driver CUDA version, wheel code, label)
CUDA_WHEEL_TARGETS = [
    (13.0, "cu130", "CUDA 13.0+"),
    (12.8, "cu128", "CUDA 12.8+"),
    (12.6, "cu126", "CUDA 12.6+"),
    (12.4, "cu124", "CUDA 12.4+"),
    (12.1, "cu121", "CUDA 12.1+"),
    (11.8, "cu118", "CUDA 11.8+"),
]


def get_cuda_from_driver_dll():
    """Query NVIDIA CUDA driver version directly via nvcuda.dll Driver API."""
    try:
        import ctypes
        cuda = ctypes.WinDLL("nvcuda.dll")
        ver = ctypes.c_int()
        if cuda.cuDriverGetVersion(ctypes.byref(ver)) == 0 and ver.value > 0:
            major = ver.value // 1000
            minor = (ver.value % 1000) // 10
            return True, float(f"{major}.{minor}")
    except Exception:
        pass
    return False, 0.0


def get_cuda_from_nvidia_smi():
    """Query NVIDIA CUDA driver version from nvidia-smi executable."""
    search_paths = [
        "nvidia-smi",
        r"C:\Windows\System32\nvidia-smi.exe",
        r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
    ]
    for path in search_paths:
        try:
            res = subprocess.run([path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                m = re.search(r'CUDA Version:\s+(\d+\.\d+)', res.stdout)
                if m:
                    return True, float(m.group(1))
        except Exception:
            continue
    return False, 0.0


def get_cuda_info():
    """
    Detects if NVIDIA hardware and driver are present, and returns the maximum supported CUDA version.
    Returns: (has_nv: bool, cuda_ver: float)
    """
    # 1. Try direct Driver API via ctypes (fastest and most accurate on Windows)
    has_nv, ver = get_cuda_from_driver_dll()
    if has_nv and ver > 0:
        return True, ver

    # 2. Try nvidia-smi in PATH and standard locations
    has_nv, ver = get_cuda_from_nvidia_smi()
    if has_nv and ver > 0:
        return True, ver

    # 3. Check for CUDA_PATH environment variable (set by CUDA Toolkit)
    cuda_path = os.environ.get("CUDA_PATH")
    if cuda_path and os.path.exists(cuda_path):
        m = re.search(r'v(\d+\.\d+)', cuda_path)
        if m:
            return True, float(m.group(1))
        return True, 12.4

    # 4. Check for core NVIDIA driver DLL in System32
    if os.path.exists(r"C:\Windows\System32\nvcuda.dll"):
        # nvcuda.dll is present, fallback to 12.4 as a safe modern default
        return True, 12.4

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


def build_candidate_targets(has_nv, cuda_ver):
    """
    Build an ordered list of (wheel_target, index_url, label) candidates
    matching any CUDA version, in descending order of preference.
    """
    override = os.environ.get("TORCH_CUDA_WHEEL", "auto").strip().lower()

    if override and override != "auto":
        if override in ("cpu", "none"):
            return [("cpu", "https://download.pytorch.org/whl/cpu", "CPU-only override")]
        if re.fullmatch(r"cu\d{3}", override):
            return [(override, f"https://download.pytorch.org/whl/{override}", f"manual {override} override")]
        if override in ("default", "pypi"):
            return [("pypi", None, "default PyPI packages")]
        print(f"[WARN] Ignoring unrecognized TORCH_CUDA_WHEEL override: {override}")

    if not has_nv:
        return [("cpu", "https://download.pytorch.org/whl/cpu", "CPU-only PyTorch")]

    # Build candidates list of all compatible CUDA targets (target CUDA <= driver CUDA)
    candidates = []
    for min_ver, wheel, label in CUDA_WHEEL_TARGETS:
        if cuda_ver >= min_ver:
            candidates.append((wheel, f"https://download.pytorch.org/whl/{wheel}", f"PyTorch {label} ({wheel})"))

    # If driver CUDA is below 11.8 (very old) or didn't match any above, add cu118 as a last GPU attempt
    if not candidates:
        candidates.append(("cu118", "https://download.pytorch.org/whl/cu118", "PyTorch CUDA 11.8+ (cu118)"))

    return candidates


def test_torch_cuda():
    """
    Tests if torch is installed and whether torch.cuda.is_available() works.
    Returns: (installed: bool, cuda_available: bool, info_str: str)
    """
    verify_code = (
        "import sys, torch\n"
        "cuda_avail = torch.cuda.is_available()\n"
        "gpu_name = torch.cuda.get_device_name(0) if cuda_avail else 'None'\n"
        "cap = str(torch.cuda.get_device_capability(0)) if cuda_avail else 'None'\n"
        "print(f'{torch.__version__}|{torch.version.cuda}|{cuda_avail}|{gpu_name}|{cap}')\n"
        "sys.exit(0 if cuda_avail else 10)\n"
    )
    try:
        res = subprocess.run([sys.executable, "-c", verify_code], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0:
            parts = res.stdout.strip().split('|')
            info = f"torch {parts[0]}, CUDA runtime {parts[1]}, GPU: {parts[3]} (Compute {parts[4]})"
            return True, True, info
        elif res.returncode == 10:
            parts = res.stdout.strip().split('|') if '|' in res.stdout else [res.stdout.strip(), 'None', 'False', 'None', 'None']
            info = f"torch {parts[0]}, CUDA runtime {parts[1]} (CUDA not active)"
            return True, False, info
        else:
            return False, False, res.stderr.strip()
    except Exception as e:
        return False, False, str(e)


def uninstall_torch_packages(torch_packages):
    try:
        subprocess.run(
            [sys.executable, '-m', 'pip', 'uninstall', '-y', *torch_packages, 'torchvision'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def install_candidate(torch_packages, wheel, index_url, label, is_gpu_candidate):
    print(f"\n[System] Installing {label}...")
    cmd = [sys.executable, '-m', 'pip', 'install', '--upgrade', *torch_packages]
    if index_url:
        cmd.extend(['--index-url', index_url, '--extra-index-url', 'https://pypi.org/simple'])

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[Warning] Package installation failed for {label}: {e}")
        return False

    installed, cuda_avail, info = test_torch_cuda()
    if not installed:
        print(f"[Warning] Verification failed after installing {label}.")
        return False

    if is_gpu_candidate:
        if cuda_avail:
            print(f"[SUCCESS] GPU PyTorch verified: {info}")
            return True
        else:
            print(f"[Warning] PyTorch installed ({info}), but CUDA acceleration is not active.")
            return False
    else:
        print(f"[SUCCESS] PyTorch verified: {info}")
        return True


def main():
    ensure_temp_dir()
    print("============================================================")
    print("   OmniVoice Studio - Hardware & PyTorch Detection")
    print("============================================================")
    
    has_nv, cuda_ver = get_cuda_info()
    if has_nv:
        print(f"[System] NVIDIA GPU detected with driver CUDA version {cuda_ver}.")
    else:
        print("[System] No NVIDIA GPU detected. Using CPU mode.")

    torch_packages = os.environ.get("TORCH_PACKAGES", "torch torchaudio").split()
    candidates = build_candidate_targets(has_nv, cuda_ver)

    success = False
    for idx, (wheel, index_url, label) in enumerate(candidates):
        is_gpu = (wheel != "cpu" and wheel != "pypi")
        print(f"\n[System] Candidate [{idx+1}/{len(candidates)}]: {label}")
        
        # Cleanly uninstall previous torch packages to prevent binary / ABI mismatch
        uninstall_torch_packages(torch_packages)
        
        if install_candidate(torch_packages, wheel, index_url, label, is_gpu):
            success = True
            break
        else:
            if idx + 1 < len(candidates):
                print(f"[System] Falling back to next compatible candidate target...")

    # If all CUDA candidates failed, fallback to CPU-only PyTorch
    if not success and has_nv:
        print("\n[Warning] All CUDA wheel candidates failed. Falling back to CPU-only PyTorch build...")
        uninstall_torch_packages(torch_packages)
        cpu_wheel, cpu_url, cpu_label = "cpu", "https://download.pytorch.org/whl/cpu", "CPU-only PyTorch"
        if install_candidate(torch_packages, cpu_wheel, cpu_url, cpu_label, is_gpu_candidate=False):
            success = True
            print("\n[NOTE] Running in CPU mode. If you have an NVIDIA GPU, please update your NVIDIA driver from nvidia.com.")

    if not success:
        print("\n[ERROR] Unable to successfully install PyTorch.")
        sys.exit(1)

    print("\n============================================================")
    print("   PyTorch installation and verification complete!")
    print("============================================================\n")


if __name__ == "__main__":
    main()
