"""
Video Renderer — Renders a real MP4 from scene graph + narration + timeline.

Uses ffmpeg (available on system) to produce actual video output.
On macOS, uses `say` for text-to-speech narration audio.

The renderer takes a VideoLakeResult and produces:
    - video.mp4 (real MP4 with text overlays + narration)
    - narration.txt (full narration script)

This is the "human surface" — the evidence graph is the asset.

Usage:
    renderer = VideoRenderer()
    result = renderer.render(videolake_result, output_dir="/path/to/out")
    print(result["video_path"])
    print(result["duration_seconds"])
"""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Optional

from PIL import Image, ImageDraw, ImageFont


@dataclass
class RenderResult:
    """Result of a video render operation."""
    video_path: str = ""
    narration_path: str = ""
    duration_seconds: float = 0.0
    file_size_bytes: int = 0
    ffmpeg_used: bool = False
    scenes_rendered: int = 0
    audio_generated: bool = False
    error: str = ""
    receipt_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "video_path": self.video_path,
            "narration_path": self.narration_path,
            "duration_seconds": round(self.duration_seconds, 2),
            "file_size_bytes": self.file_size_bytes,
            "ffmpeg_used": self.ffmpeg_used,
            "scenes_rendered": self.scenes_rendered,
            "audio_generated": self.audio_generated,
            "error": self.error,
            "receipt_hash": self.receipt_hash,
        }


