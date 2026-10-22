#!/usr/bin/env python3
"""
LUMI — Multi-Phrase Reproducible Custom Wake-Word Training Pipeline

Supports training custom openWakeWord binary classification ONNX models for
any of the eight authoritative LUMI wake phrases:
  1. "Hey LUMI"
  2. "Hello LUMI"
  3. "Hi LUMI"
  4. "Wake up, LUMI"
  5. "Let's play, LUMI"
  6. "Are you there, LUMI?"
  7. "LUMI!"
  8. "Good morning, LUMI"

Acoustic & Architectural Specification:
  - Input: 16 kHz, mono, 16-bit PCM (2-second audio windows = 32,000 samples)
  - Acoustic Feature Extractor: openWakeWord AudioFeatures (pre-trained Google Speech Embedding ONNX)
  - Feature Shape: (batch, 16, 96) — 16 time steps of 96-dimensional acoustic embeddings
  - Architecture: FCN MLP network with Linear(1536, 128) -> LayerNorm -> ReLU -> FCNBlock(128) -> Linear(128, 1) -> Sigmoid
  - Export: Standard ONNX (opset_version=13, dynamic batch size) matching openWakeWord runtime specification

Child Acoustic Considerations & Synthetic Data Limitations:
  - Child speech differs substantially from adult speech:
      * Higher fundamental frequency (F0: 250–400 Hz vs adult 100–220 Hz)
      * Formant frequencies (F1, F2, F3) shifted up by 20–30% due to shorter vocal tract
      * Phoneme duration variability and inconsistent consonant articulation (e.g. /r/, /l/, /s/)
  - IMPORTANT: Models trained purely on synthetic adult TTS (e.g., Piper Lessac) MUST be labeled
    as 'NEEDS VALIDATION' or 'NEEDS TRAINING' because synthetic TTS does not reflect real child
    speech acoustics, room reverberation, microphone clipping, or child speech variability.
  - Production verification requires at least 200–500 natural recordings across diverse child speakers
    (aged 3–9), varied environments (classroom, living room, car), and negative speech/noise.

Usage:
  python tools/wake_word_training/train_wake_word.py --help
  python tools/wake_word_training/train_wake_word.py --phrase "Good morning, LUMI" --generate-synthetic
"""

import argparse
import copy
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
from torch import nn, optim

# Ensure LUMI repository root is on sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [WakeWordTrain] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("WakeWordTrain")

# Supported phrases map to default model filenames
PHRASE_FILENAME_MAP: Dict[str, str] = {
    "Hey LUMI": "hey_lumi.onnx",
    "Hello LUMI": "hello_lumi.onnx",
    "Hi LUMI": "hi_lumi.onnx",
    "Wake up, LUMI": "wake_up_lumi.onnx",
    "Let's play, LUMI": "lets_play_lumi.onnx",
    "Are you there, LUMI?": "are_you_there_lumi.onnx",
    "LUMI!": "lumi.onnx",
    "Good morning, LUMI": "good_morning_lumi.onnx",
}


# ---------------------------------------------------------------------------
# openWakeWord Compatible Neural Network Architecture
# ---------------------------------------------------------------------------

class FCNBlock(nn.Module):
    """Fully Connected Block with Linear, LayerNorm, and ReLU."""
    def __init__(self, layer_dim: int):
        super().__init__()
        self.fcn_layer = nn.Linear(layer_dim, layer_dim)
        self.layer_norm = nn.LayerNorm(layer_dim)
        self.relu = nn.ReLU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.relu(self.layer_norm(self.fcn_layer(x)))


class OpenWakeWordNet(nn.Module):
    """PyTorch implementation of the official openWakeWord FCN classifier.

    Expects input shape: (batch, 16, 96)
    Outputs: (batch, 1) probability score in [0.0, 1.0]
    """
    def __init__(self, input_shape: Tuple[int, int] = (16, 96), layer_dim: int = 128,
                 n_blocks: int = 1, n_classes: int = 1):
        super().__init__()
        self.input_shape = input_shape
        self.flatten = nn.Flatten()
        in_features = input_shape[0] * input_shape[1]
        self.layer1 = nn.Linear(in_features, layer_dim)
        self.layernorm1 = nn.LayerNorm(layer_dim)
        self.relu1 = nn.ReLU()
        self.blocks = nn.ModuleList([FCNBlock(layer_dim) for _ in range(n_blocks)])
        self.last_layer = nn.Linear(layer_dim, n_classes)
        self.last_act = nn.Sigmoid() if n_classes == 1 else nn.ReLU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.relu1(self.layernorm1(self.layer1(self.flatten(x))))
        for block in self.blocks:
            x = block(x)
        return self.last_act(self.last_layer(x))


# ---------------------------------------------------------------------------
# Synthetic Phrase Generator (Local Piper TTS)
# ---------------------------------------------------------------------------

