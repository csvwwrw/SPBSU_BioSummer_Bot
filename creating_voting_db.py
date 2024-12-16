import sqlite3
from sqlite3 import Error

def create_connection(path):
    connection = None
    try:
        connection = sqlite3.connect(path)
        print("Connection to SQLite DB successful")
    except Error as e:
        print(f"The error '{e}' occurred")

    return connection

def execute_query(connection, query):
    cursor = connection.cursor()
    try:
        cursor.execute(query)
        connection.commit()
        print("Query executed successfully")
    except Error as e:
        print(f"The error '{e}' occurred")
        
connection = create_connection('voting.db')
    
create_users_table = """
CREATE TABLE IF NOT EXISTS voting_db (
  id INTEGER,
  PACK_1 INTEGER,
  PACK_2 INTEGER,
  PACK_3 INTEGER,
  PACK_4 INTEGER,
  PACK_5 INTEGER,
  PACK_6 INTEGER,
  PACK_7 INTEGER,
  PACK_8 INTEGER,
  PACK_9 INTEGER,
  PACK_10 INTEGER,
  PACK_11 INTEGER,
  PACK_12 INTEGER,
  PACK_13 INTEGER,
  PACK_14 INTEGER,
  PACK_15 INTEGER,
  PACK_16 INTEGER,
  PACK_17 INTEGER,
  PACK_18 INTEGER,
  PACK_19 INTEGER,
  PACK_20 INTEGER
);
"""

execute_query(connection, create_users_table)  