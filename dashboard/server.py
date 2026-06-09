import os
import json
from flask import Flask, jsonify, render_template, send_from_directory, abort, Response

app = Flask(__name__, template_folder='templates', static_folder='static')

app.config['JSON_AS_ASCII'] = False

CLASSIFIED_JSON_PATH = os.path.join(app.root_path, '..', 'classified_emails.json')
NEWS_JSON_PATH = os.path.join(app.root_path, 'news.json')
TAXONOMY_JSON_PATH = os.path.join(app.root_path, '..', 'taxonomy.json')
DATA_DIR = os.path.join(app.root_path, '..', 'Data', 'Data')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/emails')
def get_emails():
    if not os.path.exists(CLASSIFIED_JSON_PATH):
        return jsonify({"error": "classified_emails.json not found"}), 404
    with open(CLASSIFIED_JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return jsonify(data)

@app.route('/api/news')
def get_news():
    if not os.path.exists(NEWS_JSON_PATH):
        return jsonify({"error": "news.json not found"}), 404
    with open(NEWS_JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return jsonify(data)

@app.route('/api/taxonomy')
def get_taxonomy():
    if not os.path.exists(TAXONOMY_JSON_PATH):
        return jsonify({"error": "taxonomy.json not found"}), 404
    with open(TAXONOMY_JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return jsonify(data.get("asset_taxonomy", {}))

# For specific emails
@app.route('/api/email/<path:source_folder>')
def get_email_html(source_folder):
    html_path = os.path.join(DATA_DIR, source_folder, 'emailbody.html')
    if not os.path.exists(html_path):
        abort(404, description="Email HTML file not found.")

    # Multiple encodings in case one of them doesn't work
    # Tries common encodings: UTF-8 with BOM, standard UTF-8, then Windows-1252 
    for enc in ['utf-8-sig', 'utf-8', 'cp1252', 'latin-1']:
        try:
            with open(html_path, "r", encoding=enc) as f:
                content = f.read()
            break
        except UnicodeDecodeError:
            continue

    return Response(content, mimetype='text/html', content_type='text/html; charset=utf-8')

@app.route('/api/pdf/<path:source_folder>/<path:pdf_name>')
def get_pdf(source_folder, pdf_name):
    pdf_dir = os.path.join(DATA_DIR, source_folder)
    if not os.path.exists(os.path.join(pdf_dir, pdf_name)):
        abort(404, description="PDF file not found.")
    return send_from_directory(pdf_dir, pdf_name)

if __name__ == '__main__':
    app.run(debug=True, port=5001)