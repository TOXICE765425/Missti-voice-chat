import requests
from .config import API_URL, API_MODEL

def ask_ai(prompt: str) -> str:
    try:
        response = requests.get(
            API_URL,
            params={"prompt": prompt, "model": API_MODEL},
            timeout=40,
        )
        response.raise_for_status()
        data = response.json()
        answer = data.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            return "Sorry, mujhe abhi jawab nahi mila."
        return answer.strip()
    except requests.RequestException as exc:
        print(f"AI API request failed: {exc}")
        return "Sorry, abhi AI service available nahi hai."
    except (ValueError, TypeError) as exc:
        print(f"AI API returned invalid data: {exc}")
        return "AI service se valid response nahi mila."
