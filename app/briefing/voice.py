from elevenlabs.client import ElevenLabs


def synthesize_speech(text: str, *, api_key: str, voice_id: str) -> bytes:
    client = ElevenLabs(api_key=api_key)
    audio_stream = client.text_to_speech.convert(
        voice_id=voice_id,
        text=text,
    )
    return b"".join(audio_stream)
