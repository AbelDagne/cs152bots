import base64
import requests


# Function to encode the image
def encode_image(image_url):
    response = requests.get(image_url)
    image_content = response.content
    return base64.b64encode(image_content).decode('utf-8')

def flag_image(image_url):
    base64_image = encode_image(image_url)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    payload = {
        "model": "gpt-4o",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "You are a content moderator. Flag images for potentially containing political misinformation or other reasons. "
                            "Respond with 'YES, reason: ...' if it should be flagged, or 'NO, reason: ...' if it is safe. "
                            "Additionally, provide detailed information in the following format. Choose one option for each item: \n"
                            "1. Abuse type (1 for Misleading or False Information), (2 for Inappropriate Adult Content), (3 for Illegal Products or Services), (4 for Offensive Content), (5 for Other)\n"
                            "2. Specific issue (if Abuse type is 1: (1 for Deepfakes and deceptive AI-generated content, 2 for Deceptive offers, 3 for Impersonation, 4 for Manipulated Media, 5 for Political Disinformation)), (if Abuse type is 2: (1 for Nudity and sexual content, 2 for Adult products and/or services, 3 for Sensitive content)), (if Abuse type is 3: (1 for Banned substances/drugs, 2 for Unauthorized medical products, 3 for Weapons or explosives, 4 for Illegal activities/services)), (if Abuse type is 4: (1 for Profanity, 2 for Hate speech, 3 for Violent imagery, 4 for Technical issues)), (if Abuse type is 5: (1 for Privacy issues, 2 for Feedback on ad preferences, 3 for Other concerns))\n"
                            "3. Source (a brief explanation or 'none' if not applicable)"
                        )
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 300
    }

    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    result = response.json()
    if 'choices' not in result:
        print("API response:", result)
        raise ValueError("Unexpected API response structure")
    return result