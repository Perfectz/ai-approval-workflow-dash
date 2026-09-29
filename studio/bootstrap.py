import json
from .store import ROOT
from .media import inspect_media


def seed(store):
    """Import a real, unapproved technical test on the very first start only."""
    if store.list_projects():
        return
    project = store.create_project({"title": "Temporary audio lab", "brief": "A real 15-second timing test with two temporary voices. Explore prompts, version history and reviews here. This sandbox is separate from your film projects.", "runtime_minutes": .25, "demo": True})
    scene = store.save_scene(project["id"], {"title": "Two voices · one exchange", "duration": 15, "purpose": "Check the space between dialogue, reaction and the cut.", "emotion": "Neutral technical test", "start_state": "CHAR_A (blue) and CHAR_B (orange) in a shared frame.", "end_state": "Hold CHAR_B after the reply.", "locked": "Character IDs and color mapping; 30 fps; no clipped speech.", "flexible": "Camera distance and the length of the silent reaction."})
    folders = sorted((ROOT / "outputs/TIMING_DEMO").glob("*/timing.json"))
    if folders:
        folder = folders[-1].parent
        report = json.loads((folder / "timing.json").read_text(encoding="utf-8"))
        files = [folder / "mix.wav"] + sorted((folder / "stems").glob("*.wav")) + [folder / "timing.json", folder / "dialogue.srt", folder / "blender-timing.json"]
        value = store.add_version(project["id"], {"kind": "audio", "stage": "audio", "scene_id": scene, "title": "Dialogue & timing test", "content": "CHAR_A · Blue · temporary David voice\n01.00s: This is voice A. Leave room for a response.\n\nCHAR_B · Orange · temporary Zira voice\n08.00s: This is voice B. Hold the last frame before the cut.\n\nListen to the full mix and isolated tracks. The voices are placeholders. No film has been approved.", "prompt": "15-second timing study, 30 fps.\n\n0–7s: Wide shot of two characters. CHAR_A is the blue dummy on the left; CHAR_B is the orange dummy on the right. CHAR_A speaks at 1s, then allows a quiet reaction.\n\n7–15s: Cut to a medium shot of CHAR_B. CHAR_B replies at 8s. Hold after the reply.\n\nPreserve character positions, screen direction and the deliberate silence. Use the approved identity sheets when replacing dummies. No on-screen labels in the final video.\n\nThis is a planning prompt; it has not been sent to Wan.", "metadata": {**inspect_media(folder / "mix.wav"), "timing_passed": report["timing_passed"], "timing": report, "reference_map": "CHAR_A → blue dummy → Voice A (temporary David)\nCHAR_B → orange dummy → Voice B (temporary Zira)", "prompt_extend": False, "reference_media": [], "source": "Local System.Speech technical test"}}, [(f.name, f) for f in files if f.exists()], actor="import")
        store.submit(value["version_id"], "import")
    store.create_project({"title": "My first film", "brief": "Start with the premise. Choose the audience, the emotional journey, and what changes by the end. Your agents can propose ideas here before anything moves into production.", "runtime_minutes": 2})
