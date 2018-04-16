CREATE TABLE IF NOT EXISTS twits.users(
        user_id uuid,
        username text,
        email text,
        followers set<int>,
        followees set<int>,
        PRIMARY KEY(user_id);

CREATE TABLE IF NOT EXISTS twits.messages(
        author_id uuid,
        message_id int,
        message_text text,
        pub_date int,
        PRIMARY KEY(author_id));

CREATE TABLE IF NOT EXISTS twits.login(
        username text PRIMARY KEY,
        pw_hash text);