from requests_oauthlib import OAuth2
import json
import requests
import google_secrets
import reddit_secrets
import praw
from collections import defaultdict
import collections
import re
import pandas as pd
import sqlite3
import flask
from flask import Flask, render_template, request
from praw.models import MoreComments


GOOGLE_CACHE_FILENAME = "google_cache.json"
REDDIT_CACHE_FILENAME = "reddit_cache.json"


client_google_key = google_secrets.BOOKS_API_KEY
baseurl = 'https://www.googleapis.com/books/v1/volumes?'


reddit = praw.Reddit(client_id = reddit_secrets.CLIENT_ID,
                     client_secret = reddit_secrets.CLIENT_SECRET,
                     user_agent = reddit_secrets.USER_AGENT,
                     username = reddit_secrets.USERNAME,                
                     password = reddit_secrets.PASSOWRD)

def open_cache(filename):
    try:
        cache_file = open (filename, 'r+')
        cache_contents = cache_file.read()
        cache_dict = json.loads(cache_contents)
        cache_file.close()
    except:
        cache_dict = {}
    return cache_dict

def save_cache(cache_dict, filename):
    dumped_json_Cache = json.dumps(cache_dict)
    fw = open(filename, "w")
    fw.write(dumped_json_Cache)
    fw.close()

def construct_unique_key(baseurl, params):
    unique_key = baseurl + f'q={params["q"]}'
    return unique_key

def make_request(baseurl, params):
    response = requests.get(baseurl, params=params)
    return response.json()
    
def make_request_with_reddit(param):
    subreddit = reddit.subreddit(param)
    hot_books = subreddit.hot(limit = 10)
    res = {}
    for submission in hot_books:
        if not submission.stickied:
            res[submission.title] = {}
            res[submission.title]['id'] = submission.id
            res[submission.title]['ups'] = submission.ups
            res[submission.title]['num_comments'] = submission.num_comments
    return res

def make_request_with_cache(GOOGLE_CACHE_DICT, baseurl, params):
    request_key = construct_unique_key(baseurl, params)
    if request_key in GOOGLE_CACHE_DICT.keys():
        print("cache hit!", request_key)
        return GOOGLE_CACHE_DICT[request_key]
    else:
        print("cache miss!", request_key)
        GOOGLE_CACHE_DICT[request_key] = make_request(baseurl, params)
        save_cache(GOOGLE_CACHE_DICT, GOOGLE_CACHE_FILENAME)
        return GOOGLE_CACHE_DICT[request_key]

def make_request_with_reddit_cache(REDDIT_CACHE_DICT, param):
    if param in REDDIT_CACHE_DICT.keys():
        print('in cache', param)
        return REDDIT_CACHE_DICT[param]
    else:
        print('not in cache', param)
        REDDIT_CACHE_DICT[param] = make_request_with_reddit(param)
        save_cache(REDDIT_CACHE_DICT, REDDIT_CACHE_FILENAME)
        return REDDIT_CACHE_DICT[param]

def get_search_query():
    query = input("Search for a book or author:")
    query = query.replace(" ","")
    return query

# def print_book_title():
#     result = make_request_with_cache(GOOGLE_CACHE_DICT, baseurl, params)
#     book_info = result['items']
#     for title in book_info:
#         print(title['volumeInfo']['title'])

DB_NAME = 'reddit_google_books.sqlite'

def create_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    drop_books = 'DROP TABLE IF EXISTS "Books"'
    drop_authors = 'DROP TABLE IF EXISTS "Authors"'
    drop_redditposts = 'DROP TABLE IF EXISTS "RedditPosts"'

    create_books = '''
        CREATE TABLE IF NOT EXISTS "Books" (
            "ID"            INTEGER PRIMARY KEY AUTOINCREMENT,
            "BookTitle"	    TEXT NOT NULL,
            "BOOKID"	    INTEGER NOT NULL,
            "PublishedDate"	TEXT NOT NULL,
            "Rating"	    REAL NOT NULL,
            "Price"	        REAL
    ); 
    '''
    create_authors = '''
        CREATE TABLE IF NOT EXISTS "Authors" (
            "ID"            INTEGER PRIMARY KEY AUTOINCREMENT,
            "BookID"	    TEXT NOT NULL,
            "BookTitle"	    TEXT NOT NULL,
            "Name"	        TEXT NOT NULL,
            "Language"	    TEXT NOT NULL
    ); 
    '''

    create_redditposts = '''
        CREATE TABLE IF NOT EXISTS "RedditPosts" (
            "ID"	           INTEGER PRIMARY KEY AUTOINCREMENT,
            "SubredditsTitle"  TEXT NOT NULL,
            "Ups"	           INTEGER NOT NULL,
            "NumComments"	   INTEGER NOT NULL
    ); 
    '''

    # cur.execute(drop_books)
    # cur.execute(drop_authors)
    # cur.execute(drop_redditposts)
    cur.execute(create_books)
    cur.execute(create_authors)
    cur.execute(create_redditposts)
    conn.commit()
    conn.close()

