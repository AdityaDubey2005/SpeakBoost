from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from flask_cors import CORS
from flask_mysqldb import MySQL
from flask_bcrypt import Bcrypt
import os
import json
import tempfile
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
import librosa
from datetime import datetime
import base64 

load_dotenv()  # Load environment variables from .env file

app = Flask(__name__)


CORS(app)
bcrypt = Bcrypt(app)

# Configuration
app.secret_key = os.getenv('FLASK_SECRET_KEY')
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB')

# Initialize MySQL and OpenAI
mysql = MySQL(app)
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

from urllib.parse import quote

AI_ROLES = {
    'host': {
        'voice': 'nova',  # Professional female host
        'description': 'Main AI host for introductions and guidance'
    },
    'interviewer': {
        'voice': 'onyx',  # Authoritative male for job interviews
        'description': 'Professional interviewer for job scenarios'
    },
    'presenter': {
        'voice': 'fable',  # Engaging storyteller for presentations
        'description': 'Presentation coach and evaluator'
    },
    'negotiator': {
        'voice': 'echo',  # Deep male voice for negotiations
        'description': 'Business negotiation expert'
    }
}

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        # Ensure proper encoding for the avatar URL
        avatar_url = f"https://ui-avatars.com/api/?name={quote(username)}&background=random"
        print("Generated Avatar URL:", avatar_url)  # Debugging
        
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        # Insert data into the database without role
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO users (username, email, password, avatar_url, role) VALUES (%s, %s, %s, %s, %s)", 
                    (username, email, hashed_password, avatar_url, None))  
        mysql.connection.commit()
        cur.close()

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        # Check if email or password are missing
        if not email or not password:
            flash("Please enter both email and password.", "danger")
            return redirect(url_for('login'))

        cur = mysql.connection.cursor()
        # Only fetch username and password hash to reduce unnecessary data retrieval
        cur.execute("SELECT id, username, password FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()

        # Check if user exists and password is correct
        if user and bcrypt.check_password_hash(user[2], password):  # user[2] is the hashed password
            session['user_id'] = user[0]  # Store user ID in session
            session['username'] = user[1]  # Store username in session
            flash("Login successful!", "success")
            return redirect(url_for('set_role'))  # Redirect to role setup page if necessary
        else:
            flash("Invalid email or password.", "danger")
            return redirect(url_for('login'))  # Redirect back to login page in case of invalid credentials

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

@app.route('/set_role', methods=['GET', 'POST'])
def set_role():
    try:
        if 'user_id' not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for('login'))

        if request.method == 'POST':
            role = request.form.get('role')
            age = request.form.get('age')
            interests = request.form.get('interests')
            communication_rating = request.form.get('communication_rating')

            cur = mysql.connection.cursor()
            cur.execute("""
                UPDATE users 
                SET role = %s, age = %s, interests = %s, communication_rating = %s 
                WHERE id = %s
            """, (role, age, interests, communication_rating, session['user_id']))
            mysql.connection.commit()
            cur.close()

            flash("Profile updated successfully!", "success")
            return redirect(url_for('profile'))

        # GET request - show the form
        cur = mysql.connection.cursor()
        cur.execute("SELECT username, avatar_url FROM users WHERE id = %s", (session['user_id'],))
        user = cur.fetchone()
        cur.close()

        return render_template('set_role.html', 
                             username=user[0] if user else "Unknown",
                             avatar_url=user[1] if user and user[1] else 'https://api.multiavatar.com/default.svg')
    except Exception as e:
        print(f"Error in set_role: {str(e)}")
        flash("An error occurred. Please try again.", "error")
        return redirect(url_for('profile'))

