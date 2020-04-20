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

GOOGLE_CACHE_FILENAME = "google_cache.json"
REDDIT_CACHE_FILENAME = "reddit_cache.json"


client_google_key = google_secrets.BOOKS_API_KEY

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
            res[submission.title]['ups'] = submission.ups
            res[submission.title]['num_comments'] = submission.num_comments
            # res[submission.title]['comments'] = submission.comments

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

REDDIT_CACHE_DICT = open_cache(REDDIT_CACHE_FILENAME)
param = input('Search for a book recommendations: ')
result = make_request_with_reddit_cache(REDDIT_CACHE_DICT, param)
print(result)

GOOGLE_CACHE_DICT = open_cache(GOOGLE_CACHE_FILENAME)
baseurl = 'https://www.googleapis.com/books/v1/volumes?'
query = get_search_query()
params = {"q":query}
result = make_request_with_cache(GOOGLE_CACHE_DICT, baseurl, params)
# print(print_book_title())

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
        if title['saleInfo']['saleability'] == "FOR_SALE" and 'averageRating' in title['volumeInfo'].keys():
            cur.execute(insert_sql,
                [
                    title['volumeInfo']['title'],
                    title['id'],
                    title['volumeInfo']['publishedDate'],
                    title['volumeInfo']['averageRating'],
                    title['saleInfo']['listPrice']['amount']
                ]
            )
        elif title['saleInfo']['saleability'] == "FOR_SALE" and 'averageRating' not in title['volumeInfo'].keys():
            cur.execute(insert_sql,
                [
                    title['volumeInfo']['title'],
                    title['id'],
                    title['volumeInfo']['publishedDate'],
                    'No Rating',
                    title['saleInfo']['listPrice']['amount']
                ]
            )
        elif title['saleInfo']['saleability'] == "NOT_FOR_SALE" and 'averageRating' in title['volumeInfo'].keys():
            cur.execute(insert_sql,
                [
                    title['volumeInfo']['title'],
                    title['id'],
                    title['volumeInfo']['publishedDate'],
                    title['volumeInfo']['averageRating'],
                    'Not for Sale'
                ]
            )
        elif title['saleInfo']['saleability'] == "NOT_FOR_SALE" and 'averageRating' not in title['volumeInfo'].keys():
            cur.execute(insert_sql,
                [
                    title['volumeInfo']['title'],
                    title['id'],
                    title['volumeInfo']['publishedDate'],
                    'No Rating',
                    'Not for Sale'
                ]
            )
    conn.commit()
    conn.close()

def load_authors(baseurl, params):
    bookresult = open_cache(GOOGLE_CACHE_FILENAME)
    
    insert_sql = '''
        INSERT INTO Authors
        VALUES (NULL, ?, ?, ?)
    '''
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    book_info = bookresult[construct_unique_key(baseurl, params)]['items']

    for title in book_info:
        for author in title['volumeInfo']['authors']:
            # print(title['id'])
            # print(author)
            # print(title['volumeInfo']['language'])
            cur.execute(insert_sql,
                [
                    title['id'],
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

create_db()
load_books(baseurl, params)
load_redditposts(param)
load_authors(baseurl, params)



#         # submission.comments.replace_more(limit=0)
#         comments = submission.comments.list()
#         for comment in comments:
#             print(20*'-')
#             print('Parent ID:', comment.parent())
#             print('Comment ID', comment.id)
#             print(comment.body)
#             # if len(comment.replieds) > 0:
#             #     for reply in comment.replies:
#             #         print('REPLY',reply.body)



    







