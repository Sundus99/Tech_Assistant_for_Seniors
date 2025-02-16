#import openai
from openai import OpenAI
import os
from dotenv import load_dotenv
import SpeechRecognition as sr
import markdown
from bs4 import BeautifulSoup

def speech_to_text():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("Listening")
        recognizer.adjust_for_ambient_noise(source)
        audio = recognizer.listen(source)
    try:
        user_request = recognizer.recognize_google(audio)
        print(f"User: {user_request}")
        return user_request
    except sr.RequestError:
        print("API unavailable")
        return None
    except sr.UnknownValueError:
        print("Sorry I couldn't understand")
        return None
    
def generate_response(user_request):
    load_dotenv
    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),  # This is the default and can be omitted
    )
#gpt-3.5-turbo
    response = client.chat.completions.create(
        model = "gpt-4o-mini",
        store= True,
        messages = [{"role":"user", "content":user_request}]
    )

    # Beautifying the response
    html_content = markdown.markdown(response.choices[0].message.content)
    soup = BeautifulSoup(html_content, "html.parser")
    reply = soup.get_text()
    print(f"AI: {reply}")
    return reply

def main():
    while True:
        user_input = input("please type in a message: ") #speech_to_text()
        if user_input:
            response = generate_response(user_input)
            print(f"AI: {response}")

if __name__ == "__main__":
    main()
    
