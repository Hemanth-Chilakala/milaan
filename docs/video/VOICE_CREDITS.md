# Narration and third-party credits

The demonstration narration is synthetic speech generated offline using [Piper](https://github.com/OHF-Voice/piper1-gpl). It is not a recording or imitation of the entrant's voice. The product's explanations are deterministic and do not depend on this presentation tool.

Voice: `en_US-ljspeech-high`. Its [model card](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/ljspeech/high/MODEL_CARD) identifies the public-domain [LJ Speech dataset](https://keithito.com/LJ-Speech-Dataset/) and credits the model training. Model files are downloaded separately into ignored `private/voice/`; they are not bundled with the project. Piper's own licence remains applicable to that separately installed tool.

To reproduce the narration after installing the locked dependencies:

```bash
mkdir -p private/voice
curl -fL https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ljspeech/high/en_US-ljspeech-high.onnx -o private/voice/en_US-ljspeech-high.onnx
curl -fL https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ljspeech/high/en_US-ljspeech-high.onnx.json -o private/voice/en_US-ljspeech-high.onnx.json
.venv/bin/python -m scripts.prepare_presentation
bash scripts/export_deck.sh
.venv/bin/python -m scripts.record_demo
# Refresh narration and deck headline from the actual recorded run:
.venv/bin/python -m scripts.prepare_presentation
bash scripts/export_deck.sh
bash scripts/make_video.sh
```

Before recording, start the dashboard and load the 10M dataset. Recording rebuilds derived reconciliation results and preserves source data and decision history. All captions use the same narration text. Any time-compressed dashboard segment is visibly labelled; the on-screen timer reports the actual database run.
