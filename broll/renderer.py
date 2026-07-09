"""
MP4 Renderer — Turns scene graphs into real video files.

Uses ffmpeg + PIL for frame generation + macOS `say` for narration TTS.

Pipeline:
    SceneGraph
    → Generate frames (PIL, one PNG per scene)
    → Generate narration audio (macOS say → AIFF → ffmpeg → AAC)
    → Concatenate frames + audio into MP4 (ffmpeg)

The MP4 is the human surface. The evidence graph is the asset.
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
    """Result of an MP4 render operation."""
    mp4_path: str = ""
    audio_path: str = ""
    duration_seconds: float = 0.0
    frame_count: int = 0
    audio_generated: bool = False
    narration_text: str = ""
    ffmpeg_used: bool = False
    receipt_hash: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "mp4_path": self.mp4_path,
            "audio_path": self.audio_path,
            "duration_seconds": round(self.duration_seconds, 2),
            "frame_count": self.frame_count,
            "audio_generated": self.audio_generated,
            "narration_length": len(self.narration_text),
            "ffmpeg_used": self.ffmpeg_used,
            "receipt_hash": self.receipt_hash,
            "error": self.error,
        }


class MP4Renderer:
    """
    Renders a scene graph into a real MP4 video file.

    Each scene becomes a sequence of frames:
        - Text overlay scenes → title card with question/conclusion text
        - Footage scenes → placeholder with claim text + status badge
        - Simulation scenes → animated gradient with description
        - Diagram scenes → chart placeholder with data
        - Experiment scenes → lab setup placeholder

    Narration is generated via macOS `say` command (TTS).
    Final mux is done with ffmpeg.

    Usage:
        renderer = MP4Renderer()
        result = renderer.render(scene_graph, output_path="video.mp4")
    """

    WIDTH = 1920
    HEIGHT = 1080
    FPS = 30
    BG_COLOR = (15, 15, 25)
    TEXT_COLOR = (235, 235, 245)
    ACCENT_COLOR = (100, 180, 255)
    WARNING_COLOR = (255, 180, 80)
    DANGER_COLOR = (255, 100, 100)
    SUCCESS_COLOR = (100, 255, 150)

    STATUS_COLORS = {
        "verified": (100, 255, 150),
        "replicated": (100, 255, 150),
        "partially_replicated": (180, 220, 100),
        "disputed": (255, 180, 80),
        "speculative": (255, 180, 80),
        "unverified": (200, 200, 200),
        "retracted": (255, 100, 100),
    }

    MOOD_GRADIENTS = {
        "investigative": [(20, 30, 50), (40, 50, 80)],
        "revelatory": [(20, 50, 30), (40, 80, 50)],
        "tense": [(50, 20, 20), (80, 40, 40)],
        "uncertain": [(40, 35, 20), (60, 55, 35)],
        "conclusive": [(20, 25, 40), (35, 45, 70)],
        "somber": [(25, 20, 30), (40, 35, 45)],
    }

    def __init__(self, fps: int = 30, width: int = 1920, height: int = 1080):
        self.fps = fps
        self.width = width
        self.height = height

    def render(
        self,
        scene_graph: list,
        output_path: str,
        narration: bool = True,
        voice: str = "Alex",
    ) -> RenderResult:
        """
        Render a scene graph into an MP4 file.

        Uses per-scene clips: one PIL frame per scene → ffmpeg loop → concat.
        This avoids the drawtext filter (not available in all ffmpeg builds).

        Args:
            scene_graph: List of SceneNode dicts (from VideoLakeCompiler)
            output_path: Path to output .mp4 file
            narration: Whether to generate TTS narration
            voice: macOS say voice name

        Returns:
            RenderResult with render details
        """
        result = RenderResult()

        if not scene_graph:
            result.error = "Empty scene graph"
            return result

        has_ffmpeg = shutil.which("ffmpeg") is not None
        has_say = shutil.which("say") is not None
        result.ffmpeg_used = has_ffmpeg

        if not has_ffmpeg:
            result.error = "ffmpeg not found"
            return result

        tmpdir = tempfile.mkdtemp(prefix="videolake_render_")

        try:
            # 1. Generate one representative frame per scene
            scene_pngs = []
            for i, scene in enumerate(scene_graph):
                frame = self._render_frame(scene, 0.5, 0, 1)
                png_path = os.path.join(tmpdir, f"scene_{i:03d}.png")
                frame.save(png_path)
                scene_pngs.append(png_path)
            result.frame_count = len(scene_pngs)

            # 2. Generate narration audio
            audio_path = None
            if narration and has_say:
                narration_text = self._build_narration(scene_graph)
                result.narration_text = narration_text
                audio_path = self._generate_narration_audio(
                    narration_text, tmpdir, voice, has_ffmpeg
                )
                result.audio_generated = audio_path is not None

            # 3. Calculate total duration
            total_duration = sum(s.get("duration", 10.0) for s in scene_graph)
            result.duration_seconds = total_duration

            # 4. Render: per-scene clips → concat
            self._render_scenes_to_mp4(
                scene_pngs, scene_graph, audio_path, output_path, tmpdir
            )

            if os.path.exists(output_path):
                result.mp4_path = output_path
            else:
                result.error = "ffmpeg render failed"

            # 5a. Save audio file alongside video
            if audio_path and os.path.exists(audio_path):
                audio_out = output_path.replace(".mp4", ".wav")
                if audio_path.endswith(".aiff") and has_ffmpeg:
                    subprocess.run([
                        "ffmpeg", "-y", "-i", audio_path, audio_out,
                    ], capture_output=True, timeout=30)
                elif audio_path.endswith(".aac"):
                    subprocess.run([
                        "ffmpeg", "-y", "-i", audio_path, audio_out,
                    ], capture_output=True, timeout=30)
                else:
                    shutil.copy2(audio_path, audio_out)
                if os.path.exists(audio_out):
                    result.audio_path = audio_out

            # 5. Receipt
            receipt_data = {
                "mp4_path": output_path,
                "duration": total_duration,
                "scenes": len(scene_pngs),
                "audio": result.audio_generated,
                "ffmpeg": has_ffmpeg,
                "timestamp": time.time(),
            }
            result.receipt_hash = f"sha256:{hashlib.sha256(
                json.dumps(receipt_data, sort_keys=True).encode()
            ).hexdigest()[:16]}"

        except Exception as e:
            result.error = str(e)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        return result

    def _generate_all_frames(
        self,
        scene_graph: list[dict],
        tmpdir: str,
    ) -> list[str]:
        """Generate PNG frames for each scene."""
        frame_paths = []
        for i, scene in enumerate(scene_graph):
            duration = scene.get("duration", 10.0)
            num_frames = max(1, int(duration * self.fps))
            scene_dir = os.path.join(tmpdir, f"scene_{i:03d}")
            os.makedirs(scene_dir, exist_ok=True)

            for f in range(num_frames):
                progress = f / num_frames if num_frames > 1 else 0
                frame = self._render_frame(scene, progress, f, num_frames)
                frame_path = os.path.join(scene_dir, f"frame_{f:05d}.png")
                frame.save(frame_path)
                frame_paths.append(frame_path)

        return frame_paths

    def _render_frame(
        self,
        scene: dict,
        progress: float,
        frame_idx: int,
        total_frames: int,
    ) -> Image.Image:
        """Render a single frame for a scene."""
        scene_type = scene.get("scene_type", "text_overlay")
        mood = scene.get("mood", "investigative")

        img = Image.new("RGB", (self.width, self.height), self.BG_COLOR)
        draw = ImageDraw.Draw(img)

        # Apply mood gradient background
        self._draw_gradient(draw, mood, progress)

        # Render based on scene type
        if scene_type == "text_overlay":
            self._draw_text_overlay(draw, scene)
        elif scene_type == "simulation":
            self._draw_simulation(draw, scene, progress)
        elif scene_type == "diagram":
            self._draw_diagram(draw, scene, progress)
        elif scene_type == "experiment":
            self._draw_experiment(draw, scene, progress)
        else:
            self._draw_footage(draw, scene, progress)

        # Draw progress bar at bottom
        self._draw_progress_bar(draw, progress)

        # Draw scene ID watermark
        self._draw_watermark(draw, scene)

        return img

    def _draw_gradient(self, draw: ImageDraw.Draw, mood: str, progress: float) -> None:
        """Draw a vertical gradient background based on mood."""
        colors = self.MOOD_GRADIENTS.get(mood, self.MOOD_GRADIENTS["investigative"])
        top, bottom = colors[0], colors[1]
        steps = 50
        for i in range(steps):
            y0 = int(self.height * i / steps)
            y1 = int(self.height * (i + 1) / steps)
            ratio = i / steps
            r = int(top[0] + (bottom[0] - top[0]) * ratio)
            g = int(top[1] + (bottom[1] - top[1]) * ratio)
            b = int(top[2] + (bottom[2] - top[2]) * ratio)
            draw.rectangle([(0, y0), (self.width, y1)], fill=(r, g, b))

    def _get_font(self, size: int) -> ImageFont.FreeTypeFont:
        """Get a font, falling back to default if needed."""
        font_paths = [
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Helvetica.ttf",
        ]
        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    return ImageFont.truetype(fp, size)
                except Exception:
                    continue
        return ImageFont.load_default()

    def _wrap_text(self, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
        """Wrap text to fit within max_width."""
        words = text.split()
        lines = []
        current = ""
        for word in words:
            test = current + " " + word if current else word
            bbox = font.getbbox(test)
            if bbox[2] - bbox[0] > max_width and current:
                lines.append(current)
                current = word
            else:
                current = test
        if current:
            lines.append(current)
        return lines

    def _draw_text_overlay(self, draw: ImageDraw.Draw, scene: dict) -> None:
        """Draw a text overlay scene (title card or conclusion)."""
        description = scene.get("description", "")
        font_large = self._get_font(48)
        font_small = self._get_font(28)

        lines = self._wrap_text(description, font_large, self.width - 200)
        total_height = len(lines) * 60
        y_start = (self.height - total_height) // 2

        for i, line in enumerate(lines):
            y = y_start + i * 60
            draw.text((100, y), line, fill=self.TEXT_COLOR, font=font_large)

        # Draw visual elements as bullet points
        elements = scene.get("visual_elements", [])
        if elements:
            y = y_start + total_height + 40
            for elem in elements[:5]:
                draw.text((120, y), f"  {elem}", fill=self.ACCENT_COLOR, font=font_small)
                y += 36

    def _draw_footage(self, draw: ImageDraw.Draw, scene: dict, progress: float) -> None:
        """Draw a footage scene placeholder."""
        description = scene.get("description", "")
        claim_ref = scene.get("claim_ref", "")
        font = self._get_font(36)
        font_small = self._get_font(24)

        # Draw a "camera viewfinder" frame
        margin = 80
        draw.rectangle(
            [(margin, margin), (self.width - margin, self.height - margin)],
            outline=self.ACCENT_COLOR, width=3,
        )

        # Corner brackets
        bracket_len = 40
        for cx, cy in [(margin, margin), (self.width - margin, margin),
                       (margin, self.height - margin), (self.width - margin, self.height - margin)]:
            dx = bracket_len if cx < self.width // 2 else -bracket_len
            dy = bracket_len if cy < self.height // 2 else -bracket_len
            draw.line([(cx, cy), (cx + dx, cy)], fill=self.ACCENT_COLOR, width=3)
            draw.line([(cx, cy), (cx, cy + dy)], fill=self.ACCENT_COLOR, width=3)

        # Description text
        lines = self._wrap_text(description, font, self.width - 200)
        y = self.height // 2 - len(lines) * 25
        for line in lines:
            draw.text((100, y), line, fill=self.TEXT_COLOR, font=font)
            y += 45

        # Claim reference
        if claim_ref:
            draw.text((100, self.height - 120), f"Segment: {claim_ref}",
                      fill=self.ACCENT_COLOR, font=font_small)

    def _draw_simulation(self, draw: ImageDraw.Draw, scene: dict, progress: float) -> None:
        """Draw a simulation scene with animated waveform."""
        font = self._get_font(32)
        font_small = self._get_font(24)

        description = scene.get("description", "")
        lines = self._wrap_text(description, font, self.width - 200)
        y = 80
        for line in lines:
            draw.text((100, y), line, fill=self.TEXT_COLOR, font=font)
            y += 40

        # Draw animated waveform
        import math
        wave_y = self.height // 2 + 50
        wave_points = []
        for x in range(100, self.width - 100, 2):
            phase = (x / 200) + progress * 4 * math.pi
            amplitude = 80 * (0.5 + 0.5 * math.sin(progress * 2 * math.pi))
            y_off = int(amplitude * math.sin(phase))
            wave_points.append((x, wave_y + y_off))

        if len(wave_points) > 1:
            draw.line(wave_points, fill=self.ACCENT_COLOR, width=2)

        # Draw frequency labels
        for i in range(5):
            x = 100 + i * (self.width - 200) // 4
            freq_label = f"{7.83 * (i + 1):.1f} Hz"
            draw.text((x, wave_y + 120), freq_label, fill=self.ACCENT_COLOR, font=font_small)

    def _draw_diagram(self, draw: ImageDraw.Draw, scene: dict, progress: float) -> None:
        """Draw a diagram scene with chart placeholder."""
        font = self._get_font(32)
        font_small = self._get_font(24)

        description = scene.get("description", "")
        draw.text((100, 80), description[:80], fill=self.TEXT_COLOR, font=font)

        # Draw bar chart
        chart_x = 150
        chart_y = 200
        chart_w = self.width - 300
        chart_h = self.height - 350
        draw.rectangle(
            [(chart_x, chart_y), (chart_x + chart_w, chart_y + chart_h)],
            outline=(60, 70, 90), width=2,
        )

        bar_count = 6
        bar_w = chart_w // (bar_count * 2)
        for i in range(bar_count):
            bar_h = int(chart_h * (0.3 + 0.5 * ((i + 1) / bar_count) * progress))
            bx = chart_x + (i * 2 + 1) * bar_w
            by = chart_y + chart_h - bar_h
            color_intensity = int(100 + 155 * (i / bar_count))
            draw.rectangle(
                [(bx, by), (bx + bar_w, chart_y + chart_h)],
                fill=(50, color_intensity, 150),
            )
            draw.text((bx, chart_y + chart_h + 10), f"S{i+1}",
                      fill=self.TEXT_COLOR, font=font_small)

    def _draw_experiment(self, draw: ImageDraw.Draw, scene: dict, progress: float) -> None:
        """Draw an experiment scene placeholder."""
        font = self._get_font(32)
        font_small = self._get_font(24)

        description = scene.get("description", "")
        draw.text((100, 80), "EXPERIMENT", fill=self.WARNING_COLOR, font=self._get_font(48))
        lines = self._wrap_text(description, font, self.width - 200)
        y = 160
        for line in lines:
            draw.text((100, y), line, fill=self.TEXT_COLOR, font=font)
            y += 40

        # Draw measurement device
        device_x = self.width // 2 - 200
        device_y = self.height // 2
        draw.rectangle(
            [(device_x, device_y), (device_x + 400, device_y + 150)],
            outline=self.SUCCESS_COLOR, width=3,
        )
        reading = f"{67.83 + 10 * progress:.2f} Hz"
        draw.text((device_x + 50, device_y + 30), reading,
                  fill=self.SUCCESS_COLOR, font=self._get_font(56))
        draw.text((device_x + 50, device_y + 100), "Schumann Resonance Monitor",
                  fill=self.TEXT_COLOR, font=font_small)

    def _draw_progress_bar(self, draw: ImageDraw.Draw, progress: float) -> None:
        """Draw a progress bar at the bottom of the frame."""
        bar_y = self.height - 8
        bar_w = int(self.width * progress)
        draw.rectangle([(0, bar_y), (self.width, self.height)], fill=(30, 30, 40))
        draw.rectangle([(0, bar_y), (bar_w, self.height)], fill=self.ACCENT_COLOR)

    def _draw_watermark(self, draw: ImageDraw.Draw, scene: dict) -> None:
        """Draw scene ID and timestamp watermark."""
        font = self._get_font(18)
        scene_id = scene.get("scene_id", "")
        timestamp = scene.get("timestamp", 0.0)
        text = f"{scene_id}  t={timestamp:.1f}s  VideoLake"
        draw.text((self.width - 350, 20), text, fill=(80, 80, 100), font=font)

    def _build_narration(self, scene_graph: list[dict]) -> str:
        """Build narration text from scene graph."""
        parts = []
        for scene in scene_graph:
            scene_type = scene.get("scene_type", "")
            description = scene.get("description", "")
            mood = scene.get("mood", "investigative")

            if scene_type == "text_overlay":
                parts.append(description)
            else:
                claim_ref = scene.get("claim_ref", "")
                parts.append(f"Next: {description}")
                if claim_ref:
                    parts.append(f"Evidence segment {claim_ref}.")

        return ". ".join(parts)

    def _generate_narration_audio(
        self,
        text: str,
        tmpdir: str,
        voice: str,
        has_ffmpeg: bool,
    ) -> Optional[str]:
        """Generate narration audio using macOS say + ffmpeg."""
        if not text.strip():
            return None

        aiff_path = os.path.join(tmpdir, "narration.aiff")
        try:
            subprocess.run(
                ["say", "-v", voice, "-o", aiff_path, text[:3000],
                 "-r", "180"],
                capture_output=True, timeout=30,
            )
        except Exception:
            return None

        if not os.path.exists(aiff_path):
            return None

        if has_ffmpeg:
            aac_path = os.path.join(tmpdir, "narration.aac")
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", aiff_path, "-codec:a", "aac",
                     "-b:a", "128k", aac_path],
                    capture_output=True, timeout=30,
                )
                if os.path.exists(aac_path):
                    return aac_path
            except Exception:
                pass

        return aiff_path

    def _render_scenes_to_mp4(
        self,
        scene_pngs: list[str],
        scene_graph: list[dict],
        audio_path: Optional[str],
        output_path: str,
        tmpdir: str,
    ) -> None:
        """Render per-scene clips then concat into final MP4."""
        clip_paths = []

        for i, (png_path, scene) in enumerate(zip(scene_pngs, scene_graph)):
            duration = max(scene.get("duration", 10.0), 1.0)
            clip_path = os.path.join(tmpdir, f"clip_{i:03d}.mp4")

            # Per-scene narration audio
            scene_audio = None
            if audio_path and os.path.exists(audio_path):
                # Use the full narration audio, will be muxed at the end
                pass

            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", png_path,
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-r", str(self.fps),
                "-t", str(duration),
                "-preset", "fast",
                "-crf", "28",
                clip_path,
            ]
            subprocess.run(cmd, capture_output=True, timeout=60)

            if os.path.exists(clip_path) and os.path.getsize(clip_path) > 0:
                clip_paths.append(clip_path)

        if not clip_paths:
            return

        # Concat all clips
        concat_file = os.path.join(tmpdir, "concat.txt")
        with open(concat_file, "w") as f:
            for cp in clip_paths:
                f.write(f"file '{os.path.abspath(cp)}'\n")

        # Final concat: video-only, then mux audio if available
        video_only = os.path.join(tmpdir, "video_only.mp4")
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_file, "-c", "copy", video_only,
        ], capture_output=True, timeout=120)

        if not os.path.exists(video_only):
            return

        # Mux audio if available, otherwise just copy video
        if audio_path and os.path.exists(audio_path):
            subprocess.run([
                "ffmpeg", "-y",
                "-i", video_only, "-i", audio_path,
                "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                "-shortest", output_path,
            ], capture_output=True, timeout=120)
        else:
            # Add silent audio track
            total_dur = sum(s.get("duration", 10.0) for s in scene_graph)
            subprocess.run([
                "ffmpeg", "-y",
                "-i", video_only,
                "-f", "lavfi", "-i",
                f"anullsrc=channel_layout=stereo:sample_rate=44100",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                "-t", str(total_dur),
                "-shortest", output_path,
            ], capture_output=True, timeout=120)

        # Fallback: if mux failed, just copy video_only
        if not os.path.exists(output_path) and os.path.exists(video_only):
            shutil.copy2(video_only, output_path)

    def _render_fallback(
        self,
        scene_pngs: list[str],
        scene_graph: list[dict],
        output_path: str,
        tmpdir: str,
    ) -> None:
        """Fallback: save first frame as PNG if ffmpeg not available."""
        if scene_pngs:
            png_path = output_path.replace(".mp4", ".png")
            shutil.copy2(scene_pngs[0], png_path)
            manifest_path = output_path.replace(".mp4", "_render_manifest.json")
            with open(manifest_path, "w") as f:
                json.dump({
                    "error": "ffmpeg not available",
                    "frames_generated": len(scene_pngs),
                    "first_frame": png_path,
                    "total_duration": sum(s.get("duration", 10.0) for s in scene_graph),
                }, f, indent=2)
