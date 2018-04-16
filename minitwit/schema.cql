CREATE TABLE IF NOT EXISTS twits.users(
        username text,
        email text,
        followers set<text>,
        followees set<text>,
        PRIMARY KEY(username);

CREATE TABLE IF NOT EXISTS twits.messages(
        author_username text,
        message_text text,
        pub_date int,
        ;

CREATE TABLE IF NOT EXISTS twits.login(
        username text PRIMARY KEY,
        pw_hash text);
