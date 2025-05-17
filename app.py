from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_session import Session
import os
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

DATABASE = 'lifeline.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT UNIQUE,
            password TEXT,
            emergency_contact TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hospitals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hospital_name TEXT UNIQUE,
            user_id TEXT,
            password TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            hospital_name TEXT,
            report_name TEXT,
            report_type TEXT,
            result TEXT,
            description TEXT,
            remark TEXT,
            critical TEXT,
            date TEXT
        )
    ''')

    # Remove default user creation to let user create new users manually
    cursor.execute('SELECT COUNT(*) FROM hospitals')
    hospital_count = cursor.fetchone()[0]
    if hospital_count == 0:
        cursor.execute('INSERT INTO hospitals (hospital_name, user_id, password) VALUES (?, ?, ?)', ('City Hospital', 'hospital1', 'password1'))

    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/user', methods=['GET', 'POST'])
def user_page():
    if request.method == 'POST':
        try:
            data = request.get_json()
            if data:
                user_id = data.get('user_id')
                password = data.get('password')
            else:
                user_id = request.form.get('user_id')
                password = request.form.get('password')

            if not user_id or not password:
                return jsonify({'status': 'error', 'message': 'User ID and password are required'}), 400

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            user = cursor.fetchone()

            if user:
                if not check_password_hash(user['password'], password):
                    conn.close()
                    return jsonify({'status': 'error', 'message': 'Invalid password'}), 401
            else:
                conn.close()
                return jsonify({'status': 'error', 'message': 'User not found'}), 404

            conn.close()

            session['user_id'] = user_id
            return jsonify({'status': 'success'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': f'An error occurred: {str(e)}'}), 500
    return render_template('user.html')

@app.route('/user/create', methods=['POST'])
def user_create():
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        password = data.get('password')

        if not user_id or not password:
            return jsonify({'status': 'error', 'message': 'User ID and password required'}), 400

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        existing_user = cursor.fetchone()
        if existing_user:
            conn.close()
            return jsonify({'status': 'error', 'message': 'User ID already exists'}), 409

        hashed_password = generate_password_hash(password)
        cursor.execute('INSERT INTO users (user_id, password) VALUES (?, ?)', (user_id, hashed_password))
        conn.commit()
        conn.close()

        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'An error occurred: {str(e)}'}), 500

from flask import g

latest_sos_message = None
latest_sos_reports = []

@app.route('/user/sos', methods=['POST'])
def user_sos():
    global latest_sos_message, latest_sos_reports
    data = request.get_json()
    user_id = data.get('user_id', 'Unknown User')
    message = data.get('message', 'There is an emergency.')
    emergency_contact = data.get('emergency_contact', 'No contact provided')
    location = data.get('location', None)
    address = data.get('address', None)

    # Fetch user reports from database
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM reports WHERE user_id = ?', (user_id,))
    reports = cursor.fetchall()
    conn.close()

    # Convert reports to list of dicts
    latest_sos_reports = []
    for row in reports:
        latest_sos_reports.append({
            'id': row['id'],
            'user_id': row['user_id'],
            'hospital_name': row['hospital_name'],
            'report_name': row['report_name'],
            'report_type': row['report_type'],
            'result': row['result'],
            'description': row['description'],
            'remark': row['remark'],
            'critical': row['critical'],
            'date': row['date'],
        })

    # Store latest SOS message
    latest_sos_message = {
        'user_id': user_id,
        'message': message,
        'location': location,
        'address': address,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

    # Override hospital info to JLU College for SOS
    hospital_name = "JLU College"
    hospital_location = {"lat": 23.2590, "lng": 77.4120}  # Approximate JLU College coords

    print(f"SOS from user {user_id}: {message}")
    print(f"Location: {location}, Address: {address}")
    print(f"Notify emergency contact: {emergency_contact}")
    print(f"SOS sent to hospital: {hospital_name}")
    print(f"Reports sent: {len(latest_sos_reports)}")

    return jsonify({
        'status': 'SOS signal received',
        'hospital_name': hospital_name,
        'hospital_location': hospital_location
    })

@app.route('/api/hospital/sos')
def api_hospital_sos():
    global latest_sos_message, latest_sos_reports
    if latest_sos_message:
        return jsonify({'status': 'new', 'sos': latest_sos_message, 'reports': latest_sos_reports})
    else:
        return jsonify({'status': 'none'})

@app.route('/user/dashboard')
def user_dashboard():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('user_page'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT emergency_contact FROM users WHERE user_id = ?', (user_id,))
    contact = cursor.fetchone()
    conn.close()

    return render_template('user_dashboard.html', emergency_contact=contact)

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return '', 204

@app.route('/user/emergency_contact', methods=['POST'])
def user_emergency_contact():
    data = request.get_json()
    name = data.get('name')
    number = data.get('number')
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'status': 'error', 'message': 'User not logged in'}), 401

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET emergency_contact = ? WHERE user_id = ?', (f"{name} - {number}", user_id))
    conn.commit()
    conn.close()

    return jsonify({'status': 'success'})

@app.route('/user/emergency_contact', methods=['GET'])
def get_user_emergency_contact():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'status': 'error', 'message': 'User not logged in'}), 401

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT emergency_contact FROM users WHERE user_id = ?', (user_id,))
    contact = cursor.fetchone()
    conn.close()

    if contact and contact['emergency_contact']:
        return jsonify({'status': 'success', 'emergency_contact': contact['emergency_contact']})
    else:
        return jsonify({'status': 'success', 'emergency_contact': None})

@app.route('/user/address', methods=['POST'])
def user_address():
    data = request.get_json()
    address = data.get('address')
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'status': 'error', 'message': 'User not logged in'}), 401

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET emergency_contact = ? WHERE user_id = ?', (address, user_id))
    conn.commit()
    conn.close()

    return jsonify({'status': 'success'})

@app.route('/user/report')
def user_report():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('user_page'))

    return render_template('user_report.html')

@app.route('/api/user/reports')
def api_user_reports():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify([])

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM reports WHERE user_id = ?', (user_id,))
    rows = cursor.fetchall()
    conn.close()

    reports = []
    for row in rows:
        reports.append({
            'id': row['id'],
            'user_id': row['user_id'],
            'hospital_name': row['hospital_name'],
            'report_name': row['report_name'],
            'report_type': row['report_type'],
            'result': row['result'],
            'description': row['description'],
            'remark': row['remark'],
            'critical': row['critical'],
            'date': row['date'],
        })

    return jsonify(reports)

import openai

openai.api_key = os.getenv("OPENAI_API_KEY")

@app.route('/user/chatbot')
def user_chatbot():
    return render_template('user_chatbot.html')

@app.route('/api/hospital/reports', methods=['POST'])
def api_hospital_reports():
    data = request.get_json()
    required_fields = ['user_id', 'hospital_name', 'report_name', 'report_type', 'result', 'description', 'remark', 'critical', 'date']
    if not all(field in data for field in required_fields):
        return jsonify({'status': 'error', 'message': 'Missing fields'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO reports (user_id, hospital_name, report_name, report_type, result, description, remark, critical, date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data['user_id'],
        data['hospital_name'],
        data['report_name'],
        data['report_type'],
        data['result'],
        data['description'],
        data['remark'],
        data['critical'],
        data['date']
    ))
    conn.commit()
    conn.close()

    return jsonify({'status': 'success'})

import openai

openai.api_key = "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"

@app.route('/api/chatbot', methods=['POST'])
def api_chatbot():
    data = request.get_json()
    message = data.get('message', '').lower()
    if not message:
        return jsonify({'response': "Please provide a message."})

    # Extended rule-based chatbot responses for medical conditions
    responses = {
        "i am having trouble breathing": "Breathing difficulty can be serious. Are you also experiencing chest pain or high fever?\nIf yes, I advise you to call emergency services or go to the nearest hospital immediately.\nUntil help arrives, sit upright and try to stay calm. Avoid lying down.",
        "i have chest pain and dizziness": "This could be a sign of a heart attack. Call emergency services now.\nChew an aspirin (unless allergic), lie down in a comfortable position, and stay calm.\nI'm notifying the nearest hospital. Please keep your emergency contact nearby.",
        "my face is drooping and i can't speak properly": "You may be experiencing a stroke. Time is critical.\nCall emergency services immediately.\nNote the time symptoms began and keep yourself safe until help arrives.",
        "i feel shaky, sweaty, and dizzy": "These are signs of low blood sugar. Please drink juice or eat a sugary snack immediately.\nIf symptoms persist or worsen, seek medical attention.\nDo you have insulin or diabetes medication with you?",
        "i have a high fever with chills and body pain": "This could be a sign of viral infection or something more serious like dengue or malaria.\nDrink plenty of fluids and rest. Avoid self-medication without proper diagnosis.\nIf the fever persists for more than 2 days or is above 102°F, consult a doctor.",
        "i have a sore throat and runny nose": "It looks like you have symptoms of a common cold or flu.\nStay hydrated, get rest, and use warm salt water gargles for your throat.\nIf symptoms worsen after 3 days or you get a high fever, consult a doctor.",
        "i feel anxious and can't sleep": "I'm here for you. Anxiety and insomnia are common and treatable.\nTry deep breathing exercises or guided meditation.\nIf this happens frequently, talking to a mental health professional can help a lot.\nWould you like a calming playlist or breathing guide?",
        "i'm having pain while urinating": "You may have a urinary tract infection (UTI).\nDrink lots of water and avoid caffeinated or acidic drinks.\nIf you also have fever or back pain, it’s best to visit a doctor soon.",
        "someone just fell and is bleeding": "Apply pressure to the wound with a clean cloth to stop bleeding.\nCall emergency services immediately.\nIf they’re unconscious or not breathing, perform CPR if trained.\nI'm notifying the nearest hospital with your location.",
        "i have chronic kidney disease. what diet should i follow?": "For CKD, limit sodium, potassium, and phosphorus intake. Stay hydrated and avoid high-protein foods unless prescribed.\nPlease consult your nephrologist for a personalized diet.\nWould you like a sample renal-friendly meal plan?",
        "i'm having severe chest pain and it's spreading to my left arm": "This could be a heart attack. Call emergency services immediately and try to stay calm. Do not exert yourself.",
        "my father is unconscious and his face is drooping on one side": "Possible stroke. Call emergency services immediately. Note the time symptoms started and keep the person on their side with head elevated.",
        "my sister just had a seizure and she's shaking uncontrollably": "Ensure she's in a safe place, turn her to her side, and don’t put anything in her mouth. Call emergency services immediately.",
        "i'm feeling shortness of breath with sharp chest pain": "This might be a heart attack or pulmonary embolism. Call emergency services right away. Sit upright and stay calm.",
        "he suddenly fainted and is not waking up": "Check for breathing and pulse. If absent, begin CPR and call emergency services immediately.",
        "i accidentally spilled hot water on my leg and it’s blistering": "Run cool water on the burn for 15 minutes, don’t burst the blisters, cover with a sterile gauze and seek medical attention.",
        "i think i broke my arm, it's swollen and very painful": "Immobilize the arm, avoid moving it, apply ice wrapped in cloth, and visit the emergency room.",
        "i got a deep cut while chopping vegetables, it's bleeding a lot": "Apply direct pressure with a clean cloth. Elevate the wound. If bleeding doesn't stop in 10 mins, go to ER.",
        "my friend is having difficulty breathing and her lips are swelling": "Possible allergic reaction. Use an epinephrine auto-injector if available. Call emergency services immediately.",
        "my brother is having an asthma attack and his inhaler isn’t helping": "Sit him upright, keep him calm, and call emergency services. Avoid cold air and allergens.",
        "i have a fever and body ache since last night": "Drink plenty of fluids, rest, and take paracetamol. If fever persists beyond 3 days, see a doctor.",
        "my ankle is swollen after i twisted it": "Apply ice, elevate the leg, and wrap it with a bandage. Avoid walking too much and monitor for severe swelling.",
        "i've been feeling nauseous and throwing up since morning": "Stay hydrated with oral rehydration solution. Avoid solid food temporarily. If vomiting persists, consult a doctor.",
        "my throat is sore and it hurts to swallow": "Gargle with warm salt water, drink warm fluids, and rest your voice. If symptoms worsen, consult a doctor.",
        "i have a mild headache since waking up": "Rest in a quiet dark room and stay hydrated. You can take a mild painkiller like paracetamol if needed.",
        "my grandma is gasping for breath and can't speak": "Call emergency help. Loosen clothing, sit her upright, and reassure her until help arrives.",
        "i have a small burn on my finger from touching a hot pan": "Cool the area under running water for 10 minutes. Apply aloe vera or a burn ointment and cover with a clean bandage.",
        "i twisted my wrist while lifting a box": "Rest it, apply ice, and wrap with a bandage. Avoid lifting anything heavy for a day or two.",
        "i'm bleeding from a nose injury": "Pinch your nose and lean forward. If bleeding doesn’t stop in 10–15 minutes, seek medical help.",
        "i feel dizzy and have blurred vision after skipping meals": "Eat something with sugar immediately. Rest and hydrate. If symptoms persist, consult a doctor.",
        "high blood pressure": "Possible complications include heart disease, stroke, kidney damage, vision loss, and aneurysms.",
        "diabetes": "Possible complications include heart disease, nerve damage, kidney damage, eye problems, and foot problems.",
        "chronic kidney disease": "Possible complications include high blood pressure, anemia, bone disease, heart disease, and end-stage renal disease.",
        "asthma": "Possible symptoms include frequent coughing, shortness of breath, wheezing, hospitalization, and lung infections.",
        "arthritis": "Possible symptoms include joint pain, swelling, reduced mobility, deformities, and chronic pain.",
        "depression": "Possible symptoms include persistent sadness, fatigue, sleep disturbances, appetite changes, and suicidal thoughts.",
        "anxiety": "Possible symptoms include panic attacks, restlessness, difficulty concentrating, insomnia, and physical symptoms.",
        "obesity": "Possible complications include heart disease, diabetes, joint problems, sleep apnea, and certain cancers.",
        "coronary artery disease": "Possible symptoms include chest pain, heart attack, heart failure, irregular heartbeat, and death.",
        "stroke": "Possible symptoms include paralysis, speech difficulties, cognitive impairment, emotional problems, and death.",
        "i am suffering from fever, and i want to know the possible health outcomes.": "Possible health outcomes include: fatigue, chills, sweating, muscle aches, dehydration.",
        "i am suffering from cold, and i want to know the possible health outcomes.": "Possible health outcomes include: sneezing, runny nose, sore throat, coughing, fatigue.",
        "i am suffering from flu, and i want to know the possible health outcomes.": "Possible health outcomes include: high fever, body aches, chills, cough, headache.",
        "i am suffering from headache, and i want to know the possible health outcomes.": "Possible health outcomes include: sensitivity to light, nausea, difficulty concentrating, irritability, fatigue.",
        "i am suffering from stomach ache, and i want to know the possible health outcomes.": "Possible health outcomes include: nausea, vomiting, diarrhea, bloating, cramping.",
        "i am suffering from diarrhea, and i want to know the possible health outcomes.": "Possible health outcomes include: dehydration, abdominal pain, fatigue, nausea, weight loss.",
        "i am suffering from constipation, and i want to know the possible health outcomes.": "Possible health outcomes include: abdominal discomfort, bloating, straining during bowel movements, hemorrhoids, irritability.",
        "i am suffering from sore throat, and i want to know the possible health outcomes.": "Possible health outcomes include: pain while swallowing, swollen glands, hoarseness, fever, cough.",
        "i am suffering from cough, and i want to know the possible health outcomes.": "Possible health outcomes include: throat irritation, chest pain, fatigue, sleep disruption, shortness of breath.",
        "i am suffering from vomiting, and i want to know the possible health outcomes.": "Possible health outcomes include: dehydration, weakness, dizziness, electrolyte imbalance, abdominal pain."
    }

    # Check for exact key match first
    if message in responses:
        return jsonify({'response': responses[message]})

    # Check for partial key match
    for key in responses:
        if key in message:
            return jsonify({'response': responses[key]})

    return jsonify({'response': "Sorry, I couldn't process your request."})

@app.route('/hospital', methods=['GET', 'POST'])
def hospital_login():
    if request.method == 'POST':
        hospital_name = request.form.get('hospital_name')

        # Set default hospital name if empty
        if not hospital_name:
            hospital_name = "JK Hospital Bhopal"

        # For simplicity, no user_id or password required
        session['hospital_name'] = hospital_name
        return redirect(url_for('hospital_dashboard'))
    return render_template('hospital_login.html')

@app.route('/hospital/dashboard', methods=['GET', 'POST'])
def hospital_dashboard():
    hospital_name = session.get('hospital_name', 'JK Hospital Bhopal')
    hospital_descriptions = {
        "JK Hospital Bhopal": "JK Hospital Bhopal is dedicated to providing exceptional healthcare services with a focus on patient-centered care, advanced medical technology, and compassionate staff. Our hospital specializes in emergency response, critical care, and comprehensive medical treatments to ensure the well-being of our community.",
        "Apollo Sage Hospital": "Apollo Sage Hospital offers world-class medical care with state-of-the-art facilities and a team of experienced healthcare professionals committed to patient well-being.",
        "Bansal Hospital": "Bansal Hospital is known for its comprehensive healthcare services, advanced diagnostics, and compassionate patient care.",
        "Galaxy Hospital": "Galaxy Hospital provides specialized medical treatments with a focus on innovation and patient comfort.",
        "Siddhanta Hospital": "Siddhanta Hospital is committed to delivering quality healthcare with a patient-centric approach and advanced medical technology.",
        "Hamidia Hospital": "Hamidia Hospital offers a wide range of medical services with experienced staff and modern facilities.",
        "Chirayu Hospital": "Chirayu Hospital specializes in critical care and emergency services with a dedicated medical team.",
        "Manoriya Hospital": "Manoriya Hospital provides comprehensive healthcare solutions with a focus on patient safety and comfort.",
        "Sagar Multispeciality Hospital": "Sagar Multispeciality Hospital offers multidisciplinary medical services with advanced technology and compassionate care."
    }

    if request.method == 'POST':
        report_name = request.form.get('report_name')
        report_type = request.form.get('report_type')
        result = request.form.get('result')
        description = request.form.get('description')
        remark = request.form.get('remark')
        critical = request.form.get('critical')
        user_id = request.form.get('user_id')
        date = datetime.now().strftime('%Y-%m-%d')

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO reports (user_id, hospital_name, report_name, report_type, result, description, remark, critical, date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, hospital_name, report_name, report_type, result, description, remark, critical, date))
        conn.commit()
        conn.close()

        return redirect(url_for('hospital_dashboard'))

    hospital_description = hospital_descriptions.get(hospital_name, "")
    return render_template('hospital_dashboard.html', hospital_name=hospital_name, hospital_description=hospital_description)

@app.route('/api/hospitals')
def api_hospitals():
    # Return list of hospitals with coordinates
    hospitals = [
        {"name": "JK Hospital Bhopal", "lat": 23.259933, "lng": 77.412615},
        {"name": "City Hospital", "lat": 23.250000, "lng": 77.400000},
        {"name": "Green Valley Hospital", "lat": 23.270000, "lng": 77.420000},
        {"name": "Sunrise Medical Center", "lat": 23.265000, "lng": 77.430000}
    ]
    return jsonify(hospitals)

@app.route('/api/user/reports/<int:report_id>', methods=['DELETE'])
def api_delete_user_report(report_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'status': 'error', 'message': 'User not logged in'}), 401

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM reports WHERE id = ? AND user_id = ?', (report_id, user_id))
    report = cursor.fetchone()
    if not report:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Report not found'}), 404

    cursor.execute('DELETE FROM reports WHERE id = ? AND user_id = ?', (report_id, user_id))
    conn.commit()
    conn.close()

    return jsonify({'status': 'success', 'message': 'Report deleted'})

if __name__ == '__main__':
    app.run(debug=True)