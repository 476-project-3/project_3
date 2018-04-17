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
from operator import attrgetter
from collections import namedtuple



# configuration
cluster = Cluster()
DATABASE = 'minitwit.db'
PER_PAGE = 30
DEBUG = True
SECRET_KEY = b'_5#y2L"F4Q8z\n\xec]/'

# create our little application :)
app = Flask('minitwit')
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
    init_db_cass()
    print('Initialized cass.')

def user_inserts(db):
    db.execute('''INSERT INTO users (username, email, followers, followees)
     VALUES ('Daniel', 'foo@bar.com', {'Kaz', 'Antonio'}, {'Kaz'})''')
    db.execute('''INSERT INTO users (username, email, followers, followees)
     VALUES ('Sollis', 'bar@foo.com', {}, {'Antonio'})''')
    db.execute('''INSERT INTO users (username, email, followers, followees)
     VALUES ('Kaz', 'foo@foo.com', {'Daniel'}, {'Sollis'})''')
    db.execute('''INSERT INTO users (username, email, followers, followees)
     VALUES ('Antonio', 'bar@bar.com', {'Kaz', 'Daniel', 'Sollis'}, {'Kaz'})''')

    #insert login information into 'login' table
    thing = generate_password_hash('foobar')
    db.execute('INSERT INTO login (username, pw_hash) VALUES (\'Daniel\', \'' + thing + '\')')
    thing = generate_password_hash('barfoo')
    db.execute('INSERT INTO login (username, pw_hash) VALUES (\'Sollis\', \'' + thing + '\')')
    thing = generate_password_hash('kaz')
    db.execute('INSERT INTO login (username, pw_hash) VALUES (\'Kaz\', \'' + thing + '\')')
    thing = generate_password_hash('barbar')
    db.execute('INSERT INTO login (username, pw_hash) VALUES (\'Antonio\', \'' + thing + '\')')


    # db.execute('''INSERT INTO user (username, email, pw_hash)
    # VALUES ("Sollis", "bar@foo.com", ?)''', [generate_password_hash('barfoo')])
    # db.execute('''INSERT INTO user (username, email, pw_hash)
    # VALUES ("Kaz", "foo@foo.com", ?)''', [generate_password_hash('foofoo')])
    # db.execute('''INSERT INTO user (username, email, pw_hash)
    # VALUES ("Antonio", "bar@bar.com", ?)''', [generate_password_hash('barbar')])

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

class MtAuth(BasicAuth):
    def check_credentials(self, username, password):
        session = cluster.connect()
        rows = session.execute('''SELECT pw_hash FROM twits.login WHERE username=\'''' + username + '''\'''')
        if rows != None:
            for x in rows:
                if check_password_hash(x.pw_hash, password):
                    return True
        return False

basic_auth = MtAuth(app)

#===============================================================================
#testing API endpoints
@app.route('/api/guser/<username>', methods = ['GET'])
def get_g_user(username):
    session = cluster.connect()
    rows = session.execute('select * from twits.users where username =\'' + username + '\'')
    for row in rows:
        username = row.username
        email = row.email
    rows = session.execute('select * from twits.login where username =\'' + username + '\'')
    for row in rows:
        pass_hash = row.pw_hash
    return jsonify({ 'username' : username, 'email' : email, 'pass_hash' : pass_hash})

#Working with CASS
"""
API Route for getting all users
Just send a GET request to /api/users to get all users back in a json.
"""
@app.route('/api/users', methods = ['GET'])
def get_users():
    session = cluster.connect()
    rows = session.execute('''select * from twits.users''')
    users = { 'users' : []}
    for row in rows:
        new_dictionary = { 'username' : row.username, 'email' : row.email}
        users['users'].append(new_dictionary)
    return jsonify(users)

#WORKING WITH CASS
"""
API Route for Public Timeline
Just send a GET requuest to /api/public to get all of the public timeline back in a json.
"""
@app.route('/api/public', methods = ['GET'])
def get_public():
    session = cluster.connect()
    rows = session.execute('SELECT * FROM twits.messages')
    messages = {'public timeline' : []}
    list_of_messages = []
    for row in rows:
        list_of_messages.append(row)
    sorted_messages = sorted(list_of_messages, reverse=True, key=attrgetter('pub_date'))
    for message in sorted_messages:
        new_dictionary= {'text' : message.message_text, 'pub_date' : message.pub_date, 'username' : message.author_username, 'email' : message.email}
        messages['public timeline'].append(new_dictionary)
    return jsonify(messages)

