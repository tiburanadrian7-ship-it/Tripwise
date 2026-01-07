import os
from flask import Flask, request, jsonify, render_template
from google import genai

os.environ["GOOGLE_API_KEY"] = "AIzaSyD1Qwsiw_PHOyngYlVw_HICNxznDpUUweY"

client = genai.Client()

BOT_NAME = "WiseBot"

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "../templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "../static")
)

@app.route("/")
def index():
    return render_template("gemini_chat.html", bot_name=BOT_NAME)
    

@app.route("/ask", methods=["POST"])
def ask():
    data = request.json
    user_message = data.get("message", "")

    if not user_message.strip():
        return jsonify({"response": "⚠️ Please type a message."})

    prompt = f"You are a helpful assistant named {BOT_NAME}. Answer the following user message accordingly:\n\nUser: {user_message}\n{BOT_NAME}:"

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        return jsonify({"response": response.text})
    except Exception as e:
        return jsonify({"response": f"⚠️ Error: {str(e)}"})

if __name__ == "__main__":
    app.run(debug=True)