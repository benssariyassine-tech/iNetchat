import os
from flask import Flask, jsonify, render_template, send_from_directory, request
from flask_cors import CORS
from supabase import create_client, Client

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

# ====== Supabase Connection ======
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase = None
    print("⚠️ Supabase credentials not configured!")


# ====== Routes ======

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ok",
        "app": "iNetchat",
        "supabase": "connected" if supabase else "not configured"
    })


@app.route('/api/db-test', methods=['GET'])
def db_test():
    if not supabase:
        return jsonify({"status": "error", "message": "Supabase not configured"}), 500
    try:
        response = supabase.table('profiles').select('*').limit(1).execute()
        return jsonify({
            "status": "success",
            "message": "Database connected successfully!",
            "data": response.data
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
