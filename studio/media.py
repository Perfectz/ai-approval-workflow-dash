"""Local media inspection. Metadata comes from decoded files, not filename guesses."""
import json
import shutil
import subprocess
import wave
from array import array


def inspect_media(path):
    if path.suffix.lower() == ".wav":
        with wave.open(str(path), "rb") as wav:
            duration = wav.getnframes() / wav.getframerate()
            result = {"duration": duration, "sample_rate": wav.getframerate(), "channels": wav.getnchannels(), "measured_by": "wave"}
            if wav.getsampwidth() == 2:
                samples = array("h", wav.readframes(wav.getnframes()))
                stride = max(1, len(samples) // 100)
                result["waveform"] = [round(max((abs(v) for v in samples[i:i+stride]), default=0) / 32768, 4) for i in range(0, len(samples), stride)][:100]
            return result
    executable = shutil.which("ffprobe")
    if not executable:
        return {}
    process = subprocess.run([executable, "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height,r_frame_rate", "-of", "json", str(path)], capture_output=True, text=True, timeout=45)
    if process.returncode:
        raise ValueError("Media could not be decoded by ffprobe.")
    data = json.loads(process.stdout)
    return {"duration": float(data["format"]["duration"]), "streams": data.get("streams", []), "measured_by": "ffprobe"}
