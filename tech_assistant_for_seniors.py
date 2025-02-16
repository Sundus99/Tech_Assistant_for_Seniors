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
from fastapi.middleware.cors import CORSMiddleware
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
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_methods=["*"], 
    allow_headers=["*"]
)

# Validates the user input
class UserRequest(BaseModel):
    user_input: str
    
def generate_response(user_request: str) -> str:
    l_u_r = user_request.lower()
    if ("open" in l_u_r or "launch" in l_u_r or "go to" in l_u_r) and ("how" not in l_u_r):
        if "youtube" in l_u_r: 
            return {"AI": "Opening Youtube, now in search bar, type what you want to watch. \nFor example, type 'funny cat videos' and press Enter key on your keyboard.",
                    "type": "open web page",
                    "url": "https://www.youtube.com/"}
        elif "gmail" in l_u_r:
            return {"AI": "Opening Gmail",
                    "type": "open web page",
                    "url": "https://www.gmail.com/"}
        elif "google" in l_u_r:
            return {"AI": "Opening Google",
                    "type": "open web page",
                    "url": "https://www.google.ca/"}
        elif "facebook" in l_u_r:    
            return {"AI": "Opening Facebook",
                    "type": "open web page",
                    "url": "https://www.facebook.com/"}
        elif "hotmail" in l_u_r:
            return {"AI": "Opening Hotmail",
                    "type": "open web page",
                    "url": "https://www.hotmail.com/"}
        elif "yahoo" in l_u_r:  
            return {"AI": "Opening Yahoo",
                    "type": "open web page",
                    "url": "https://www.yahoo.com/"}
        elif "bing" in l_u_r:
            return {"AI": "Opening Bing",
                    "type": "open web page",
                    "url": "https://www.bing.com/"}
        elif "duckduckgo" in l_u_r or "duck duck go" in l_u_r or "duck duckgo" in l_u_r:
            return {"AI": "Opening DuckDuckGo",
                    "type": "open web page",
                    "url": "https://www.duckduckgo.com/"}
        elif "amazon" in l_u_r:   
            return {"AI": "Opening Amazon",
                    "type": "open web page",
                    "url": "https://www.amazon.ca/"}
        elif "ebay" in l_u_r:       
            return {"AI": "Opening Ebay",
                    "type": "open web page",
                    "url": "https://www.ebay.ca/"}
        elif "wikipedia" in l_u_r:  
            return {"AI": "Opening Wikipedia",
                    "type": "open web page",
                    "url": "https://www.wikipedia.org/"}
    
        
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
    return {"AI": reply,
            "type": "chat"}

@app.post("/chat")  # POST request to /chat
async def chat_endpoint(user_request: UserRequest):
    reply = generate_response(user_request.user_input)  
    return reply


    