#WORKING WITH CASS
"""
API Route for getting users timeline (All messages made by user)
Send a GET request to "/api/users/<username>/timeline" (replacing <username> with desired username)
to get back all of that users posts in a json.
"""
@app.route('/api/users/<username>/timeline', methods = ['GET'])
def users_timeline(username):
    session = cluster.connect()
    rows = session.execute('SELECT * FROM twits.messages WHERE author_username=\'' + username + '\'')
    timeline = username + "\'s timeline"
    messages = { timeline : []}
    list_of_messages = []
    for row in rows:
        list_of_messages.append(row)
    sorted_messages = sorted(list_of_messages, key=attrgetter('pub_date'))
    for message in sorted_messages:
        new_dictionary= {'text' : message.message_text, 'pub_date' : message.pub_date, 'username' : message.author_username, 'email' : message.email}
        messages[timeline].append(new_dictionary)
    return jsonify(messages)

#WORKING
"""
API Route for registering new user
This route only takes POST requests.
A new user requires a new username, password, and email.
This route doesn't actually require authentication, but still uses those fields.
The username and password should be put into the authorization form of the request, using Basic Au@basic_auth.required
thentication.
The email of the user should be put into the request body under the key "email"
"""
@app.route('/api/register', methods = ['POST'])
def add_user():
    session = cluster.connect()
    rows = session.execute('''select username from twits.users where username=\'''' + str(request.authorization["username"]) + '''\'''')
    email = request.form.get("email")
    if rows:
        return jsonify({"message": "That username is already taken. Please try a different username."})
    elif email == None:
        return jsonify({"message": "There was no email for the user in the request body. Please add the user's email in the 'email' form in the request body"})
    else:
        hashed_pass = generate_password_hash(request.authorization["password"])
        session.execute('insert into twits.login (username, pw_hash) values (\'' + request.authorization["username"] + '\', \'' + hashed_pass + '\')')
        session.execute('insert into twits.users (username, email) values (\'' + request.authorization["username"] + '\', \'' + email + '\')')
        m = "Success, user has been added."
        return jsonify({"message" : m})

#WORKING WITH CASS
@app.route('/api/users/<username>', methods = ['GET'])
def get_user(username):
    session = cluster.connect()
    rows = session.execute('''select * from twits.users where username=\''''+ username + '\' ALLOW FILTERING')
    user = {'user' : []}
    if rows:
        for row in rows:
            new_dictionary= {'username' : row.username, 'email' : row.email}
            user['user'].append(new_dictionary)
    return jsonify(user)


"""
API Route for getting users who username is followed by
Send a GET request to "/api/users/<username>/followers" (replacing <username> with desired username)
to get back all of the users following that user in a json.
"""
@app.route('/api/users/<username>/followers', methods = ['GET'])
def get_followers(username):
    session = cluster.connect()
    rows = session.execute('select * from twits.users where username=\'' + username + '\'')
    if not rows:
        return jsonify({"status code" : "404"})
    for row in rows:
        followers = row.followers
    followers_dict = { "followers" : []}
    if not followers:
        return jsonify(followers_dict)
    for follower in followers:
        new_dict = { 'user' : follower }
        followers_dict['followers'].append(new_dict)
    return jsonify(followers_dict)


"""
API Route for getting users who username is following
Send a GET request to "/api/users/<username>/following" (replacing <username> with desired username)
to get back all of the users that user is following in a json."""
@app.route('/api/users/<username>/following', methods = ['GET'])
def get_following(username):
    session = cluster.connect()
    rows = session.execute('select * from twits.users where username=\'' + username + '\'')
    if not rows:
        return jsonify({"status code" : "404"})
    for row in rows:
        followees = row.followees
    followees_dict = { "following" : []}
    if not followees:
        return jsonify(followees_dict)
    for followee in followees:
        new_dict = { 'user' : followee }
        followees_dict['following'].append(new_dict)
    return jsonify(followees_dict)

