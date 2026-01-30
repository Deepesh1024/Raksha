import os
import base64
from pathlib import Path
from groq import Groq
from dotenv import load_dotenv
import time
from typing import Optional

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Save TTS directly into uploads/ so Flask can serve via /uploads/<filename>
OUTPUT_DIR = Path("uploads")
OUTPUT_DIR.mkdir(exist_ok=True)


def encode_image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def get_image_mime_type(image_path: str) -> str:
    ext = Path(image_path).suffix.lower()
    mime_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp'
    }
    return mime_types.get(ext, 'image/jpeg')


def analyze_emergency_situation(
    image_path: str,
    transcription: Optional[str] = None,
    additional_context: Optional[str] = None
) -> str:
    base64_image = encode_image_to_base64(image_path)
    mime_type = get_image_mime_type(image_path)
    image_data_url = f"data:{mime_type};base64,{base64_image}"

    prompt_parts = [
        "You are an emergency response assistant. Analyze this situation and generate a short, clear emergency call speech (2-3 sentences max)."
    ]

    if transcription:
        prompt_parts.append(f"\n\nAudio transcription: {transcription}")

    if additional_context:
        prompt_parts.append(f"\n\nAdditional context: {additional_context}")

    prompt_parts.append("\n\nGenerate ONLY the emergency call speech text, nothing else. Be concise, urgent, and factual.")
    prompt_text = "".join(prompt_parts)

    content = [
        {"type": "text", "text": prompt_text},
        {"type": "image_url", "image_url": {"url": image_data_url}}
    ]

    try:
        completion = client.chat.completions.create(
            model="meta-llama/llama-4-maverick-17b-128e-instruct",
            messages=[{"role": "user", "content": content}],
            temperature=0.7,
            max_completion_tokens=150,
            top_p=1,
            stream=True,
            stop=None
        )

        emergency_speech = ""
        for chunk in completion:
            if chunk.choices[0].delta.content:
                emergency_speech += chunk.choices[0].delta.content

        return emergency_speech.strip()

    except Exception as e:
        print(f"Emergency analysis failed: {str(e)}")
        raise


def text_to_emergency_audio(text: str, voice: str = "austin") -> Path:
    if not text.strip():
        raise ValueError("Cannot generate audio from empty text")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    speech_file = OUTPUT_DIR / f"alert_{timestamp}.wav"

    try:
        response = client.audio.speech.create(
            model="canopylabs/orpheus-v1-english",
            voice=voice,
            response_format="wav",
            input=text.strip(),
        )

        response.write_to_file(str(speech_file))

        if not speech_file.is_file():
            raise RuntimeError("TTS file was not created")

        print(f"✓ Emergency audio generated: {speech_file}")
        return speech_file

    except Exception as e:
        print(f"TTS failed: {str(e)}")
        raise


def process_emergency_call(
    image_path: str,
    transcription: Optional[str] = None,
    additional_context: Optional[str] = None,
    voice: str = "austin",
    save_text: bool = True
) -> tuple[str, Path]:
    print(f"📸 Analyzing emergency situation from: {image_path}")

    emergency_text = analyze_emergency_situation(
        image_path=image_path,
        transcription=transcription,
        additional_context=additional_context
    )

    print(f"📝 Generated emergency speech:\n{emergency_text}\n")

    audio_path = text_to_emergency_audio(emergency_text, voice=voice)

    if save_text:
        text_file = audio_path.with_suffix('.txt')
        text_file.write_text(emergency_text, encoding='utf-8')
        print(f"💾 Text saved: {text_file}")

    return emergency_text, audio_path