def generate_synthetic_samples_for_phrase(
    phrase: str,
    output_dir: Path,
    num_positive: int = 30,
    num_negative: int = 60,
) -> Tuple[List[np.ndarray], List[np.ndarray]]:
    """Generate 2-second audio clips (16 kHz int16) using local Piper TTS and noise."""
    from src.tts import PiperTTS

    model_path = REPO_ROOT / "models" / "tts" / "en_US-lessac-medium.onnx"
    config_path = REPO_ROOT / "models" / "tts" / "en_US-lessac-medium.onnx.json"
    if not model_path.exists() or not config_path.exists():
        raise RuntimeError("Piper TTS models not found. Please ensure local Piper model is present.")

    tts = PiperTTS(str(model_path), str(config_path), str(output_dir / "cache"))

    target_rate = 16000
    clip_len = 32000  # 2.0 seconds at 16 kHz

    # Variation phrases for target positive
    positive_phrases = [
        phrase,
        phrase.replace(",", "").replace("!", "").replace("?", ""),
        f"{phrase} please",
        f"{phrase} help me",
        f"{phrase} what is this",
    ]

    # Hard negatives (other LUMI phrases + common commands + conversational speech)
    other_phrases = [p for p in PHRASE_FILENAME_MAP.keys() if p.lower() != phrase.lower()]
    negative_phrases = other_phrases + [
        "Hey Jarvis",
        "Hello there",
        "Good afternoon",
        "What time is it",
        "Can you help me",
        "Tell me a story",
        "One two three four five",
        "Elephant and giraffe",
        "The sky is blue",
        "Apples and bananas",
        "Stop talking please",
        "Yes that is correct",
    ]

    positive_clips: List[np.ndarray] = []
    negative_clips: List[np.ndarray] = []

    logger.info("Generating %d positive samples for '%s'...", num_positive, phrase)
    for i in range(num_positive):
        p_text = positive_phrases[i % len(positive_phrases)]
        res = tts.synthesize(p_text)
        audio = res.audio
        # Resample from TTS sample rate (22050) to 16000
        orig_times = np.linspace(0, 1, len(audio))
        new_len = int(len(audio) * target_rate / res.sample_rate)
        new_times = np.linspace(0, 1, new_len)
        resampled = np.interp(new_times, orig_times, audio).astype(np.int16)

        # Pad or position in 2.0s buffer
        buf = np.zeros(clip_len, dtype=np.int16)
        if len(resampled) < clip_len:
            max_offset = clip_len - len(resampled)
            offset = (i * 1234) % max_offset if max_offset > 0 else 0
            buf[offset : offset + len(resampled)] = resampled
        else:
            buf[:] = resampled[:clip_len]

        # Add mild Gaussian noise
        noise = np.random.normal(0, 50, clip_len).astype(np.int16)
        positive_clips.append(np.clip(buf.astype(np.int32) + noise, -32768, 32767).astype(np.int16))

    logger.info("Generating %d negative speech samples...", num_negative)
    for i in range(num_negative):
        n_text = negative_phrases[i % len(negative_phrases)]
        res = tts.synthesize(n_text)
        audio = res.audio
        orig_times = np.linspace(0, 1, len(audio))
        new_len = int(len(audio) * target_rate / res.sample_rate)
        new_times = np.linspace(0, 1, new_len)
        resampled = np.interp(new_times, orig_times, audio).astype(np.int16)

        buf = np.zeros(clip_len, dtype=np.int16)
        if len(resampled) < clip_len:
            max_offset = clip_len - len(resampled)
            offset = (i * 987) % max_offset if max_offset > 0 else 0
            buf[offset : offset + len(resampled)] = resampled
        else:
            buf[:] = resampled[:clip_len]

        noise = np.random.normal(0, 80, clip_len).astype(np.int16)
        negative_clips.append(np.clip(buf.astype(np.int32) + noise, -32768, 32767).astype(np.int16))

    # Add pure silence and pure noise negatives
    for _ in range(5):
        negative_clips.append(np.zeros(clip_len, dtype=np.int16))
        negative_clips.append(np.random.normal(0, 150, clip_len).astype(np.int16))

    return positive_clips, negative_clips


# ---------------------------------------------------------------------------
# Training Pipeline
# ---------------------------------------------------------------------------

