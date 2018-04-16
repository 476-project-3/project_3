"""
Made by Kazander Antonio and Daniel Sollis
To use, in the folder containing mt_api.py, run the command
export FLASK_APP=./mt_api.py
Usage of each of the endpoints is explained in the comment above the endpoint.
"""

import time
import datetime
import json
from sqlite3 import dbapi2 as sqlite3
from hashlib import md5
from datetime import datetime
from flask import Flask, request, session, url_for, redirect, \
     render_template, abort, g, flash, _app_ctx_stack, jsonify
from werkzeug import check_password_hash, generate_password_hash
from flask_basicauth import BasicAuth
from cassandra.cluster import Cluster
from fileinput import input

class MtAuth(BasicAuth):
    def check_credentials(self, username, password):
        cursor = get_db().cursor()
        cursor.execute('''select pw_hash from user where username="''' + str(username) + '''"''')
        data = cursor.fetchone()
        if data != None:
            if check_password_hash(data[0], password):
                return True
        return False

# configuration
cluster = Cluster()
DATABASE = 'minitwit.db'
PER_PAGE = 30
DEBUG = True
SECRET_KEY = b'_5#y2L"F4Q8z\n\xec]/'

# create our little application :)
app = Flask('minitwit')
basic_auth = MtAuth(app)
app.config.from_object(__name__)
app.config.from_envvar('MINITWIT_SETTINGS', silent=True)


def get_db():
    """Opens a new database connection if there is none yet for the
    current application context.
    """
    top = _app_ctx_stack.top
    if not hasattr(top, 'sqlite_db'):
        top.sqlite_db = sqlite3.connect(app.config['DATABASE'])
        top.sqlite_db.row_factory = sqlite3.Row
    return top.sqlite_db


@app.teardown_appcontext
def close_database(exception):
    """Closes the database again at the end of the request."""
    top = _app_ctx_stack.top
    if hasattr(top, 'sqlite_db'):
        top.sqlite_db.close()


def init_db():
    """Initializes the database."""
    db = get_db()
    with app.open_resource('schema.sql', mode='r') as f:
        db.cursor().executescript(f.read())
    db.commit()

def init_db_cass():
    """Initializes the database."""
    cass_session = cluster.connect()
    try:
        cass_session.execute('''CREATE KEYSPACE "twits" WITH replication = 
            {'class': 'SimpleStrategy', 'replication_factor' : 3};''')
    except:
        print "Keyspace Exists"
    cass_session.set_keyspace('twits')
    user_inserts(cass_session)

@app.cli.command('initdb')
def initdb_command():
    """Creates the database tables."""
    init_db()
    print('Initialized the database.')

@app.cli.command('initcass')
def initdb_command():
    """Creates the database tables."""
    init_db_cass()
    print('Initialized cass.')

def pop_db():
    """Populates the database"""
    db = get_db()
    user_inserts(db)
    with app.open_resource('population.sql', mode='r') as otherf:
        db.executescript(otherf.read())
        db.commit()

def user_inserts(db):
    db.execute('''INSERT INTO user (username, email, pw_hash)
    VALUES ("Daniel", "foo@bar.com", ?)''', [generate_password_hash('foobar')])
    # db.execute('''INSERT INTO user (username, email, pw_hash)
    # VALUES ("Sollis", "bar@foo.com", ?)''', [generate_password_hash('barfoo')])
    # db.execute('''INSERT INTO user (username, email, pw_hash)
    # VALUES ("Kaz", "foo@foo.com", ?)''', [generate_password_hash('foofoo')])
    # db.execute('''INSERT INTO user (username, email, pw_hash)
    # VALUES ("Antonio", "bar@bar.com", ?)''', [generate_password_hash('barbar')])

@app.cli.command('popdb')
def popdb_command():
    """adds predefined users to database"""
    pop_db()
    print('Populating the Database.')

@app.cli.command('restartdb')
def restartdb_command():
    initdb()
    popdb()
    print('Remaking the Database.')

def query_db(query, args=(), one=False):
    """Queries the database and returns a list of dictionaries."""
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    return (rv[0] if rv else None) if one else rv

def query_db_json(query, desc, args=(), one=False):
    """Queries the database and returns a json"""
    cursor = get_db().cursor()
    cursor.execute(query, args)
    r = [dict((cursor.description[i][0], value)
              for i, value in enumerate(row)) for row in cursor.fetchall()]
    return jsonify({desc : r})


def get_user_id(username):
    """Convenience method to look up the id for a username."""
    rv = query_db('select user_id from user where username = ?',
                  [username], one=True)
    return rv[0] if rv else None

