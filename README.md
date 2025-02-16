# Tech_Assistant_for_Seniors
The project aims to assist seniors to be independent when navigating technology. 
## Features
- voice command
- Gen AI assisstant
- mouse actions
- chrome extension
## How to Work with it
Create a separate environment for it first, using the command `python -m venv ellehack25`, you can change the name of the venv to anything you want
- you may get an error, to resolve that run the following command and rerun the above command
- `Set-ExecutionPolicy Unrestricted -Scope Process`
- After rerunning the venv creation command run this command to activate the virtual env `ellehacks25\Scripts\activate`

Use the command `pip install -r requirements.txt` to install all dependencies in this virtual environment
## Backend is Deployed here, use the `/chat` endpoint for POST:
https://tech-assistant-for-seniors-eb4876783faf.herokuapp.com/
## Tools & References Used:
- VS Code
- Github Copilot for VS Code debugging & gpt-o1 model
- Speech Recognition API Reference & Boilerplate
- Chrome Extension Docs
- ChatGPT API