def load_books(baseurl, params):
    bookresult = open_cache(GOOGLE_CACHE_FILENAME)

    insert_sql = '''
        INSERT INTO Books
        VALUES (NULL,?,?,?,?,?)
    '''
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    print(bookresult)
    book_info = bookresult[construct_unique_key(baseurl, params)]['items']
    for title in book_info:
        try: 
            pb = title['volumeInfo']['publishedDate']
        except:
            pb = "Not Known"
        try: 
            ar = title['volumeInfo']['averageRating']
        except: 
            ar = 'No Rating'
        try: 
            lp = title['saleInfo']['listPrice']['amount']
        except:
            lp = 'Not for Sale'
            cur.execute(insert_sql,
                [
                    title['volumeInfo']['title'],
                    title['id'],
                    pb,
                    ar,
                    lp
                ]
            )
    conn.commit()
    conn.close()

def load_authors(baseurl, params):
    bookresult = open_cache(GOOGLE_CACHE_FILENAME)
    
    insert_sql = '''
        INSERT INTO Authors
        VALUES (NULL, ?, ?, ?, ?)
    '''
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    book_info = bookresult[construct_unique_key(baseurl, params)]['items']

    for title in book_info:
        for author in title['volumeInfo']['authors']:
            cur.execute(insert_sql,
                [
                    title['id'],
                    title['volumeInfo']['title'],
                    author,
                    title['volumeInfo']['language']
                ]
            )
    conn.commit()
    conn.close()
        
def load_redditposts(param):
    result = open_cache(REDDIT_CACHE_FILENAME)[param]

    insert_sql = '''
        INSERT INTO RedditPosts
        VALUES (NULL, ?, ?, ?)
    '''
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    print(result)
    for title, posts in result.items():
        print(posts['ups'])
        cur.execute(insert_sql,
            [
                title,
                posts['ups'],
                posts['num_comments']
            ]
        )
    conn.commit()
    conn.close()   

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/subreddits', methods=['POST'])
def subreddits():
    param = request.form["search_term"]
    search_term = param
    load_redditposts(param)    
    REDDIT_CACHE_DICT = open_cache(REDDIT_CACHE_FILENAME)
    results = make_request_with_reddit_cache(REDDIT_CACHE_DICT, param)
    subreddits = []
    for key,value in results.items():
        ups = value['ups']
        comments = value['num_comments']
        title = key 
        post_id = value['id']
        post_info = [post_id,title,ups,comments]
        subreddits.append(post_info)
    return render_template('subreddits.html', 
        search_term=search_term,
        subreddits=subreddits) 

@app.route('/comments', methods=['POST'])
def comments():
    post_id = request.form["subreddits"]
    submission = reddit.submission(id=post_id)
    comment_list = []
    for comment in submission.comments:
        comments = comment.body
        comment_list.append(comments)

    return render_template('comments.html', 
        post_id = post_id,
        comment = comment_list)

def convert_string(s):
    if s is None:
        return ''
    else:
        return str(s)

def get_book_info(book_query):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    q = "SELECT BookTitle, PublishedDate, Rating, Price FROM Books WHERE BookTitle LIKE '%" + \
        convert_string(book_query) + "%' ORDER BY Rating DESC"
    results = cur.execute(q).fetchall()
    conn.close()

    return results

def get_num_rating(book_query):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    n = "SELECT BookTitle, COUNT(Rating) FROM Books WHERE NOT Rating = 'No Rating' AND BookTitle LIKE '%" + \
        convert_string(book_query) + "%'"
        
    num_rating = cur.execute(n).fetchall()
    conn.close()

    return num_rating 

def get_avg_rating(book_query):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    a = "SELECT BookTitle, AVG(Rating) FROM Books WHERE NOT Rating = 'No Rating' AND BookTitle LIKE '%" + \
        convert_string(book_query) + "%'"
        

    avg_rating = cur.execute(a).fetchall()
    conn.close()

    return avg_rating

@app.route('/books', methods=['POST'])
def books():
    book_query = request.form.get('bookname')
    results = get_book_info(book_query)
    num_rating = get_num_rating(book_query)[0][1]
    avg_rating = get_avg_rating(book_query)[0][1]

    return render_template('books.html', 
        book = book_query,
        results = results,
        num_rating = num_rating,
        avg_rating = avg_rating)

if __name__ == '__main__':   
    app.run(debug=True)




# REDDIT_CACHE_DICT = open_cache(REDDIT_CACHE_FILENAME)
# param = input('Search for a book recommendations: ')
# result = make_request_with_reddit_cache(REDDIT_CACHE_DICT, param)
# print(result)

# GOOGLE_CACHE_DICT = open_cache(GOOGLE_CACHE_FILENAME)
# baseurl = 'https://www.googleapis.com/books/v1/volumes?'
# query = get_search_query()
# params = {"q":query}
# result = make_request_with_cache(GOOGLE_CACHE_DICT, baseurl, params)

# create_db()
# load_books(baseurl, params)
# load_redditposts(param)
# load_authors(baseurl, params)



    