def get_username(user_id):
    """Convenience method to look up the id for a username."""
    rv = query_db('select username from user where user_id = ?',
                  [user_id], one=True)
    return rv[0] if rv else None

def get_g_user():
    row = query_db('select * from user where user_id = ?', [session['user_id']], one=True)
    user = type('User', (object,), {})()
    user.user_id = row[0]
    user.username = row[1]
    user.email = row[2]
    user.pass_hash = row[3]
    return user

#===============================================================================
#testing API endpoints
"""
API Route for getting all users
Just send a GET request to /api/users to get all users back in a json.
"""
@app.route('/api/users', methods = ['GET'])
def get_users():
    cursor = get_db().cursor()
    users = cursor.execute('''select * from user;''')
    r = [dict((cursor.description[i][0], value)
              for i, value in enumerate(row)) for row in cursor.fetchall()]
    return jsonify({'users' : r})

"""
API Route for Public Timeline
Just send a GET requuest to /api/public to get all of the public timeline back in a json.
"""
@app.route('/api/public', methods = ['GET'])
def get_public():
    messages=query_db_json('''
        select message.*, user.username, user.email from message, user
        where message.author_id = user.user_id
        order by message.pub_date desc limit ?''', 'public timeline', [PER_PAGE])
    return messages

"""
API Route for getting users timeline (All messages made by user)
Send a GET request to "/api/users/<username>/timeline" (replacing <username> with desired username)
to get back all of that users posts in a json.
"""
@app.route('/api/users/<username>/timeline', methods = ['GET'])
def users_timeline(username):
    if request.method != 'GET':
        return jsonify({'status code' : '405'})
    cursor = get_db().cursor()
    cursor.execute('''select user_id from user where username="''' + str(username) + '''"''')
    user_id = cursor.fetchone()
    if user_id == None:
        return jsonify({'status code' : '404'})
    cursor.execute('''select * from message, user where author_id="''' +
                   str(user_id[0]) + '''" and user_id = "''' +
                   str(user_id[0]) + '''"''')
    r = [dict((cursor.description[i][0], value)
              for i, value in enumerate(row)) for row in cursor.fetchall()]
    return jsonify({str(username) + '\'s timeline' : r})

"""
API Route for registering new user
This route only takes POST requests.
A new user requires a new username, password, and email.
This route doesn't actually require authentication, but still uses those fields.
The username and password should be put into the authorization form of the request, using Basic Authentication.
The email of the user should be put into the request body under the key "email"
"""
@app.route('/api/register', methods = ['POST'])
def add_user():
    cursor = get_db().cursor()
    cursor.execute('''select user_id from user where username="''' + str(request.authorization["username"]) + '''"''')
    user_id = cursor.fetchone()
    email = request.form.get("email")
    if user_id != None:
        return jsonify({"message": "That username is already taken. Please try a different username."})
    elif email == None:
        return jsonify({"message": "There was no email for the user in the request body. Please add the user's email in the 'email' form in the request body"})
    else:
        db = get_db()
        db.execute('insert into user (username, email, pw_hash) values (?, ?, ?)',
            [request.authorization["username"], email, generate_password_hash(request.authorization["password"])])
        db.commit()
        m = "Success, user has been added."
        return jsonify({"message" : m})

@app.route('/api/users/<username>', methods = ['GET'])
def get_user(username):
    return query_db_json('''select * from user where username= ?''', 'user', [username])

"""
API Route for getting users who username is followed by
Send a GET request to "/api/users/<username>/followers" (replacing <username> with desired username)
to get back all of the users following that user in a json.
"""
@app.route('/api/users/<username>/followers', methods = ['GET'])
def get_followers(username):
    cursor = get_db().cursor()
    user_id = get_user_id(username)
    if user_id is None:
        return jsonify({"status code" : "404"})
    cursor.execute('''select who_id from follower where whom_id="''' + str(user_id) + '''"''')
    follower_ids = [dict((cursor.description[i][0], value)
              for i, value in enumerate(row)) for row in cursor.fetchall()]
    follower_names = []
    for i in range(len(follower_ids)):
        name = get_username(int(follower_ids[i].values()[0]))
        follower_names.append(name)
    return_dict = {}
    for i in range(0, len(follower_names)):
        return_dict[str(i + 1)] = follower_names[i]
    return jsonify({"followers" : return_dict})

