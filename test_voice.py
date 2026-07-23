import os
import sys

# Ensure current directory is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    import VoiceCore
except ImportError as e:
    print(f"[Test ERROR] Failed to import VoiceCore: {e}")
    sys.exit(1)

def run_test():
    print("============================================================")
    print("   OmniVoice Model Download & Test Synthesis")
    print("============================================================")
    
    # Set Hugging Face home directory to local models folder (backup check)
    os.environ["HF_HOME"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
    print(f"HF_HOME set to: {os.environ['HF_HOME']}")
    
    print("\n[1/2] Loading OmniVoice model (will download ~2.5GB if not cached)...")
    device_info = []
    def device_callback(device_name):
        device_info.append(device_name)
        print(f"      Running on device: {device_name}")
        
    success = VoiceCore.ensure_model_loaded(
        status_cb=lambda msg: print(f"      Status: {msg}"),
        device_cb=device_callback
    )
    
    if not success:
        print("\n[ERROR] Failed to load/download the model!")
        sys.exit(1)
        
    print("\n[2/2] Generating test sample audio (random/default voice)...")
    test_text = "Hello! OmniVoice Studio is successfully set up and ready to generate high-fidelity audiobooks."
    output_file = "test_sampling.wav"
    
    # We use num_step=8 here for a faster test run during the setup process
    synthesis_success = VoiceCore.synthesize_audio(
        text=test_text,
        out_path=output_file,
        voice="alba",
        speed=1.0,
        num_step=8,
        status_cb=lambda msg: print(f"      Status: {msg}")
    )
    
    if synthesis_success and os.path.exists(output_file):
        print("\n============================================================")
        print(f"   SUCCESS: Test audio generated at '{output_file}'!")
        print("============================================================")
    else:
        print("\n[ERROR] Failed to synthesize test audio.")
        sys.exit(1)

if __name__ == "__main__":
    run_test()
