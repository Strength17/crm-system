import sqlite3
import requests

# Configuration
BASE_URL = 'http://localhost:5000'  # Change this to your server address
API_ENDPOINT = f'{BASE_URL}/crm/add-business'

# Your JWT token
TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyIiwiZXhwIjoxNzY3MjQ5MDI2fQ.IVhacHyLW2Zly6TbqSJYUNeKvSd8pWo6RaN3oepFUdM'

def reset_autoincrement():
    conn = sqlite3.connect('mvp.db')
    cursor = conn.cursor()
    tables = ['prospects', 'interactions', 'deals', 'payments']
    for table in tables:
        cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{table}';")
        print(f"Reset autoincrement for {table}")
    conn.commit()
    conn.close()

# Sample data for 3 entries
sample_data = [
    {
        "name": f"Company {i+1} Alpha",
        "website": f"https://company{i+1}alpha.com",
        "email": f"contact{i+1}@company{i+1}alpha.com",
        "phone": f"100000000{i+1:02d}",
        "pain": "Need software solutions" if i % 3 == 0 else "Expand marketing" if i % 3 == 1 else "Operational automation",
        "pain_score": (i % 10) + 1,
        "status": "new" if i % 4 == 0 else "contacted" if i % 4 == 1 else "qualified" if i % 4 == 2 else "not_qualified"
    }
    for i in range(100)
]
def clear_tables():
    conn = sqlite3.connect('mvp.db')  # Change to your DB path
    cursor = conn.cursor()

    tables = ['payments', 'deals', 'interactions', 'prospects']
    for table in tables:
        cursor.execute(f'DELETE FROM {table}')
        print(f'Cleared table {table}')
    conn.commit()
    conn.close()

def populate():
    headers = {
        'Authorization': f'Bearer {TOKEN}',
        'Content-Type': 'application/json'
    }
    for data in sample_data:
        try:
            response = requests.post(API_ENDPOINT, json=data, headers=headers)
            if response.status_code == 201:
                print(f"Successfully added business: {data['name']}")
                print("Response:", response.json())
            else:
                print(f"Failed to add {data['name']}: {response.status_code}")
                print("Error:", response.json())
        except Exception as e:
            print(f"Error during request for {data['name']}: {e}")

if __name__ == "__main__":
    print("Clearing existing data from tables...")
    clear_tables()
    reset_autoincrement()
    print("Populating tables with sample data...")
    populate()