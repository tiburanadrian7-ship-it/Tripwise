from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import os
from dotenv import load_dotenv
import google.generativeai as genai
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
import re
from datetime import date 

# ========== CONFIGURATION ==========
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "tripwise_secret_key")

# Google API
API_KEY = os.getenv("GOOGLE_API_KEY", "PUT_YOUR_KEY_HERE")
genai.configure(api_key=API_KEY)
chat_model = genai.GenerativeModel("gemini-2.5-flash")

# Database
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URI", 'mysql+pymysql://root:@localhost/tripwise')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ========== MODELS (MATCHING SQL SCHEMA) ==========

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column('user_id', db.Integer, primary_key=True)
    name = db.Column('full_name', db.String(255), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    password_hash = db.Column('password', db.String(255), nullable=True)

class Island(db.Model):
    __tablename__ = 'islands'
    id = db.Column('island_id', db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    # FIX: Mapped to 'island_image' from previous step
    image = db.Column('island_image', db.String(255), nullable=False)
    description = db.Column(db.Text)
    location = db.Column(db.String(255))
    region = db.Column(db.String(100))
    history = db.Column(db.Text) 
    map_coordinates = db.Column(db.String(255))
    
    @property
    def latitude(self):
        if self.map_coordinates:
            try:
                return float(self.map_coordinates.split(',')[0].strip())
            except:
                return None
        return None
    
    @property
    def longitude(self):
        if self.map_coordinates:
            try:
                return float(self.map_coordinates.split(',')[1].strip())
            except:
                return None
        return None

    @property
    def details(self):
        return self.history


class Establishment(db.Model):
    __tablename__ = 'establishments'
    id = db.Column('establishment_id', db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    type = db.Column(db.Enum('hotel', 'bar', 'restaurant'), nullable=False) 
    island_id = db.Column(db.Integer, db.ForeignKey('islands.island_id'))
    
    # NEW FIELDS ADDED FROM SCHEMA UPDATE
    location = db.Column(db.String(255))
    contact_number = db.Column(db.String(50))
    opening_hours = db.Column(db.String(100))
    description = db.Column(db.Text)
    rating = db.Column(db.Float)
    # CRITICAL FIX: Map the Python 'image' attribute to the SQL 'establishments_image' column
    image = db.Column('establishments_image', db.String(255), nullable=False)
    
    @property
    def category(self):
        return self.type


class Visit(db.Model):
    __tablename__ = 'visits'
    id = db.Column('visit_id', db.Integer, primary_key=True)
    island_id = db.Column(db.Integer, db.ForeignKey('islands.island_id'), nullable=False)
    visit_week = db.Column('visit_week', db.Date, nullable=False) 
    visit_month = db.Column('visit_month', db.Date, nullable=False)
    visit_year = db.Column('visit_year', db.Date, nullable=False)
    total_visits = db.Column('total_visit', db.Integer, nullable=False)
    island = db.relationship('Island', backref='visits')


# ========== DATABASE INIT (Updated with new Establishment fields) ==========
def init_db():
    print("Initializing MySQL Database...")
    try:
        with app.app_context():
            db.create_all() 
            print("✅ MySQL tables created or already exist.")

            # --- Island Data ---
            if not Island.query.first():
                sample_islands = [
                    Island(name='Alaminos Hundred Islands', image='hundred_islands.jpg', 
                            description='Famous national park with over 100 islands',
                            history='Protected area since 1940',
                            location='Alaminos', region='Pangasinan',
                            map_coordinates='16.1622,120.3621'), # ID 1
                    Island(name='Quezon Island', image='quezon_island.jpg',
                            description='Popular island for day trips',
                            history='Named after President Quezon',
                            location='Alaminos', region='Pangasinan',
                            map_coordinates='16.1660,120.3640'), # ID 2
                    Island(name='Imelda Island', image='imelda_island.jpg',
                            description='Small lodging and beach',
                            history='Named after Imelda Marcos',
                            location='Alaminos', region='Pangasinan',
                            map_coordinates='16.1680,120.3660') # ID 3
                ]
                db.session.add_all(sample_islands)
                db.session.commit()
                print("✅ Sample island data added.")

            # --- Establishment Data (Updated with image and other new fields) ---
            if not Establishment.query.first():
                sample_establishments = [
                    Establishment(name='Quezon Beach Resort', description='Beachfront resort',
                                    type='hotel', island_id=2, 
                                    image='quezon_resort.jpg', # NEW FIELD
                                    location='Quezon Island, Alaminos', # NEW FIELD
                                    rating=4.5, opening_hours='24/7'), # NEW FIELD
                    Establishment(name='Imelda Resort', description='Small cozy resort',
                                    type='hotel', island_id=3,
                                    image='imelda_resort.jpg', # NEW FIELD
                                    location='Imelda Island, Alaminos', # NEW FIELD
                                    rating=4.2, contact_number='09123456789'), # NEW FIELD
                    Establishment(name='Island Bar & Grill', description='Beachside bar and restaurant',
                                    type='bar', island_id=1,
                                    image='island_bar.jpg', # NEW FIELD
                                    location='Governor\'s Island, Alaminos', # NEW FIELD
                                    opening_hours='10:00 AM - 10:00 PM', rating=4.0) # NEW FIELD
                ]
                db.session.add_all(sample_establishments)
                db.session.commit()
                print("✅ Sample establishment data added.")

            # --- Visit Data ---
            if not Visit.query.first():
                def get_visit_data(island_id, week_day, total):
                    return Visit(
                        island_id=island_id, 
                        visit_week=date(2025, 11, week_day), 
                        visit_month=date(2025, 11, 1), 
                        visit_year=date(2025, 1, 1), 
                        total_visits=total
                    )
                
                sample_visits = [
                    get_visit_data(island_id=1, week_day=17, total=120),
                    get_visit_data(island_id=2, week_day=17, total=95),
                    get_visit_data(island_id=3, week_day=17, total=150),
                    get_visit_data(island_id=1, week_day=10, total=130),
                    get_visit_data(island_id=2, week_day=10, total=85),
                    get_visit_data(island_id=3, week_day=10, total=160)
                ]
                db.session.add_all(sample_visits)
                db.session.commit()
                print("✅ Sample visit data added.")
            
        print("✅ Database OK")
    except Exception as e:
        print(f"Database Error: {e}")
        print("ACTION NEEDED: Ensure MySQL/XAMPP is running and the 'tripwise' database exists and credentials are correct.")


init_db()

# ========== CHATBOT (Unchanged) ==========

def get_db_context(user_message):
    """Fetch relevant islands, establishments, and visit data for AI prompt."""
    
    islands = Island.query.filter(Island.name.ilike(f"%{user_message}%")).all()
    establishments = Establishment.query.filter(
        (Establishment.name.ilike(f"%{user_message}%")) |
        (Establishment.type.ilike(f"%{user_message}%"))
    ).all()

    if not islands:
        islands = Island.query.all()
        
    context = ""
    
    if islands:
        context += "Islands info (with location):\n"
        for i in islands:
            context += f"- ID {i.id}: {i.name}: {i.description}. Location: lat {i.latitude}, lon {i.longitude}\n"
            
    if establishments:
        context += "Establishment info:\n"
        for p in establishments:
            if p.island_id is None:
                island_name = "Not connected to any island"
            else:
                island = Island.query.get(p.island_id)
                island_name = island.name if island else "Unknown Island (Invalid ID)"
            
            # Uses property getter for category
            context += f"- {p.name} ({p.category}) at {island_name}: {p.description}\n"
            
    # Add Visit Data (Popularity Context)
    total_visits_data = db.session.query(
        Visit.island_id,
        db.func.sum(Visit.total_visits).label('annual_visits')
    ).filter(
        Visit.visit_month.between('2025-01-01', '2025-12-31') 
    ).group_by(Visit.island_id).order_by(db.desc('annual_visits')).all()

    if total_visits_data:
        context += "\nIsland Popularity Context (Total Visits in 2025):\n"
        for island_id, annual_visits in total_visits_data:
            island = Island.query.get(island_id)
            if island:
                context += f"- {island.name} (ID {island_id}): {annual_visits:,} total visitors.\n"
                
    return context


def link_islands_places(text):
    """Replace island/place names in AI-generated text with clickable links."""
    islands = Island.query.all()
    establishments = Establishment.query.all()

    for obj_list, base_url in [(islands, '/island/'), (establishments, '/place/')]:
        sorted_list = sorted(obj_list, key=lambda x: len(x.name), reverse=True)
        for obj in sorted_list:
            pattern = r'\b' + re.escape(obj.name) + r'\b'
            text = re.sub(pattern, f"<a href='{base_url}{obj.id}'>{obj.name}</a>", text)

    return text

@app.route("/ask", methods=["POST"])
def ask():
    data = request.json
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"response": "⚠️ Please type a message."})

    with app.app_context():
        db_context = get_db_context(user_message)
    
    prompt = f"""
You are WiseBot, a friendly travel assistant specializing in Philippine destinations.
Use the following information, especially the visitor statistics, to provide helpful suggestions to the user.
Do not mention the source of your information.

Information:
{db_context}

User: {user_message}
AI:
"""
    try:
        response = chat_model.generate_content(prompt)
        linked_response = link_islands_places(response.text)
        return jsonify({"response": linked_response})
    except Exception as e:
        return jsonify({"response": f"⚠️ Chat error: {str(e)}"})

# ========== ROUTES (Unchanged as they rely on the 'image' attribute, which is now mapped) ==========
@app.route("/")
def index():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        pwd = request.form.get("password", "")
        user = User.query.filter_by(email=email).first() 
        if user and check_password_hash(user.password_hash, pwd):
            session["user"] = email
            flash(f"Welcome back, {user.name}!", "success") 
            return redirect(url_for("home"))
        flash("Invalid credentials (email or password)", "danger")
    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        pwd = request.form.get("password", "")
        cpwd = request.form.get("confirm_password", "")

        if User.query.filter_by(email=email).first():
            flash("Email already exists", "warning")
        elif pwd != cpwd:
            flash("Passwords do not match", "danger")
        else:
            try:
                new_user = User(name=name, email=email, password_hash=generate_password_hash(pwd))
                db.session.add(new_user)
                db.session.commit()
                flash("Account created! You can now log in.", "success")
                return redirect(url_for("login"))
            except Exception as e:
                db.session.rollback()
                flash(f"Database error during sign up: {e}", "danger")
    return render_template("signup.html")


@app.route("/plan_trip", methods=["GET", "POST"])
def plan_trip():
    if "user" not in session:
        return redirect(url_for("login"))

    destinations_list = Island.query.all()

    if request.method == "POST":
        destination_ids = request.form.getlist("destinations")
        if not destination_ids:
            flash("Please select at least one destination.", "danger")
            return redirect(url_for("plan_trip"))

        try:
            budget_per_person = float(request.form.get("budget"))
            days = int(request.form.get("days"))
            people = int(request.form.get("people"))
        except (ValueError, TypeError):
            flash("Invalid numeric input for budget, days, or number of people.", "danger")
            return redirect(url_for("plan_trip"))

        selected_islands = Island.query.filter(Island.id.in_(destination_ids)).all()
        if not selected_islands:
            flash("Selected islands not found.", "danger")
            return redirect(url_for("plan_trip"))

        establishments = Establishment.query.filter(Establishment.island_id.in_([i.id for i in selected_islands])).all()
        db_context = ""
        for island in selected_islands:
            db_context += f"Island: {island.name}\nDescription: {island.description}\nDetails: {island.details}\n\n"
            island_establishments = [p for p in establishments if p.island_id == island.id]
            if island_establishments:
                db_context += "Places:\n"
                for p in island_establishments:
                    db_context += f"- {p.name} ({p.category}): {p.description}\n"
            db_context += "\n"

        islands_names = ', '.join([i.name for i in selected_islands])
        plan_prompt = (
            f"You are a Philippine travel expert. Create a detailed, day-by-day travel itinerary "
            f"for a trip to: {islands_names}. The trip length is exactly {days} days, for {people} people, "
            f"with a budget of PHP {budget_per_person} per person.\n\n"
            f"Use the following information about islands and places to make the itinerary realistic:\n{db_context}\n"
            "Include local food, transport, and estimated cost per day per person. "
            "Present the plan in clear Markdown with day headers: 'Day 1', 'Day 2', etc. "
            "Do not add extra days beyond the specified trip length."
        )

        try:
            response = chat_model.generate_content(plan_prompt)
            itinerary = response.text

            day_splits = re.split(r'Day\s+\d+[:.\s]*', itinerary, flags=re.IGNORECASE)
            filtered_itinerary = ""
            for i in range(1, min(days + 1, len(day_splits))):
                filtered_itinerary += f"Day {i}\n{day_splits[i].strip()}\n\n"

            return render_template(
                "plan_result.html",
                destination=islands_names,
                itinerary=filtered_itinerary.strip(),
                budget=budget_per_person,
                days=days,
                people=people
            )
        except Exception as e:
            flash(f"Error generating plan: {e}", "danger")
            return redirect(url_for("plan_trip"))

    return render_template("plan_trip.html", destinations=destinations_list)


@app.route("/home")
def home():
    if "user" not in session:
        return redirect(url_for("login"))
    
    user_data = User.query.filter_by(email=session["user"]).first()
    if not user_data:
        session.clear()
        return redirect(url_for("login"))
    
    # Query to get Top 10 Islands by total 2025 visits
    top_islands_data = db.session.query(
        Island.id,
        Island.name,
        Island.image, 
        db.func.sum(Visit.total_visits).label('annual_visits')
    ).join(Visit, Island.id == Visit.island_id).filter(
        Visit.visit_month.between('2025-01-01', '2025-12-31') 
    ).group_by(Island.id, Island.name, Island.image).order_by(
        db.desc('annual_visits')
    ).limit(10).all()
    
    islands = Island.query.all()
    establishments = Establishment.query.all()
    
    return render_template(
        "home.html", 
        user=user_data.name, 
        islands=islands, 
        places=establishments,
        top_islands=top_islands_data 
    )


@app.route("/island/<int:island_id>")
def island_details(island_id):
    if "user" not in session:
        return redirect(url_for("login"))

    island = Island.query.get_or_404(island_id)
    establishments = Establishment.query.filter_by(island_id=island.id).all()

    return render_template("island_details.html", island=island, places=establishments)


@app.route("/place/<int:place_id>")
def place_details(place_id):
    if "user" not in session:
        return redirect(url_for("login"))
    # The Establishment object now includes 'image', 'location', 'rating', etc.
    establishment = Establishment.query.get_or_404(place_id)
    return render_template("place_details.html", place=establishment)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ========== RUN ==========
if __name__ == "__main__":
    app.run(debug=True)