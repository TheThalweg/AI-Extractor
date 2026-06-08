import os
import json
from flask import Flask, jsonify, render_template, send_from_directory, abort

app = Flask(__name__, template_folder='templates', static_folder='static')

# --- Configuration ---
# Adjust these paths based on your project structure.
# These paths assume the 'dashboard' directory is inside 'AI-Extractor'.
CLASSIFIED_JSON_PATH = os.path.join(app.root_path, '..', 'classified_emails.json')
NEWS_JSON_PATH = os.path.join(app.root_path, 'news.json')
DATA_DIR = os.path.join(app.root_path, '..', 'Data', 'Data')

# --- Routes ---

@app.route('/')
def index():
    """Serves the main dashboard page."""
    return render_template('index.html')

@app.route('/api/emails')
def get_emails():
    """Serves the main classified emails JSON data."""
    if not os.path.exists(CLASSIFIED_JSON_PATH):
        return jsonify({"error": "classified_emails.json not found"}), 404
    with open(CLASSIFIED_JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return jsonify(data)

@app.route('/api/news')
def get_news():
    """Serves the fetched news headlines."""
    if not os.path.exists(NEWS_JSON_PATH):
        return jsonify({"error": "news.json not found"}), 404
    with open(NEWS_JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return jsonify(data)

@app.route('/api/email/<path:source_folder>')
def get_email_html(source_folder):
    """Serves the HTML content for a specific email."""
    html_path = os.path.join(DATA_DIR, source_folder, 'emailbody.html')
    if not os.path.exists(html_path):
        abort(404, description="Email HTML file not found.")
    return send_from_directory(os.path.dirname(html_path), 'emailbody.html')

@app.route('/api/pdf/<path:source_folder>/<path:pdf_name>')
def get_pdf(source_folder, pdf_name):
    """Serves a PDF attachment."""
    pdf_dir = os.path.join(DATA_DIR, source_folder)
    if not os.path.exists(os.path.join(pdf_dir, pdf_name)):
        abort(404, description="PDF file not found.")
    return send_from_directory(pdf_dir, pdf_name)

if __name__ == '__main__':
    app.run(debug=True, port=5001)