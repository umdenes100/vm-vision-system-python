import os
from pathlib import Path
from typing import Optional, Tuple

import torch
import torch.nn.functional as F
import torchvision

from machinelearning.util import preprocess


class Predictor:
    """
    Matches old behavior:
      - model filenames: {teamName}_{index}_{dim}.pth
      - base model: resnet18 (IMAGENET1K_V1)
      - replace fc -> Linear(512, dim)
      - output argmax class index
    """

    def __init__(self, models_dir: Optional[str] = None):
        repo_root = Path(__file__).resolve().parents[1]
        self.models_dir = Path(models_dir) if models_dir else (repo_root / "machinelearning" / "models")
        self.models_dir = self.models_dir.resolve()

        self.base = torchvision.models.resnet18(weights="IMAGENET1K_V1")
        self.base = self.base.to(torch.device("cpu"))
        self.base.eval()

    def _find_model_file(self, team_name: str, model_index: int) -> Tuple[Path, int]:
        team = str(team_name).strip()
        idx = int(model_index)

        best: Optional[Path] = None
        for entry in self.models_dir.iterdir():
            if not entry.is_file():
                continue
            if not entry.name.lower().endswith(".pth"):
                continue
            if not entry.name.startswith(team + "_"):
                continue

            parts = entry.name.split("_")
            if len(parts) < 3:
                continue

            try:
                file_idx = int(parts[1])
            except Exception:
                continue
            if file_idx != idx:
                continue

            best = entry
            break

        if best is None:
            available = []
            try:
                for e in self.models_dir.iterdir():
                    if e.is_file():
                        available.append(e.name)
            except Exception:
                pass
            raise FileNotFoundError(
                f"Could not find model for team '{team}' index {idx}. Available: {', '.join(available)}"
            )

        # last segment contains dim like "..._3.pth"
        dim_str = os.path.splitext(best.name)[0].split("_")[-1]
        dim = int(dim_str)
        return best, dim

    def predict(self, frame_bgr, team_name: str, model_index: int) -> int:
        model_path, dim = self._find_model_file(team_name, model_index)

        model = self.base
        model.fc = torch.nn.Linear(512, dim)
        model = model.to(torch.device("cpu"))
        model.eval()

        # load weights (torch versions differ on weights_only support)
        try:
            state = torch.load(str(model_path), map_location=torch.device("cpu"), weights_only=True)
        except TypeError:
            state = torch.load(str(model_path), map_location=torch.device("cpu"))
        model.load_state_dict(state)

        x = preprocess(frame_bgr)
        with torch.no_grad():
            out = model(x)
            probs = F.softmax(out, dim=1).detach().cpu().numpy().flatten()
        return int(probs.argmax())
