from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.scenario_runner import ScenarioRunner
from app.session_service import SessionManager


SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg"}


class AudioResult(BaseModel):
    success: bool
    transcript: str = ""
    language: str | None = None
    duration_seconds: float | None = None
    confidence: float | None = None
    file_path: str | None = None
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AudioService:
    def __init__(
        self,
        scenario_runner: ScenarioRunner | None = None,
        session_manager: SessionManager | None = None,
        model_name: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        temporary_directory: str | None = None,
    ) -> None:
        self.scenario_runner = scenario_runner
        self.session_manager = (
            session_manager
            if session_manager is not None
            else scenario_runner.session_manager if scenario_runner is not None else None
        )
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.temporary_directory = Path(
            temporary_directory or tempfile.gettempdir()
        )
        self._model: Any | None = None
        self._model_lock = asyncio.Lock()

    async def transcribe_audio(
        self,
        audio_path: str,
        language: str | None = None,
    ) -> AudioResult:
        validation = await self.validate_audio(audio_path)
        if not validation.success:
            return validation

        try:
            model = await self._get_model()
            segments, info = await asyncio.to_thread(
                model.transcribe,
                audio_path,
                language=language,
            )
            segment_list = list(segments)
            transcript = " ".join(segment.text.strip() for segment in segment_list)
            confidence = self._calculate_confidence(segment_list)

            return AudioResult(
                success=True,
                transcript=transcript.strip(),
                language=getattr(info, "language", language),
                duration_seconds=getattr(info, "duration", None),
                confidence=confidence,
                file_path=audio_path,
                metadata={
                    "model": self.model_name,
                    "segments": len(segment_list),
                },
            )
        except ImportError as exc:
            return AudioResult(
                success=False,
                file_path=audio_path,
                errors=[str(exc)],
            )
        except Exception as exc:
            return AudioResult(
                success=False,
                file_path=audio_path,
                errors=[f"audio transcription failed: {exc}"],
            )

    async def save_temporary_audio(
        self,
        audio_bytes: bytes,
        filename: str,
    ) -> AudioResult:
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_AUDIO_EXTENSIONS:
            return AudioResult(
                success=False,
                errors=[f"unsupported audio format '{suffix}'"],
                metadata={"supported_formats": sorted(SUPPORTED_AUDIO_EXTENSIONS)},
            )

        try:
            self.temporary_directory.mkdir(parents=True, exist_ok=True)
            audio_path = self.temporary_directory / f"{uuid4()}{suffix}"
            await asyncio.to_thread(audio_path.write_bytes, audio_bytes)
            return AudioResult(success=True, file_path=str(audio_path))
        except OSError as exc:
            return AudioResult(
                success=False,
                errors=[f"failed to save temporary audio: {exc}"],
            )

    async def cleanup_audio(self, audio_path: str) -> AudioResult:
        path = Path(audio_path)
        try:
            if path.exists():
                await asyncio.to_thread(path.unlink)
            return AudioResult(success=True, file_path=audio_path)
        except OSError as exc:
            return AudioResult(
                success=False,
                file_path=audio_path,
                errors=[f"failed to cleanup audio: {exc}"],
            )

    async def validate_audio(self, audio_path: str) -> AudioResult:
        path = Path(audio_path)
        errors: list[str] = []

        if not path.exists():
            errors.append("audio file does not exist")

        if not path.is_file():
            errors.append("audio path is not a file")

        if path.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
            errors.append(f"unsupported audio format '{path.suffix.lower()}'")

        if errors:
            return AudioResult(
                success=False,
                file_path=audio_path,
                errors=errors,
                metadata={"supported_formats": sorted(SUPPORTED_AUDIO_EXTENSIONS)},
            )

        return AudioResult(success=True, file_path=audio_path)

    async def _get_model(self) -> Any:
        async with self._model_lock:
            if self._model is not None:
                return self._model

            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise ImportError(
                    "faster-whisper is not installed; install it to enable "
                    "audio transcription"
                ) from exc

            self._model = await asyncio.to_thread(
                WhisperModel,
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
            )
            return self._model

    def _calculate_confidence(self, segments: list[Any]) -> float | None:
        probabilities = [
            float(segment.avg_logprob)
            for segment in segments
            if getattr(segment, "avg_logprob", None) is not None
        ]
        if not probabilities:
            return None

        return sum(probabilities) / len(probabilities)
