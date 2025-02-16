#import openai
from openai import OpenAI
import webbrowser

import os
from dotenv import load_dotenv

# Markdown is used to convert the response to HTML
import markdown
from bs4 import BeautifulSoup
# FastAPI is used to create the API
from fastapi import FastAPI, Request
# Pydantic is used for data validation
from pydantic import BaseModel 

# Uvicorn is used to run the server
import uvicorn

# Load environment variables 
load_dotenv()
server = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),  # This is the default and can be omitted
)
app = FastAPI()

# Validates the user input
class UserRequest(BaseModel):
    user_input: str
    
def generate_response(user_request: str) -> str:
    l_u_r = user_request.lower()
    if ("open" in l_u_r or "launch" in l_u_r) and ("how" not in l_u_r):
        if "youtube" in l_u_r: 
            webbrowser.open(url="https://www.youtube.com/")  # Open Youtube
            return "Opening Youtube, now in search bar, type what you want to watch. \nFor example, type 'funny cat videos' and press Enter key on your keyboard."
        elif "gmail" in l_u_r:
            webbrowser.open(url="https://www.gmail.com/")
            return "Opening Gmail"
        elif "google" in l_u_r:
            webbrowser.open(url="https://www.google.ca/")
            return "Opening Google"
        elif "facebook" in l_u_r:    
            webbrowser.open(url="https://www.facebook.com/")
            return "Opening Facebook"
        elif "hotmail" in l_u_r:
            webbrowser.open(url="https://www.hotmail.com/")
            return "Opening Hotmail"
        elif "yahoo" in l_u_r:  
            webbrowser.open(url="https://www.yahoo.com/")
            return "Opening Yahoo"
        elif "bing" in l_u_r:
            webbrowser.open(url="https://www.bing.com/")
            return "Opening Bing"
        elif "duckduckgo" in l_u_r or "duck duck go" in l_u_r or "duck duckgo" in l_u_r:
            webbrowser.open(url="https://www.duckduckgo.com/")
            return "Opening DuckDuckGo"
        elif "amazon" in l_u_r:   
            webbrowser.open(url="https://www.amazon.ca/")
            return "Opening Amazon"
        elif "ebay" in l_u_r:       
            webbrowser.open(url="https://www.ebay.ca/")
            return "Opening Ebay"
        elif "wikipedia" in l_u_r:  
            webbrowser.open(url="https://www.wikipedia.org/")
            return "Opening Wikipedia"
    
        
    #gpt-3.5-turbo
    response = server.chat.completions.create(
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

@app.post("/chat")  # POST request to /chat
async def chat_endpoint(user_request: UserRequest):
    reply = generate_response(user_request.user_input)  
    return {"AI": reply}


    