@app.route('/profile')
def profile():
    if 'user_id' not in session:  # Check if the user is logged in
        flash("Please log in to view your profile.", "warning")
        return redirect(url_for('login'))

    user_id = session.get('user_id')

    # Fetch the user's info from the database (username, avatar_url, and role)
    cur = mysql.connection.cursor()
    cur.execute("SELECT username, avatar_url, role, age, interests, communication_rating FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()

    if user:
        username = user[0]
        avatar_url = user[1] if user[1] else 'https://api.multiavatar.com/default.svg'  # Default avatar if None
        role = user[2] if user[2] else 'Not specified'  # Default to 'Not specified' if no role is set
        age = user[3] if user[3] else 'Not specified'  # Default
        interests = user[4] if user[4] else 'Not specified'  # Default
        communication_rating = user[5] if user[5] else 'Not specified'  #

    else:
        username = "Unknown"
        avatar_url = 'https://api.multiavatar.com/default.svg'  # Default avatar URL
        role = 'Not specified'
        age = 'Not specified'
        interests = 'Not specified'
        communication_rating = 'Not specified'
    
    return render_template('profile.html', username=username, avatar_url=avatar_url, role=role
                               , age=age, interests=interests, communication_rating=communication_rating)



@app.route('/exercises')
def exercises():
    if 'user_id' not in session:
        flash("Please log in to access exercises.", "warning")
        return redirect(url_for('login'))
    
    user_id = session.get('user_id')
    
    # Fetch user data
    cur = mysql.connection.cursor()
    cur.execute("SELECT username, avatar_url FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()
    
    username = user[0] if user else "Unknown"
    avatar_url = user[1] if user and user[1] else 'https://api.multiavatar.com/default.svg'
    
    # Hardcoded exercises data with multiple choice options
    exercises_data = [
        {
            "id": 1,
            "question": "Which of the following is the most effective way to show active listening?",
            "options": [
                "Interrupting with your own story",
                "Nodding and maintaining eye contact",
                "Looking at your phone occasionally",
                "Thinking about your response while they speak"
            ],
            "correct": 1,  # Index of correct answer
            "category": "Active Listening"
        },
        {
            "id": 2,
            "question": "What is the best approach when giving constructive feedback?",
            "options": [
                "Wait until you're angry to address issues",
                "Focus on personal characteristics",
                "Be specific and focus on behaviors",
                "Give feedback in public settings"
            ],
            "correct": 2,
            "category": "Feedback Skills"
        },
        {
            "id": 3,
            "question": "How can you improve your non-verbal communication?",
            "options": [
                "Cross your arms to show confidence",
                "Avoid eye contact to seem mysterious",
                "Keep a neutral face at all times",
                "Mirror the other person's body language appropriately"
            ],
            "correct": 3,
            "category": "Body Language"
        },
        {
            "id": 4,
            "question": "What is the best way to handle disagreements in a conversation?",
            "options": [
                "Stand your ground and never compromise",
                "Listen to understand and find common ground",
                "Change the subject immediately",
                "Agree with everything to avoid conflict"
            ],
            "correct": 1,
            "category": "Conflict Resolution"
        },
        {
            "id": 5,
            "question": "Which communication channel is most appropriate for delivering sensitive feedback?",
            "options": [
                "Email",
                "Text message",
                "Face-to-face conversation",
                "Group chat"
            ],
            "correct": 2,
            "category": "Communication Channels"
        },
        {
            "id": 6,
            "question": "What is the most effective way to start a presentation?",
            "options": [
                "Apologize for being nervous",
                "Start with a compelling story or statistic",
                "Read directly from your slides",
                "Give a detailed personal introduction"
            ],
            "correct": 1,
            "category": "Public Speaking"
        },
        {
            "id": 7,
            "question": "How can you best handle interruptions during a conversation?",
            "options": [
                "Stop talking immediately",
                "Talk louder to be heard",
                "Ignore the interruption completely",
                "Politely acknowledge and redirect back to the topic"
            ],
            "correct": 3,
            "category": "Conversation Skills"
        }
    ]
    
    return render_template('exercises.html', 
                         exercises=exercises_data, 
                         username=username, 
                         avatar_url=avatar_url)

# Communication scenarios configuration
COMMUNICATION_SCENARIOS = {
    'interview': {
        'title': 'Job Interview',
        'description': 'Practice common interview questions and responses',
        'prompts': [
            'Tell me about yourself and your professional background.',
            'What are your greatest strengths and weaknesses?',
            'Where do you see yourself in five years?'
        ],
        'metrics': {
            'target_wpm': (130, 150),
            'tone': 'professional and confident',
            'key_points': ['clear articulation', 'structured responses', 'positive attitude']
        }
    },
    'presentation': {
        'title': 'Business Presentation',
        'description': 'Practice delivering engaging presentations',
        'prompts': [
            'Present a project proposal to stakeholders',
            'Give a quarterly business update',
            'Pitch a new product or service'
        ],
        'metrics': {
            'target_wpm': (140, 160),
            'tone': 'authoritative and engaging',
            'key_points': ['clear structure', 'engaging delivery', 'audience awareness']
        }
    },
    'negotiation': {
        'title': 'Business Negotiation',
        'description': 'Practice negotiation skills and techniques',
        'prompts': [
            'Negotiate a salary increase',
            'Discuss contract terms with a client',
            'Resolve a business conflict'
        ],
        'metrics': {
            'target_wpm': (120, 140),
            'tone': 'assertive yet diplomatic',
            'key_points': ['active listening', 'clear objectives', 'win-win solutions']
        }
    }
}

# Add a new route for welcome message
@app.route('/get_welcome_message', methods=['GET'])
def get_welcome_message():
    try:
        welcome_text = """
        Welcome to SpeakBoost! I'm Nova, your AI communication coach. 
        I'll guide you through various communication scenarios to help improve your speaking skills. 
        Please select a scenario to begin your practice session.
        """
        
        # Generate welcome audio
        audio_response = client.audio.speech.create(
            model="tts-1",
            voice=AI_ROLES['host']['voice'],
            input=welcome_text
        )

        # Convert to base64
        import base64
        audio_base64 = base64.b64encode(audio_response.content).decode('utf-8')

        return jsonify({
            'message': welcome_text,
            'audio': audio_base64
        })
    except Exception as e:
        print(f"Error generating welcome message: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/get_scenario_question', methods=['POST'])
def get_scenario_question():
    if 'user_id' not in session:
        return jsonify({'error': 'User not authenticated'}), 401

    scenario_id = request.json.get('scenario')
    if scenario_id not in COMMUNICATION_SCENARIOS:
        return jsonify({'error': 'Invalid scenario'}), 400

    try:
        scenario = COMMUNICATION_SCENARIOS[scenario_id]
        
        # Select appropriate AI voice based on scenario
        ai_voice = {
            'interview': AI_ROLES['interviewer']['voice'],
            'presentation': AI_ROLES['presenter']['voice'],
            'negotiation': AI_ROLES['negotiator']['voice']
        }.get(scenario_id, AI_ROLES['host']['voice'])

        question_prompt = f"""
        You are an AI interviewer for a {scenario['title']} scenario.
        Generate a natural, conversational question based on this context: {scenario['description']}.
        Select and adapt one of these prompts: {scenario['prompts']}.
        Make it sound natural, as if asked by a real person.
        """

        # Get question from GPT-4
        question_response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a professional interviewer."},
                {"role": "user", "content": question_prompt}
            ],
            temperature=0.7
        )
        
        question_text = question_response.choices[0].message.content

        # Generate speech with scenario-specific voice
        audio_response = client.audio.speech.create(
            model="tts-1",
            voice=ai_voice,
            input=question_text
        )

        # Convert to base64
        import base64
        audio_base64 = base64.b64encode(audio_response.content).decode('utf-8')

        return jsonify({
            'question': question_text,
            'audio': audio_base64,
            'voice': ai_voice
        })

    except Exception as e:
        print(f"Error generating scenario question: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/get_scenarios')
def get_scenarios():
    """Return available communication scenarios"""
    return jsonify(COMMUNICATION_SCENARIOS)

# Add these helper functions before your analyze_speech route
def calculate_feedback_quality(transcript, feedback, analysis):
    """Calculate feedback quality metrics"""
    try:
        # Check relevance to transcript
        transcript_words = set(transcript.lower().split())
        feedback_words = set(feedback.lower().split())
        relevance_score = len(transcript_words & feedback_words) / len(transcript_words)
        
        # Check conciseness (aim for 150-200 chars)
        ideal_length = 175
        length_score = 1.0 - min(abs(len(feedback) - ideal_length) / ideal_length, 1.0)
        
        # Check if feedback addresses key points
        key_points = {
            'wpm_mentioned': any(w in feedback.lower() for w in ['wpm', 'speed', 'pace']),
            'strength_mentioned': any(s.lower() in feedback.lower() for s in analysis['strengths']),
            'improvement_mentioned': any(i.lower() in feedback.lower() for i in analysis['areas_for_improvement']),
            'grammar_mentioned': 'grammar' in feedback.lower() and len(analysis['grammar']['issues']) > 0
        }
        completeness_score = sum(key_points.values()) / len(key_points)
        
        # Calculate overall score
        accuracy_score = (relevance_score + length_score + completeness_score) / 3
        
        return accuracy_score, {
            'relevance': relevance_score,
            'conciseness': length_score,
            'completeness': completeness_score
        }
    except Exception as e:
        print(f"Error calculating feedback quality: {str(e)}")
        return 0.0, {}

def get_successful_patterns(scenario_id, cur):
    """Retrieve previously successful feedback patterns"""
    try:
        cur.execute("""
            SELECT feedback 
            FROM feedback_tracking 
            WHERE scenario_id = %s 
            AND accuracy_score >= 0.8 
            ORDER BY accuracy_score DESC, 
                     CASE WHEN user_rating IS NULL THEN 0 ELSE user_rating END DESC
            LIMIT 3
        """, (scenario_id,))
        return cur.fetchall()
    except Exception as e:
        print(f"Error getting successful patterns: {str(e)}")
        return []

@app.route('/analyze_speech', methods=['POST'])
def analyze_speech():
    """Analyze real-time speech using OpenAI with learning capabilities"""
    if 'user_id' not in session:
        return jsonify({'error': 'User not authenticated'}), 401
        
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file provided'}), 400
    
    scenario_id = request.form.get('scenario')
    if scenario_id not in COMMUNICATION_SCENARIOS:
        return jsonify({'error': 'Invalid scenario'}), 400

    try:
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_audio:
            audio_file = request.files['audio']
            audio_file.save(temp_audio.name)
            
            # Get audio duration using librosa with error handling
            try:
                y, sr = librosa.load(temp_audio.name, sr=None)
                duration = librosa.get_duration(y=y, sr=sr)
            except Exception as audio_error:
                print(f"Error loading audio: {str(audio_error)}")
                duration = 0
            
            # Transcribe with Whisper
            with open(temp_audio.name, 'rb') as audio:
                transcript_response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio
                )
            transcript = transcript_response.text
            
            # Calculate WPM
            words = len(transcript.split())
            wpm = (words / duration) * 60 if duration > 0 else 0

            # Get scenario details and successful patterns
            scenario = COMMUNICATION_SCENARIOS[scenario_id]
            cur = mysql.connection.cursor()
            successful_patterns = get_successful_patterns(scenario_id, cur)

            # Analyze with GPT-4
            analysis_prompt = f"""
            Analyze this speech for a {scenario['title']} scenario:
            "{transcript}"
            
            Target metrics:
            - WPM: {scenario['metrics']['target_wpm']}
            - Desired tone: {scenario['metrics']['tone']}
            - Key points: {', '.join(scenario['metrics']['key_points'])}
            
            Previous successful analyses:
            {json.dumps([p[0] for p in successful_patterns]) if successful_patterns else 'None available'}
            
            Provide detailed analysis in this JSON format:
            {{
                "metrics": {{
                    "clarity": <score 1-10>,
                    "confidence": <score 1-10>,
                    "professionalism": <score 1-10>,
                    "engagement": <score 1-10>
                }},
                "tone_analysis": "<brief tone analysis>",
                "strengths": ["<key strength>"],
                "areas_for_improvement": ["<specific suggestion>"],
                "recommended_phrases": ["<better phrasing>"],
                "voice_coaching_tips": ["<specific tip>"],
                "grammar": {{
                    "score": <score 1-10>,
                    "issues": [
                        {{
                            "error": "<grammar issue>",
                            "correction": "<correction>",
                            "explanation": "<brief explanation>"
                        }}
                    ]
                }}
            }}
            """

            analysis_response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a precise speech analyst focusing on actionable insights."},
                    {"role": "user", "content": analysis_prompt}
                ],
                temperature=0.5
            )
            
            analysis = json.loads(analysis_response.choices[0].message.content)

            # Generate concise feedback
            feedback_prompt = f"""
            Create a BRIEF, focused feedback (max 250 characters) on the speech said by the user that includes:
            1. WPM ({wpm:.0f} vs target {scenario['metrics']['target_wpm']})
            2. ONE key strength
            3. ONE main improvement
            4. ONE grammar point if score < 7
            Keep it natural and encouraging. 

            Previous successful feedback patterns:
            {json.dumps([p[0] for p in successful_patterns]) if successful_patterns else 'None available'}
            """

            feedback_response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are Nova, giving concise, focused feedback."},
                    {"role": "user", "content": feedback_prompt}
                ],
                temperature=0.5
            )

            voice_feedback = feedback_response.choices[0].message.content

            # Validate feedback quality
            accuracy_score, metrics = calculate_feedback_quality(transcript, voice_feedback, analysis)

            # Regenerate if quality is low
            if accuracy_score < 0.7:
                feedback_prompt += "\nPrevious feedback wasn't specific enough. Be more precise and relevant."
                feedback_response = client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "You are Nova, focusing on precise feedback."},
                        {"role": "user", "content": feedback_prompt}
                    ],
                    temperature=0.3
                )
                voice_feedback = feedback_response.choices[0].message.content

            # Store feedback for learning
            cur.execute("""
                INSERT INTO feedback_tracking 
                (scenario_id, transcript, feedback, analysis, accuracy_score, was_regenerated, user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                scenario_id,
                transcript,
                voice_feedback,
                json.dumps(analysis),
                accuracy_score,
                accuracy_score < 0.7,  # was_regenerated
                session['user_id']
            ))
            mysql.connection.commit()

            # Generate audio feedback
            feedback_audio = client.audio.speech.create(
                model="tts-1",
                voice=AI_ROLES['host']['voice'],
                input=voice_feedback
            )
            feedback_audio_base64 = base64.b64encode(feedback_audio.content).decode('utf-8')

            # Save analysis report
            cur.execute("""
                INSERT INTO speech_analysis_reports 
                (user_id, scenario_id, transcript, words_per_minute, duration,
                speaking_clarity, speaking_confidence, speaking_professionalism,
                tone_analysis, strengths, areas_for_improvement,
                recommended_phrases, voice_coaching_tips, sentiment_analysis,
                structure_feedback, audio_duration, grammar_analysis)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                session['user_id'],
                scenario_id,
                transcript,
                wpm,
                duration,
                analysis['metrics']['clarity'],
                analysis['metrics']['confidence'],
                analysis['metrics']['professionalism'],
                analysis['tone_analysis'],
                json.dumps(analysis['strengths']),
                json.dumps(analysis['areas_for_improvement']),
                json.dumps(analysis['recommended_phrases']),
                json.dumps(analysis['voice_coaching_tips']),
                voice_feedback,
                analysis['tone_analysis'],
                duration,
                json.dumps(analysis['grammar'])
            ))
            mysql.connection.commit()

            # Prepare response
            results = {
                'transcript': transcript,
                'wpm': wpm,
                'duration': duration,
                'analysis': analysis,
                'voice_feedback': voice_feedback,
                'feedback_audio': feedback_audio_base64,
                'scenario': scenario['title'],
                'word_count': words,
                'feedback_metrics': metrics
            }

            return jsonify(results)

    except Exception as e:
        print(f"Error analyzing speech: {str(e)}")
        return jsonify({'error': str(e)}), 500

    finally:
        if 'cur' in locals():
            cur.close()
        if 'temp_audio' in locals():
            os.unlink(temp_audio.name)