"""
API Route for getting users who username is following
Send a GET request to "/api/users/<username>/following" (replacing <username> with desired username)
to get back all of the users that user is following in a json."""
@app.route('/api/users/<username>/following', methods = ['GET'])
def get_following(username):
    cursor = get_db().cursor()
    user_id = get_user_id(username)
    if user_id is None:
        return jsonify({"status code" : "404"})
    cursor.execute('''select whom_id from follower where who_id="''' + str(user_id) + '''"''')
    follower_ids = [dict((cursor.description[i][0], value)
              for i, value in enumerate(row)) for row in cursor.fetchall()]
    follower_names = []
    for i in range(len(follower_ids)):
        name = get_username(int(follower_ids[i].values()[0]))
        follower_names.append(name)
    return_dict = {}
    for i in range(0, len(follower_names)):
        return_dict[str(i + 1)] = follower_names[i]
    return jsonify({"following" : return_dict})

"""
API Route for posting
This route requires authentication, the fields must be filled out accordingly in the request.
In the request body, put the desired text of the post under the "message" form.
"""
@app.route('/api/users/<username>/post', methods = ['POST'])
@basic_auth.required
def insert_message(username):
    post_message = request.form.get("message")
    if post_message == None:
        return jsonify({"Error" : "There was no message in the request body."
                                  " Please add what you would like to post under"
                                  " the 'message' form in the request body"})
    if request.authorization["username"] == username:
        db = get_db()
        db.execute('insert into message (author_id, text, pub_date) values (?, ?, ?)',
            [get_user_id(username), post_message, time.time()])
        db.commit()
        m = "Success, you've made a post."
        return jsonify({"message" : m})
    else:
        return jsonify({"status code" : "403 Forbidden: You cannot post to a user that isn't you"})

"""
API route for getting a users Dashboard (Timeline of followed users)
This route requires authentication, the fields must be filled out accordingly in the request.
Sending a GET request returns the dashboard for that user, which is all the messages of all the users that the authenticated user follows.
"""
@app.route('/api/users/<username>/dashboard', methods = ['GET'])
@basic_auth.required
def get_dash(username):
    if request.authorization["username"] == username:
        messages = query_db_json('''
            select message.*, user.* from message, user
            where message.author_id = user.user_id and (
                user.user_id = ? or
                user.user_id in (select whom_id from follower
                                    where who_id = ?))
                order by message.pub_date desc limit ?''', 'dashboard',
                [get_user_id(username), get_user_id(username), PER_PAGE])
        return messages
    else:
        return jsonify({"status code" : "403 Forbidden: This dashboard doesn't belong to you"})

"""
Route for Api Follow
This route requires authentication, the fields must be filled out accordingly in the request.
Sending an authenticated POST request to this endpoint makes the follower user follow the followee user.
Ex.
/api/users/Daniel/follow/Kaz
With authenticated Daniel login would make the user Daniel follow the user Kaz
"""
@app.route('/api/users/<follower>/follow/<followee>', methods = ['POST'])
@basic_auth.required
def api_follow(follower, followee):
    if request.authorization["username"] == follower:
        if(get_user_id(follower) == get_user_id(followee)):
            return jsonify({"Error" : "You can't follow yourself"})
        followee_id = get_user_id(followee)
        follower_id = get_user_id(follower)
        if followee_id is None or follower_id is None:
            return jsonify({"status code" : "404: User not found."})
        db = get_db()
        db.execute('insert into follower (who_id, whom_id) values (?, ?)',
            [get_user_id(follower), get_user_id(followee)])
        db.commit()
        m = "Success, You are now following " + followee
        return jsonify({"message" : m})
    else:
        return jsonify({"status code" : "403 Forbidden: You're trying to make someone who isn't you follow someone else."})

"""
Route for Api Unfollow
This route requires authentication, the fields must be filled out accordingly in the request.
Sending an authenticated DELETE request to this endpoint makes the follower user unfollow the followee user.
Ex.
/api/users/Daniel/follow/Kaz
With authenticated Daniel login would make the user Daniel unfollow the user Kaz
"""
@app.route('/api/users/<follower>/unfollow/<followee>', methods = ['DELETE'])
@basic_auth.required
def api_unfollow(follower, followee):
    if request.authorization["username"] == follower:
        if(get_user_id(follower) == get_user_id(followee)):
            return jsonify({"Error" : "You can't unfollow yourself"})
        followee_id = get_user_id(followee)
        follower_id = get_user_id(follower)
        if followee_id is None or follower_id is None:
            return jsonify({"status code" : "404: User not found."})
        db = get_db()
        db.execute('delete from follower where who_id=? and whom_id=?',
                  [follower_id, followee_id])
        db.commit()
        m = "Success, you unfollowed " + followee
        return jsonify({"message" : m})
    else:
        return jsonify({"status code" : "403 Forbidden: You're trying to make someone who isn't you unfollow someone else."})
