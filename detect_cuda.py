import os
import subprocess
import sys
import re

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
        # Fall back to 12.1 as a safe, highly compatible modern target.
        return True, 12.1

    return False, 0.0

def main():
    print("[System] Running advanced GPU/CUDA detection...")
    has_nv, cuda_ver = get_cuda_info()

    cmd = [sys.executable, '-m', 'pip', 'install', 'torch', 'torchaudio']
    if has_nv:
        if cuda_ver >= 12.4:
            cmd.extend(['--index-url', 'https://download.pytorch.org/whl/cu124'])
            print(f"[System] NVIDIA GPU detected with CUDA {cuda_ver}. Installing PyTorch with CUDA 12.4 acceleration...")
        elif cuda_ver >= 12.1:
            cmd.extend(['--index-url', 'https://download.pytorch.org/whl/cu121'])
            print(f"[System] NVIDIA GPU detected with CUDA {cuda_ver}. Installing PyTorch with CUDA 12.1 acceleration...")
        elif cuda_ver >= 11.8:
            cmd.extend(['--index-url', 'https://download.pytorch.org/whl/cu118'])
            print(f"[System] NVIDIA GPU detected with CUDA {cuda_ver}. Installing PyTorch with CUDA 11.8 acceleration...")
        else:
            print(f"[System] NVIDIA GPU detected with CUDA {cuda_ver}. Installing standard compiled PyTorch...")
    else:
        cmd.extend(['--index-url', 'https://download.pytorch.org/whl/cpu'])
        print("[System] No NVIDIA GPU detected. Installing highly optimized CPU-only PyTorch...")

    # We must uninstall any existing cpu-only torch before installing GPU torch to prevent conflicts
    if has_nv:
        print("[System] Uninstalling existing CPU PyTorch instances (if any) to prevent conflicts...")
        try:
            subprocess.run([sys.executable, '-m', 'pip', 'uninstall', '-y', 'torch', 'torchaudio'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    try:
        subprocess.run(cmd, check=True)
        print("[System] PyTorch and Torchaudio installed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] PyTorch installation failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