#WORKING
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
        session = cluster.connect()
        rows = session.execute('SELECT email from twits.users WHERE username=\'' + username + '\'')
        for row in rows:
            email = row.email
        session.execute('insert into twits.messages (author_username, message_text, email, pub_date) values (\'' + username + '\', \'' + post_message +  '\', \'' + email + '\', '  + str(int(time.time())) + ')')
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
    if username != request.authorization["username"]:
        return jsonify({ 'error' : '401: Not Authorized'})
    session = cluster.connect()
    get_followees = session.execute('SELECT followees from twits.users where username=\'' + username + '\'')
    for x in get_followees:
        get_followees = x;
    if get_followees[0]:
        followees = []
        for followee in get_followees:
            for x in followee:
             followees.append(x)
        dash = {"dashboard" : []}
        followee_messages = []
        for users in followees:
            rows = session.execute('SELECT * FROM twits.messages WHERE author_username=\'' + users + '\'')
            for message in rows:
                followee_messages.append(message)
        rows = session.execute('SELECT * FROM twits.messages WHERE author_username=\'' + username + '\'')
        for message in rows:
            followee_messages.append(message)
        followee_messages = sorted(followee_messages, reverse=True, key=attrgetter('pub_date'))
        for message in followee_messages:
            json_message = {'text' : message.message_text, 'pub_date' : message.pub_date, 'username' : message.author_username, 'email' : message.email}
            dash["dashboard"].append(json_message)
        return jsonify(dash)
    else:
        followee_messages = []
        dash = {"dashboard" : []}
        rows = session.execute('SELECT * FROM twits.messages WHERE author_username=\'' + username + '\'')
        if rows:
            for message in rows:
                followee_messages.append(message)
        followee_messages = sorted(followee_messages, reverse=True, key=attrgetter('pub_date'))
        for message in followee_messages:
            json_message = {'text' : message.message_text, 'pub_date' : message.pub_date, 'username' : message.author_username, 'email' : message.email}
            dash["dashboard"].append(json_message)
        return jsonify(dash)

#WORKING
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
    session = cluster.connect()
    if request.authorization["username"] == follower:
        if(follower == followee):
            return jsonify({"Error" : "You can't follow yourself"})
        rows = session.execute('SELECT username from twits.users where username = \'' + follower + '\'')
        if(rows == None):
            return jsonify({"status code" : "404: User not found."})
        rows = session.execute('SELECT username from twits.users where username = \'' + followee + '\'')
        if(rows == None):
            return jsonify({"status code" : "404: User not found."})
        session.execute('UPDATE twits.users SET followees = followees + {\'' + followee + '\'} WHERE username = \'' + follower + '\'')
        session.execute('UPDATE twits.users SET followers = followers + {\'' + follower + '\'} WHERE username = \'' + followee + '\'')
        m = "Success, You are now following " + followee
        return jsonify({"message" : m})
    else:
        return jsonify({"status code" : "403 Forbidden: You're trying to make someone who isn't you follow someone else."})

@app.route('/api/users/<username>/check_hash', methods = ['GET'])
def get_pw_hash(username):
    session = cluster.connect()
    rows = session.execute('select * from twits.login where username=\'' + username + '\'')
    return_dict = { 'user' : []}
    if rows:
        for row in rows:
            new_dict = {'username' : row.username, 'pw_hash' : row.pw_hash}
            return_dict['user'].append(new_dict)
    return jsonify(return_dict)




#WORKING,
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
    session = cluster.connect()
    if request.authorization["username"] == follower:
        if(follower == followee):
            return jsonify({"Error" : "You can't unfollow yourself"})
        rows = session.execute('SELECT username from twits.users where username = \'' + follower + '\'')
        if not rows:
            return jsonify({"status code" : "404: User not found."})
        rows = session.execute('SELECT username from twits.users where username = \'' + followee + '\'')
        if not rows:
            return jsonify({"status code" : "404: User not found."})
        session.execute('UPDATE twits.users SET followees = followees - {\'' + followee + '\'} WHERE username = \'' + follower + '\'')
        session.execute('UPDATE twits.users SET followers = followers - {\'' + follower + '\'} WHERE username = \'' + followee + '\'')
        m = "Success, you unfollowed " + followee
        return jsonify({"message" : m})
    else:
        return jsonify({"status code" : "403 Forbidden: You're trying to make someone who isn't you unfollow someone else."})
