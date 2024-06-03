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
                        "text": "You are a content moderator and you flag images for potentially containing political misinformation. If you think the image should be flagged for human review, respond with: 'YES, reason:' and the reason. If the image is safe and likely factual respond with: 'NO, reason:' and the reason."
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