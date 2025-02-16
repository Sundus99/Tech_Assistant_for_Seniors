#import openai
from openai import OpenAI

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


    