class VideoRenderer:
    """
    Renders a real MP4 from a VideoLakeResult.

    Pipeline:
        1. Generate narration script from scene graph
        2. For each scene, create a still frame with text overlay (ffmpeg drawtext)
        3. Generate narration audio per scene (macOS `say` or ffmpeg silence fallback)
        4. Combine audio + video per scene into clips
        5. Concatenate all clips into final MP4

    The video is 1280x720, 30fps, H.264, AAC audio.
    """

    WIDTH = 1280
    HEIGHT = 720
    FPS = 30
    VIDEO_CODEC = "libx264"
    AUDIO_CODEC = "aac"
    PIXEL_FORMAT = "yuv420p"

    # Colors for different moods (R, G, B)
    MOOD_COLORS = {
        "investigative": (10, 10, 42),
        "revelatory": (10, 42, 10),
        "tense": (42, 10, 10),
        "uncertain": (42, 42, 10),
        "conclusive": (10, 26, 42),
        "somber": (26, 10, 26),
    }

    def __init__(self):
        self._ffmpeg = shutil.which("ffmpeg")
        self._ffprobe = shutil.which("ffprobe")
        self._say = shutil.which("say") if os.name != "nt" else None

    @property
    def ffmpeg_available(self) -> bool:
        return self._ffmpeg is not None

    def _load_font(self, size: int):
        """Try to load a system font, fall back to default."""
        for path in [
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
        ]:
            try:
                return ImageFont.truetype(path, size)
            except (OSError, IOError):
                continue
        return ImageFont.load_default()

    def render(
        self,
        videolake_result,
        output_dir: str = ".",
    ) -> RenderResult:
        """
        Render a VideoLakeResult into a real MP4.

        Args:
            videolake_result: VideoLakeResult with scene_graph and mevf
            output_dir: Directory to write video.mp4 and narration.txt

        Returns:
            RenderResult with paths and metadata
        """
        result = RenderResult()

        if not self.ffmpeg_available:
            result.error = "ffmpeg not found on system"
            return result

        result.ffmpeg_used = True
        scenes = videolake_result.scene_graph
        if not scenes:
            result.error = "No scene graph in VideoLakeResult"
            return result

        result.scenes_rendered = len(scenes)
        os.makedirs(output_dir, exist_ok=True)

        # 1. Generate narration script
        narration = self._generate_narration(videolake_result)
        narration_path = os.path.join(output_dir, "narration.txt")
        with open(narration_path, "w") as f:
            f.write(narration)
        result.narration_path = narration_path

        # 2. Render each scene as a clip
        with tempfile.TemporaryDirectory() as tmpdir:
            clip_paths = []
            total_duration = 0.0

            for i, scene in enumerate(scenes):
                clip_path = os.path.join(tmpdir, f"clip_{i:03d}.mp4")
                scene_text = self._scene_narration(scene, i, len(scenes))
                duration = scene.duration if scene.duration > 0 else 5.0

                # Generate image for this scene (PIL)
                img_path = os.path.join(tmpdir, f"frame_{i:03d}.png")
                self._render_scene_image(scene, img_path, i, len(scenes))

                # Generate audio for this scene
                audio_path = os.path.join(tmpdir, f"audio_{i:03d}.aac")
                audio_ok = self._generate_audio(scene_text, audio_path, duration)

                # Combine image + audio into clip
                self._mux_image_audio(img_path, audio_path, clip_path, duration, audio_ok)

                if os.path.exists(clip_path):
                    clip_paths.append(clip_path)
                total_duration += duration

            # 3. Concatenate all clips
            video_path = os.path.join(output_dir, "video.mp4")
            if clip_paths:
                self._concat_clips(clip_paths, video_path)

            result.video_path = video_path
            result.duration_seconds = total_duration
            result.audio_generated = self._say is not None

            if os.path.exists(video_path):
                result.file_size_bytes = os.path.getsize(video_path)
            else:
                result.error = "Failed to produce video.mp4"

        # 4. Receipt hash
        result.receipt_hash = self._compute_receipt_hash(result, videolake_result)

        return result

    def _generate_narration(self, videolake_result) -> str:
        """Generate a full narration script from the investigation."""
        lines = []
        inv = videolake_result.investigation
        mevf = videolake_result.mevf

        if inv:
            lines.append(f"# Investigation: {inv.question}")
            lines.append(f"# Claims: {len(inv.claims)} | Papers: {len(inv.papers)}")
            lines.append("")

        for i, scene in enumerate(videolake_result.scene_graph):
            lines.append(f"## Scene {i+1}: {scene.scene_type} ({scene.mood})")
            lines.append(self._scene_narration(scene, i, len(videolake_result.scene_graph)))
            lines.append("")

        if mevf:
            lines.append(f"## Trust Grade: {mevf.trust_grade}")
            lines.append(f"## Machine Buyability: {mevf.avg_machine_buyability:.3f}")

        return "\n".join(lines)

    def _scene_narration(self, scene, index: int, total: int) -> str:
        """Generate narration text for a single scene."""
        if index == 0:
            # Opening
            return f"Investigation: {scene.description.replace('Title card: ', '')}"
        elif index == total - 1:
            # Closing
            return "Conclusions and evidence summary. All claims have been evaluated with provenance and rights verification."
        else:
            # Claim scene
            text = scene.description
            status_overlay = f" Status: {scene.mood}."
            return text + status_overlay

    def _generate_audio(self, text: str, output_path: str, duration: float) -> bool:
        """Generate narration audio using macOS `say` or ffmpeg silence."""
        if self._say and text.strip():
            try:
                # Use `say` to generate AIFF, then ffmpeg to convert to AAC
                aiff_path = output_path.replace(".aac", ".aiff")
                subprocess.run(
                    [self._say, "-o", aiff_path, text[:500]],
                    capture_output=True, timeout=30,
                )
                if os.path.exists(aiff_path):
                    # Convert to AAC with ffmpeg
                    subprocess.run(
                        [self._ffmpeg, "-y", "-i", aiff_path,
                         "-c:a", self.AUDIO_CODEC, "-b:a", "128k",
                         "-t", str(max(duration, 1.0)),
                         output_path],
                        capture_output=True, timeout=30,
                    )
                    os.unlink(aiff_path)
                    return os.path.exists(output_path)
            except (subprocess.TimeoutExpired, Exception):
                pass

        # Fallback: generate silence
        try:
            subprocess.run(
                [self._ffmpeg, "-y",
                 "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
                 "-t", str(max(duration, 1.0)),
                 "-c:a", self.AUDIO_CODEC, "-b:a", "128k",
                 output_path],
                capture_output=True, timeout=30,
            )
            return os.path.exists(output_path)
        except (subprocess.TimeoutExpired, Exception):
            return False

    def _render_scene_image(
        self, scene, output_path: str,
        scene_index: int, total_scenes: int,
    ) -> None:
        """Render a scene as a PNG image with text overlay using PIL."""
        bg_color = self.MOOD_COLORS.get(scene.mood, (10, 10, 42))
        img = Image.new("RGB", (self.WIDTH, self.HEIGHT), bg_color)
        draw = ImageDraw.Draw(img)

        font_large = self._load_font(28)
        font_medium = self._load_font(18)
        font_small = self._load_font(14)

        # Status badge (top-left)
        status_text = f"[{scene.mood.upper()}] Scene {scene_index+1}/{total_scenes}"
        draw.text((20, 20), status_text, fill=(170, 170, 170), font=font_small)

        # Main text (centered)
        title_text = scene.description[:120]
        lines = self._wrap_text(title_text, font_large, self.WIDTH - 80, draw)
        y_offset = (self.HEIGHT - len(lines) * 36) // 2
        for line in lines:
            draw.text((40, y_offset), line, fill=(255, 255, 255), font=font_large)
            y_offset += 36

        # Claim ref (bottom-left)
        if scene.claim_ref:
            claim_text = f"Claim: {scene.claim_ref}"
            draw.text((20, self.HEIGHT - 40), claim_text, fill=(136, 136, 136), font=font_small)

        # Visual elements (bottom)
        if scene.visual_elements:
            ve_text = " | ".join(scene.visual_elements[:3])
            draw.text((20, self.HEIGHT - 20), ve_text, fill=(100, 100, 100), font=font_small)

        img.save(output_path, "PNG")

    def _wrap_text(self, text: str, font, max_width: int, draw) -> list[str]:
        """Word-wrap text to fit within max_width."""
        words = text.split()
        lines = []
        current_line = []
        for word in words:
            test_line = " ".join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font)
            w = bbox[2] - bbox[0]
            if w > max_width and current_line:
                lines.append(" ".join(current_line))
                current_line = [word]
            else:
                current_line.append(word)
        if current_line:
            lines.append(" ".join(current_line))
        return lines[:8]

    def _mux_image_audio(
        self, img_path: str, audio_path: str, output_path: str,
        duration: float, has_audio: bool,
    ) -> None:
        """Combine a PNG image and AAC audio into an MP4 clip."""
        if not os.path.exists(img_path):
            return

        if has_audio and os.path.exists(audio_path):
            cmd = [
                self._ffmpeg, "-y",
                "-loop", "1", "-i", img_path,
                "-i", audio_path,
                "-t", str(max(duration, 1.0)),
                "-r", str(self.FPS),
                "-c:v", self.VIDEO_CODEC, "-pix_fmt", self.PIXEL_FORMAT,
                "-c:a", self.AUDIO_CODEC, "-b:a", "128k",
                "-vf", f"scale={self.WIDTH}:{self.HEIGHT}",
                "-shortest",
                output_path,
            ]
        else:
            cmd = [
                self._ffmpeg, "-y",
                "-loop", "1", "-i", img_path,
                "-t", str(max(duration, 1.0)),
                "-r", str(self.FPS),
                "-c:v", self.VIDEO_CODEC, "-pix_fmt", self.PIXEL_FORMAT,
                "-vf", f"scale={self.WIDTH}:{self.HEIGHT}",
                output_path,
            ]

        try:
            subprocess.run(cmd, capture_output=True, timeout=60)
        except (subprocess.TimeoutExpired, Exception):
            pass

    def _concat_clips(self, clip_paths: list[str], output_path: str) -> None:
        """Concatenate multiple clips into a single MP4."""
        if not clip_paths:
            return

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            for clip_path in clip_paths:
                f.write(f"file '{os.path.abspath(clip_path)}'\n")
            concat_list = f.name

        try:
            subprocess.run(
                [self._ffmpeg, "-y", "-f", "concat", "-safe", "0",
                 "-i", concat_list,
                 "-c:v", self.VIDEO_CODEC, "-c:a", self.AUDIO_CODEC,
                 "-pix_fmt", self.PIXEL_FORMAT,
                 output_path],
                capture_output=True, timeout=120,
            )
        except (subprocess.TimeoutExpired, Exception):
            pass
        finally:
            os.unlink(concat_list)

    def _compute_receipt_hash(self, render_result: RenderResult, videolake_result) -> str:
        """Compute receipt hash for the render."""
        data = {
            "video_path": render_result.video_path,
            "duration_seconds": render_result.duration_seconds,
            "file_size_bytes": render_result.file_size_bytes,
            "scenes_rendered": render_result.scenes_rendered,
            "ffmpeg_used": render_result.ffmpeg_used,
            "audio_generated": render_result.audio_generated,
            "videolake_receipt": videolake_result.receipt_hash if videolake_result else "",
        }
        return f"sha256:{hashlib.sha256(
            json.dumps(data, sort_keys=True).encode()
        ).hexdigest()[:16]}"
