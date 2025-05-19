from flask import Flask, request, jsonify
from functools import wraps
import jwt
import psycopg2
import psycopg2.extras
import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = '12345'

def get_db_connection():
    conn = psycopg2.connect(
        host='127.0.0.1',
        database='ProjetoBD',
        user='igor',
        port = '5432',
        password='123'
    )
    return conn

def create_response(status, errors=None, results=None):
    response = {
        'status': status
    }
    if errors is not None:
        response['errors'] = errors
    if results is not None:
        response['results'] = results
    elif results is None:
        response['result'] = "null"
    return response

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(" ")[1]
        if not token:
            return jsonify({'message': 'Token is missing!'}), 400
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = data['username']
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired!'}), 400
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Token is invalid!'}), 400
        return f(current_user, *args, **kwargs)
    return decorated


@app.route('/igor/register/<user_type>', methods=['POST'])
def register_user(user_type):
    data = request.json
    conn = get_db_connection()
    cur = conn.cursor()

    required_fields_person = ['username', 'email', 'password', 'first_name', 'last_name', 'phone','endereco']
    required_fields_instructor = ['username', 'email', 'password', 'first_name', 'last_name', 'phone','endereco','role','type']
    date = datetime.datetime.now().strftime('%Y-%m-%d')
    try:
        if user_type == 'student' or 'staff':
            print(user_type)
            missing_fields = [field for field in required_fields_person if field not in data]
        elif user_type in ['instructor']:
            missing_fields = [field for field in required_fields_instructor if field not in data]
        else:
            return jsonify(create_response(400, 'Invalid user type'))

        if missing_fields:
            return jsonify(create_response(400, f"{', '.join(missing_fields)} cannot be null"))

        if user_type in ['student', 'staff']:

            cur.execute("SELECT * FROM person WHERE username = %s OR email = %s FOR UPDATE", (data['username'], data['email']))
            if cur.fetchone():
                return jsonify(create_response(400, 'Username or email already exists'))
            cur.execute(
                "INSERT INTO person (username, email, password, first_name, last_name, phone, endereco) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING user_id",
                (data['username'], data['email'], data['password'], data['first_name'], data['last_name'], data['phone'], data['endereco'])
            )
            user_id = cur.fetchone()[0]
            if user_type == 'student':
                cur.execute("INSERT INTO students (person_user_id,enrollment_date) VALUES (%s,%s)", (user_id,date,))
            elif user_type == 'staff':
                cur.execute("INSERT INTO employee (person_user_id) VALUES (%s)", (user_id,))
                cur.execute("INSERT INTO staff (employee_person_user_id) VALUES (%s)", (user_id,))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify(create_response(200, results=user_id))
        elif user_type == 'instructor':
            # Check if username/email already exists in PERSON (not instructor)
            cur.execute("SELECT * FROM person WHERE username = %s OR email = %s FOR UPDATE", (data['username'], data['email']))
            if cur.fetchone():
                return jsonify(create_response(400, 'Username or email already exists'))

            # Insert into PERSON
            cur.execute(
                """
                INSERT INTO person 
                    (username, email, password, first_name, last_name, phone, endereco) 
                VALUES (%s, %s, %s, %s, %s, %s, %s) 
                RETURNING user_id
                """,
                (data['username'], data['email'], data['password'], data['first_name'], 
                data['last_name'], data['phone'], data['endereco'])
            )
            person_user_id = cur.fetchone()[0]

            # Insert into INSTRUCTOR
            cur.execute(
                """
                INSERT INTO instructor 
                    (person_user_id, role, type) 
                VALUES (%s, %s, %s)
                """,
                (person_user_id, data['role'], data['type'])
            )
            conn.commit()
            return jsonify(create_response(200, results=person_user_id))
        conn.rollback()
        return jsonify(create_response(500, 'An error occurred: ' + str(e)))
    finally:
        cur.close()
        conn.close()


@app.route('/igor/login', methods=['PUT'])
def login_user():
    data = request.json
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(
            "SELECT * FROM person WHERE username = %s AND password = %s",
            (data['username'], data['password'])
        )
        user = cur.fetchone()

        if not user:
            return jsonify(create_response(400, 'Invalid credentials'))

        user_id = user['user_id']
        user_type = None
        cur.execute("SELECT 1 FROM students WHERE person_user_id = %s", (user_id,))
        if cur.fetchone():
            user_type = 'student'
        else:
            cur.execute("SELECT 1 FROM staff WHERE employee_person_user_id = %s", (user_id,))
            if cur.fetchone():
                user_type = 'staff'
            else:
                cur.execute("SELECT 1 FROM instructor WHERE person_user_id = %s", (user_id,))
                if cur.fetchone():
                    user_type = 'instructor'

        if not user_type:
            return jsonify(create_response(400, 'User has no assigned role'))
        token = jwt.encode(
            {'username': data['username'], 'user_type': user_type, 'exp': datetime.datetime.utcnow() + datetime.timedelta(days=1)},
            app.config['SECRET_KEY'],
            algorithm="HS256"
        )
        return jsonify(create_response(200, results=token))

    except Exception as e:
        return jsonify(create_response(500, str(e)))
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(" ")[1]
        if not token:
            return jsonify(create_response(400, 'Token ausente')), 400
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = data['username']
            user_type = data['user_type']
        except jwt.ExpiredSignatureError:
            return jsonify(create_response(400, 'Token expirado')), 400
        except jwt.InvalidTokenError:
            return jsonify(create_response(400, 'Token inválido')), 400
        return f(current_user, user_type, *args, **kwargs)
    return decorated

@app.route('/igor/enrollment_degree/<degree_id>', methods=['POST'])
@token_required
def enroll_degree(current_user,user_type,degree_id):
    conn = get_db_connection()
    cur = conn.cursor()
    data = request.json
    try:
        conn.autocommit = False
        student_id = data.get('student_id')
        date = data.get('enrollment_date')

        cur.execute("SELECT 1 FROM students WHERE person_user_id = %s", (student_id,))
        if not cur.fetchone():
            return jsonify(create_response(400, 'Student not found'))
        
        cur.execute("""
            INSERT INTO students_degree_program (students_person_user_id, degree_program_degree_id)
            VALUES (%s, %s)
        """, (student_id, degree_id))

        cur.execute("""
            UPDATE students SET enrollment_date = %s WHERE person_user_id = %s
        """, (date,student_id))
        
        conn.commit()
        return jsonify(create_response(200, results='Matrícula realizada com sucesso'))
    
    except Exception as e:
        conn.rollback()
        return jsonify(create_response(500, str(e)))
    finally:
        cur.close()
        conn.close()
        

if __name__ == '__main__':
    host = '127.0.0.1'
    app.run(host=host, debug=True, threaded=True, port=8080)