def train_openwakeword_model(
    positive_clips: List[np.ndarray],
    negative_clips: List[np.ndarray],
    output_onnx_path: Path,
    epochs: int = 15,
    batch_size: int = 16,
    learning_rate: float = 0.001,
) -> Path:
    """Extract features with openWakeWord AudioFeatures and train classifier."""
    try:
        from openwakeword.utils import AudioFeatures
    except ImportError as exc:
        raise RuntimeError("openwakeword is required. Run: pip install openwakeword") from exc

    logger.info("Initializing openWakeWord AudioFeatures embedding extractor...")
    feature_extractor = AudioFeatures(device="cpu")

    logger.info("Extracting embeddings for %d positive clips...", len(positive_clips))
    pos_arr = np.array(positive_clips, dtype=np.int16)
    pos_features = feature_extractor.embed_clips(pos_arr, batch_size=batch_size)  # (N_pos, 16, 96)

    logger.info("Extracting embeddings for %d negative clips...", len(negative_clips))
    neg_arr = np.array(negative_clips, dtype=np.int16)
    neg_features = feature_extractor.embed_clips(neg_arr, batch_size=batch_size)  # (N_neg, 16, 96)

    # Combine into dataset
    X = np.concatenate([pos_features, neg_features], axis=0)
    y = np.concatenate([np.ones(len(pos_features), dtype=np.float32), np.zeros(len(neg_features), dtype=np.float32)])

    # Shuffle
    indices = np.random.permutation(len(X))
    X = X[indices]
    y = y[indices]

    # Train / Val Split (80 / 20)
    split_idx = int(0.8 * len(X))
    X_train, X_val = torch.from_numpy(X[:split_idx]).float(), torch.from_numpy(X[split_idx:]).float()
    y_train, y_val = torch.from_numpy(y[:split_idx]).float().unsqueeze(1), torch.from_numpy(y[split_idx:]).float().unsqueeze(1)

    logger.info("Dataset prepared: %d training samples, %d validation samples.", len(X_train), len(X_val))

    # Initialize Model
    model = OpenWakeWordNet(input_shape=(16, 96), layer_dim=128, n_blocks=1, n_classes=1)
    criterion = nn.BCELoss()
    optimizer = optim.Adam(model.parameters(), lr=learning_rate)

    best_val_loss = float("inf")
    best_weights = copy.deepcopy(model.state_dict())

    # Training Loop
    logger.info("Starting training for %d epochs...", epochs)
    for epoch in range(1, epochs + 1):
        model.train()
        permutation = torch.randperm(X_train.size()[0])
        epoch_loss = 0.0
        num_batches = 0

        for i in range(0, X_train.size()[0], batch_size):
            b_indices = permutation[i : i + batch_size]
            batch_x, batch_y = X_train[b_indices], y_train[b_indices]

            optimizer.zero_grad()
            outputs = model(batch_x)
            loss = criterion(outputs, batch_y)
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item()
            num_batches += 1

        avg_train_loss = epoch_loss / max(1, num_batches)

        # Validation
        model.eval()
        with torch.no_grad():
            val_preds = model(X_val)
            val_loss = criterion(val_preds, y_val).item()
            val_acc = ((val_preds >= 0.5) == (y_val >= 0.5)).float().mean().item()

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_weights = copy.deepcopy(model.state_dict())

        logger.info(
            "Epoch %2d/%2d — Train Loss: %.4f | Val Loss: %.4f | Val Acc: %.1f%%",
            epoch, epochs, avg_train_loss, val_loss, val_acc * 100,
        )

    # Load best weights
    model.load_state_dict(best_weights)
    model.eval()

    # Export to ONNX
    output_onnx_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Exporting trained model to ONNX: %s", output_onnx_path)
    dummy_input = torch.rand((1, 16, 96), dtype=torch.float32)
    torch.onnx.export(
        model,
        dummy_input,
        str(output_onnx_path),
        export_params=True,
        opset_version=13,
        do_constant_folding=True,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {0: "batch_size"}, "output": {0: "batch_size"}},
    )

    logger.info("ONNX export complete! File size: %d bytes (%.2f KB)",
                output_onnx_path.stat().st_size, output_onnx_path.stat().st_size / 1024)
    return output_onnx_path


def main():
    parser = argparse.ArgumentParser(description="LUMI — Multi-Phrase openWakeWord Custom Model Trainer")
    parser.add_argument("--phrase", type=str, default="Hey LUMI",
                        choices=list(PHRASE_FILENAME_MAP.keys()),
                        help="Wake phrase to train for (one of the 8 authoritative phrases)")
    parser.add_argument("--generate-synthetic", action="store_true",
                        help="Generate synthetic samples with local Piper TTS")
    parser.add_argument("--output", type=str, default="",
                        help="Output ONNX path (default: models/wake_words/<filename>)")
    parser.add_argument("--epochs", type=int, default=15, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=16, help="Batch size")
    parser.add_argument("--lr", type=float, default=0.001, help="Learning rate")
    args = parser.parse_args()

    phrase = args.phrase
    default_filename = PHRASE_FILENAME_MAP.get(phrase, "hey_lumi.onnx")
    out_path = Path(args.output).resolve() if args.output else (REPO_ROOT / "models" / "wake_words" / default_filename)

    logger.info("Target wake phrase: '%s' -> %s", phrase, out_path)

    if args.generate_synthetic:
        logger.info("Generating synthetic training data for '%s'...", phrase)
        tmp_dir = REPO_ROOT / "output" / "training_tmp" / phrase.lower().replace(" ", "_").replace(",", "").replace("!", "").replace("?", "")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        pos, neg = generate_synthetic_samples_for_phrase(phrase, tmp_dir, num_positive=30, num_negative=60)
        train_openwakeword_model(pos, neg, out_path, epochs=args.epochs, batch_size=args.batch_size, lr=args.lr)
    else:
        logger.info(
            "No training audio provided. To train with local Piper synthetic speech, re-run with --generate-synthetic.\n"
            "NOTE: Synthetic-only training requires post-training validation against real multi-speaker audio."
        )


if __name__ == "__main__":
    main()
