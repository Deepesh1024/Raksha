import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def audio2vec(filename):
    if not os.path.exists(filename):
        print(f"Audio file not found: {filename}")
        return ""

    try:
        with open(filename, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(os.path.basename(filename), file.read()),
                model="whisper-large-v3-turbo",
                temperature=0,
                response_format="verbose_json",
            )
            text = transcription.text.strip()
            print(f"Transcription: {text}")
            return text
    except Exception as e:
        print(f"Transcription failed: {str(e)}")
        return ""