@app.route('/speech-analysis')
def speech_analysis():
    """Render the speech analysis page"""
    if 'user_id' not in session:
        flash("Please log in to access speech analysis.", "warning")
        return redirect(url_for('login'))
    
    # Fetch user data for the sidebar
    cur = mysql.connection.cursor()
    cur.execute("SELECT username, avatar_url FROM users WHERE id = %s", (session['user_id'],))
    user = cur.fetchone()
    cur.close()
    
    username = user[0] if user else "Unknown"
    avatar_url = user[1] if user and user[1] else 'https://api.multiavatar.com/default.svg'
    
    return render_template('speech_analysis.html', 
                         username=username, 
                         avatar_url=avatar_url)



@app.route('/generate_questions', methods=['GET'])
def generate_questions():
    """Generate English grammar questions using OpenAI"""
    if 'user_id' not in session:
        return jsonify({'error': 'User not authenticated'}), 401

    try:
        prompt = """
        Generate 10 English grammar questions from easy to difficult. 
        Format the response as a JSON array with the following structure for each question:
        {
            "id": <number>,
            "category": "<grammar category>",
            "question": "<question text>",
            "options": ["<option1>", "<option2>", "<option3>", "<option4>"],
            "correct": <index of correct option (0-3)>
        }
        
        Include questions covering:
        - Basic punctuation
        - Subject-verb agreement
        - Verb tenses
        - Articles and determiners
        - Complex sentence structures
        - Conditional sentences
        - Reported speech
        """

        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert English language teacher."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )

        questions = json.loads(response.choices[0].message.content)
        return jsonify({'questions': questions})

    except Exception as e:
        print(f"Error generating questions: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/reports')
def reports():
    try:
        if 'user_id' not in session:
            flash("Please log in to view reports.", "warning")
            return redirect(url_for('login'))

        cur = mysql.connection.cursor()
        
        # Get user info
        cur.execute("SELECT username, avatar_url FROM users WHERE id = %s", (session['user_id'],))
        user = cur.fetchone()
        
        # Get all reports with complete metrics
        cur.execute("""
            SELECT 
                id, scenario_id, transcript, words_per_minute, duration,
                speaking_clarity, speaking_confidence, speaking_engagement,
                speaking_professionalism, tone_analysis, strengths,
                areas_for_improvement, recommended_phrases, voice_coaching_tips,
                sentiment_score, sentiment_analysis, filler_words_count,
                filler_words_list, grammar_issues, structure_feedback,
                timestamp, audio_duration
            FROM speech_analysis_reports 
            WHERE user_id = %s 
            ORDER BY timestamp DESC
        """, (session['user_id'],))
        
        reports = []
        for row in cur.fetchall():
            report = {
                'id': row[0],
                'scenario': row[1] or 'General Practice',
                'transcript': row[2],
                'metrics': {
                    'wpm': float(row[3]) if row[3] else 0,
                    'duration': float(row[4]) if row[4] else 0,
                    'clarity': float(row[5]) if row[5] else 0,
                    'confidence': float(row[6]) if row[6] else 0,
                    'engagement': float(row[7]) if row[7] else 0,
                    'professionalism': float(row[8]) if row[8] else 0
                },
                'analysis': {
                    'tone': row[9],
                    'strengths': json.loads(row[10]) if row[10] else [],
                    'improvements': json.loads(row[11]) if row[11] else [],
                    'phrases': json.loads(row[12]) if row[12] else [],
                    'coaching_tips': json.loads(row[13]) if row[13] else []
                },
                'sentiment': {
                    'score': float(row[14]) if row[14] else 0,
                    'analysis': row[15]
                },
                'grammar': {
                    'filler_count': row[16] or 0,
                    'filler_words': json.loads(row[17]) if row[17] else [],
                    'issues': json.loads(row[18]) if row[18] else []
                },
                'feedback': row[19],
                'timestamp': row[20].strftime('%Y-%m-%d %H:%M:%S'),
                'audio_duration': float(row[21]) if row[21] else 0
            }
            reports.append(report)
        
        cur.close()

        return render_template('reports.html',
                             username=user[0] if user else "Unknown",
                             avatar_url=user[1] if user else 'https://api.multiavatar.com/default.svg',
                             reports=reports)
    except Exception as e:
        print(f"Error in reports: {str(e)}")
        flash("An error occurred loading reports.", "error")
        return redirect(url_for('profile'))