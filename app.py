from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_session import Session
import boto3
import json
import uuid
from botocore.exceptions import NoCredentialsError

app = Flask(__name__)

# Configure session to use filesystem (you can change this for production)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# RDS configuration
DB_USER = 'admin'
DB_PASSWORD = 'sathwik1991'
DB_HOST = 'db-1.cfoouy2sarb3.us-east-2.rds.amazonaws.com'
DB_NAME = 'db-1'
app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# S3 configuration
S3_BUCKET = 'sathwik1991'
S3_REGION = 'us-east-2'
AWS_ACCESS_KEY_ID = '<Key ID>'
AWS_SECRET_ACCESS_KEY='<Key>'
s3 = boto3.client('s3', aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY, region_name='us-east-2')

# Lambda client
lambda_client = boto3.client('lambda',aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY, region_name=S3_REGION)

# Define User model for SQLAlchemy
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True)
    password = db.Column(db.String(80), nullable=False)

# Define UploadedFile model for SQLAlchemy
class UploadedFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    file_name = db.Column(db.String(120), nullable=False)
    s3_key = db.Column(db.String(120), nullable=False)
    email_addresses = db.Column(db.String(500), nullable=False)

# Function to check password requirements
def check_password_requirements(password):
    missing_requirements = []
    if len(password) < 8:
        missing_requirements.append('be at least 8 characters long')
    if not any(c.islower() for c in password):
        missing_requirements.append('at least one lowercase letter')
    if not any(c.isupper() for c in password):
        missing_requirements.append('at least one uppercase letter')
    if not any(c.isdigit() for c in password):
        missing_requirements.append('at least one digit')
    return missing_requirements

# Initialize database (create tables if they don't exist)
with app.app_context():
    db.create_all()

# Route for index page (sign-in form)
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Check user credentials
        user = User.query.filter_by(username=username, password=password).first()

        if user:
            session['user_id'] = user.id
            return redirect(url_for('upload_file'))
        else:
            flash('Invalid username or password', 'danger')

    return render_template('index.html')

# Route for sign-up page
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Check password requirements
        missing_requirements = check_password_requirements(password)

        if missing_requirements:
            return render_template('signup.html', missing_requirements=missing_requirements)
        elif password != confirm_password:
            flash('Passwords do not match', 'danger')
            return render_template('signup.html')

        # Save new user to database
        new_user = User(username=email, password=password)
        db.session.add(new_user)
        db.session.commit()

        flash('Account created successfully! Please sign in.', 'success')
        return redirect(url_for('index'))

    return render_template('signup.html')

# Route for upload page
@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        file = request.files['file']
        emails = request.form['emails']
        email_list = emails.split(',')

        # Generate unique S3 key
        s3_key = str(uuid.uuid4()) + "-" + file.filename

        try:
            s3.upload_fileobj(
                file,
                S3_BUCKET,
                s3_key,
                #ExtraArgs={"ACL": "public-read"}
            )

            # Save file info to DB
            new_file = UploadedFile(
                user_id=session['user_id'],
                file_name=file.filename,
                s3_key=s3_key,
                email_addresses=emails
            )
            db.session.add(new_file)
            db.session.commit()

            # Invoke Lambda function to send emails
            file_url = f'https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{s3_key}'
            print (file_url)
            lambda_payload = {
                "file_url": file_url,
                "email_addresses": email_list
            }
            lambda_client.invoke(
                FunctionName='cloud',
                InvocationType='Event',
                Payload=json.dumps(lambda_payload)
            )

            flash('File successfully uploaded and notifications sent!', 'success')
        except NoCredentialsError:
            flash('Credentials not available', 'danger')
        except Exception as e:
            flash(str(e), 'danger')

        return redirect(url_for('upload_file'))

    return render_template('upload_file.html')

if __name__ == '__main__':
    app.run(debug=True)
