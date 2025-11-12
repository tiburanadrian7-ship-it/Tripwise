from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import os
from dotenv import load_dotenv
import google.generativeai as genai
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
import re

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

# ========== MODELS ==========
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

class Island(db.Model):
    __tablename__ = 'islands'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    image = db.Column(db.String(100))
    description = db.Column(db.Text)
    details = db.Column(db.Text)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

class Place(db.Model):
    __tablename__ = 'places'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    image = db.Column(db.String(100))
    description = db.Column(db.Text)
    category = db.Column(db.String(50))
    island_id = db.Column(db.Integer, db.ForeignKey('islands.id'))

class Visit(db.Model):
    __tablename__ = 'visits'
    id = db.Column(db.Integer, primary_key=True)
    island_id = db.Column(db.Integer, db.ForeignKey('islands.id'), nullable=False)
    visit_month = db.Column(db.Date, nullable=False)
    total_visits = db.Column(db.Integer, nullable=False)
    island = db.relationship('Island', backref='visits')


# ========== DATABASE INIT ==========
def init_db():
    print("Initializing MySQL Database...")
    try:
        with app.app_context():
            db.create_all()
            print("✅ MySQL tables created or already exist.")

            if not Island.query.first():
                # Corrected sample image names for the 3 sample islands
                sample_islands = [
                    Island(name='Hundred Islands, Pangasinan', image='hundred_islands.jpg', 
                           description='124 islands with beaches, caves & marine life.',
                           details='The Hundred Islands National Park features 124 islands...',
                           latitude=16.27, longitude=120.03),
                    Island(name='Governors Island', image='governor_island.jpg',
                           description='Developed island with cottages and viewing decks.',
                           details='Governors Island is developed for tourism...',
                           latitude=16.268, longitude=120.039),
                    Island(name='Quezon Island', image='quezon_island.jpg',
                           description='Picnic area, snorkeling, and swimming zones.',
                           details='Quezon Island is known for its shallow waters...',
                           latitude=16.2682, longitude=120.0405)
                ]
                db.session.add_all(sample_islands)
                db.session.commit()
                print("✅ Sample island data added.")

            if not Place.query.first():
                sample_places = [
                    Place(name='Sunset View Hotel', image='sunset_hotel.jpg', description='Cozy hotel with a sea view.',
                          category='hotel', island_id=1),
                    Place(name='Island Bistro', image='island_bistro.jpg', description='Local seafood and Filipino dishes.',
                          category='restaurant', island_id=1),
                    Place(name='Seaside Inn', image='seaside_inn.jpg', description='Affordable accommodation near the beach.',
                          category='hotel', island_id=2),
                    Place(name='Pangasinan Grill', image='pangasinan_grill.jpg',
                          description='Traditional Filipino cuisine.', category='restaurant', island_id=2)
                ]
                db.session.add_all(sample_places)
                db.session.commit()
                print("✅ Sample place data added.")
            
        print("✅ Database OK")
    except Exception as e:
        print(f"Database Error: {e}")
        print("ACTION NEEDED: Ensure MySQL/XAMPP is running and the 'tripwise' database exists.")


init_db()

# ========== CHATBOT ==========

def get_db_context(user_message):
    """Fetch relevant islands, places, and visit data for AI prompt."""
    
    islands = Island.query.filter(Island.name.ilike(f"%{user_message}%")).all()
    places = Place.query.filter(
        (Place.name.ilike(f"%{user_message}%")) |
        (Place.category.ilike(f"%{user_message}%"))
    ).all()

    if not islands:
        islands = Island.query.all()
        
    context = ""
    
    if islands:
        context += "Islands info (with location):\n"
        for i in islands:
            context += f"- ID {i.id}: {i.name}: {i.description}. Location: lat {i.latitude}, lon {i.longitude}\n"
            
    if places:
        context += "Places info:\n"
        for p in places:
            # --- MODIFIED LOGIC START ---
            if p.island_id is None:
                island_name = "Not connected to any island"
            else:
                # Only query the database if island_id is not None
                island = Island.query.get(p.island_id)
                # 'Unknown Island' handles cases where the ID exists but points to a deleted island
                island_name = island.name if island else "Unknown Island (Invalid ID)"
            
            context += f"- {p.name} ({p.category}) at {island_name}: {p.description}\n"
            # --- MODIFIED LOGIC END ---
            
    # Add Visit Data (Popularity Context)
    total_visits_data = db.session.query(
        Visit.island_id,
        db.func.sum(Visit.total_visits).label('annual_visits')
    ).filter(
        Visit.visit_month.between('2024-01-01', '2024-12-31')
    ).group_by(Visit.island_id).order_by(db.desc('annual_visits')).all()

    if total_visits_data:
        context += "\nIsland Popularity Context (Total Visits in 2024):\n"
        for island_id, annual_visits in total_visits_data:
            island = Island.query.get(island_id)
            if island:
                context += f"- {island.name} (ID {island_id}): {annual_visits:,} total visitors.\n"
                
    return context


def link_islands_places(text):
    """Replace island/place names in AI-generated text with clickable links."""
    islands = Island.query.all()
    places = Place.query.all()

    for obj_list, base_url in [(islands, '/island/'), (places, '/place/')]:
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

# ========== ROUTES ==========
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

        places = Place.query.filter(Place.island_id.in_([i.id for i in selected_islands])).all()
        db_context = ""
        for island in selected_islands:
            db_context += f"Island: {island.name}\nDescription: {island.description}\nDetails: {island.details}\n\n"
            island_places = [p for p in places if p.island_id == island.id]
            if island_places:
                db_context += "Places:\n"
                for p in island_places:
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
    
    # Query to get Top 10 Islands by total 2024 visits
    top_islands_data = db.session.query(
        Island.id,
        Island.name,
        Island.image,
        db.func.sum(Visit.total_visits).label('annual_visits')
    ).join(Visit, Island.id == Visit.island_id).filter(
        Visit.visit_month.between('2024-01-01', '2024-12-31')
    ).group_by(Island.id, Island.name, Island.image).order_by(
        db.desc('annual_visits')
    ).limit(10).all()
    
    islands = Island.query.all()
    places = Place.query.all()
    
    return render_template(
        "home.html", 
        user=user_data.name, 
        islands=islands, 
        places=places,
        top_islands=top_islands_data 
    )


@app.route("/island/<int:island_id>")
def island_details(island_id):
    if "user" not in session:
        return redirect(url_for("login"))

    island = Island.query.get_or_404(island_id)
    places = Place.query.filter_by(island_id=island.id).all()

    return render_template("island_details.html", island=island, places=places)


@app.route("/place/<int:place_id>")
def place_details(place_id):
    if "user" not in session:
        return redirect(url_for("login"))
    place = Place.query.get_or_404(place_id)
    return render_template("place_details.html", place=place)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ========== RUN ==========
if __name__ == "__main__":
    app.run(debug=True)