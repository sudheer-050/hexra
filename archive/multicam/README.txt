Multi-camera (stereo 3D) work, removed from the app on request.
Nothing in src/ or tests/ uses it. To restore: copy src/*.py to src/hexra/, tests/*.py to tests/,
data/* to data/, and re-add the stereo/auto-calibration code to app.py (see git-less history: the earlier app.py
had MonoSource/StereoSource). Findings from the one real two-camera run are in the chat history.
