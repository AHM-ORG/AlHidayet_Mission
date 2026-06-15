import sqlite3

def delete_kg():
    print("Connecting to database 'users.db'...")
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Get all tables
    tables = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    
    print("\nScanning tables for 'KG' class occurrences...")
    for t in tables:
        t_name = t['name']
        columns = c.execute(f"PRAGMA table_info({t_name})").fetchall()
        
        # Check text/varchar columns
        for col in columns:
            col_name = col['name']
            col_type = col['type'].upper()
            
            if 'TEXT' in col_type or 'VARCHAR' in col_type or col_type == '':
                # Query if any rows have value 'KG' (case-insensitive or exact)
                try:
                    rows = c.execute(f"SELECT COUNT(*) FROM {t_name} WHERE {col_name} = 'KG'").fetchone()
                    count = rows[0] if rows else 0
                    if count > 0:
                        print(f" [+] Found {count} row(s) with 'KG' in table '{t_name}', column '{col_name}'. Deleting...")
                        c.execute(f"DELETE FROM {t_name} WHERE {col_name} = 'KG'")
                        conn.commit()
                except sqlite3.OperationalError:
                    # Column might not exist or be queryable in this way
                    pass

    print("\nVerifying database is clean of 'KG' values...")
    kg_found = False
    for t in tables:
        t_name = t['name']
        columns = c.execute(f"PRAGMA table_info({t_name})").fetchall()
        for col in columns:
            col_name = col['name']
            try:
                rows = c.execute(f"SELECT COUNT(*) FROM {t_name} WHERE {col_name} = 'KG'").fetchone()
                if rows and rows[0] > 0:
                    kg_found = True
                    print(f" [!] Warning: 'KG' still exists in '{t_name}'.'{col_name}'!")
            except sqlite3.OperationalError:
                pass
                
    if not kg_found:
        print(" [+] Success! No occurrences of 'KG' remain in the database.")
    
    conn.close()

if __name__ == '__main__':
    delete_kg()
