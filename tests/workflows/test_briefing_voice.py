from unittest.mock import MagicMock

from app.briefing.voice import synthesize_speech
from app.workflows.briefing import BriefingActivities
from tests.fakes import FakeNotifier


def boom(text: str) -> bytes:
    raise RuntimeError("elevenlabs down")


async def test_voice_note_follows_text(sessionmaker):
    heard, notifier = [], FakeNotifier()

    def speak(text: str) -> bytes:
        heard.append(text)
        return b"mp3"

    await BriefingActivities(
        sessionmaker, notifier, "Asia/Kolkata", synthesize=speak
    ).send_morning_briefing()
    assert heard == [notifier.sent[0].text] and notifier.audio == [(b"mp3", "Morning briefing")]


async def test_voice_off_or_failing_still_sends_text(sessionmaker):
    for synth in (None, boom):
        notifier = FakeNotifier()
        await BriefingActivities(
            sessionmaker, notifier, "Asia/Kolkata", synthesize=synth
        ).send_morning_briefing()
        assert len(notifier.sent) == 1 and notifier.audio == []


def test_synthesize_speech(monkeypatch):
    mock_client = MagicMock()
    mock_client.text_to_speech.convert.return_value = [b"chunk1", b"chunk2"]
    monkeypatch.setattr("app.briefing.voice.ElevenLabs", lambda api_key: mock_client)

    result = synthesize_speech("Good morning!", api_key="secret", voice_id="voice123")
    assert result == b"chunk1chunk2"
    mock_client.text_to_speech.convert.assert_called_once_with(
        voice_id="voice123",
        text="Good morning!",
    )
