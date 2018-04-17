I'm so, so sorry about whatever garbage we managed to code here
We found out minitwit.py still had some references to the database that snuck by us last time so we got rid of them.
mt_api now uses all that fancy cassandra stuff.
schema.cql sure is a thing
timeline.html template had to be changed because it had a reference to user_id which we totally got rid of in our design
other than that it works as far as I can tell
