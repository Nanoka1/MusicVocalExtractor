import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from vocal_split import BVE_MODEL, split_vocals


class VocalSplitTests(unittest.TestCase):
    def test_bve_output_labels_follow_metadata_even_when_order_is_reversed(self):
        model = SimpleNamespace(is_bv_model=True, primary_stem_name="Vocals",
                                secondary_stem_name="Instrumental")
        engine = Mock(model_instance=model)
        engine.separate.return_value = ["BackingVocals.wav", "LeadVocals.wav"]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / "vocals.wav"
            with patch("vocal_split.prepare_model") as prepare, patch("vocal_split.validate_loaded_device") as validate:
                stems = split_vocals(Mock(return_value=engine), audio, root / "bve", root / "models",
                                    "cpu", lambda _: None)
            prepare.assert_called_once()
            self.assertEqual(prepare.call_args.args[1], BVE_MODEL)
            self.assertEqual(prepare.call_args.kwargs, {"arch": "VR"})
            engine.separate.assert_called_once_with(
                str(audio), custom_output_names={"Vocals": "BackingVocals", "Instrumental": "LeadVocals"})
            validate.assert_called_once_with(engine, "VR", "cpu")
            self.assertEqual(stems["LeadVocals"].name, "LeadVocals.wav")
            self.assertEqual(stems["BackingVocals"].name, "BackingVocals.wav")
