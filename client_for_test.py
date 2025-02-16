import requests
import streamlit as st

# JavaScript function to open a new tab
def open_url_in_new_tab(url):
    js = f"""<script>window.open("{url}","_blank");</script>"""
    st.components.v1.html(js, height=0)

# Streamlit UI
st.title("Tech Assistant for Seniors")

# User input box
user_input = st.text_input("Ask me anything:")

if st.button("Send"):
    if user_input:
        # Use Heroku backend URL
        backend_url = "https://tech-assistant-for-seniors-eb4876783faf.herokuapp.com/chat"
        response = requests.post(backend_url, json={"user_input": user_input})

        if response.status_code == 200:
            result = response.json()
            print(result)
            ai_reply = result["AI"]
            response_type = result["type"]

            # Display AI response
            st.write(f"**AI:** {str(ai_reply)}")

            # If backend instructs to open a webpage, open a new tab
            if response_type == "open web page" and "url" in result:
                url = result["url"]
                open_url_in_new_tab(url)  # Open in new tab

        else:
            st.write("Error: Could not reach the backend.")
