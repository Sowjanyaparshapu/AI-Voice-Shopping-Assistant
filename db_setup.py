"""
db_setup.py
Creates the SQLite database for the Voice Shopping Assistant and seeds it
with sample products. Run this file once before starting the app:

    python db_setup.py
"""

import sqlite3

DB_PATH = "shopping.db"

# (name, price_per_unit, unit, category)
SAMPLE_PRODUCTS = [
    ("Basmati Rice", 120, "kg", "Grocery"),
    ("Sona Masoori Rice", 90, "kg", "Grocery"),
    ("Toor Dal", 140, "kg", "Grocery"),
    ("Moong Dal", 130, "kg", "Grocery"),
    ("Milk", 60, "litre", "Dairy"),
    ("Curd", 50, "kg", "Dairy"),
    ("Butter", 55, "packet", "Dairy"),
    ("Paneer", 80, "packet", "Dairy"),
    ("Tomato", 40, "kg", "Vegetables"),
    ("Onion", 35, "kg", "Vegetables"),
    ("Potato", 30, "kg", "Vegetables"),
    ("Sugar", 45, "kg", "Grocery"),
    ("Salt", 20, "kg", "Grocery"),
    ("Sunflower Oil", 150, "litre", "Grocery"),
    ("Wheat Flour", 55, "kg", "Grocery"),
    ("Bread", 40, "packet", "Bakery"),
    ("Eggs", 6, "piece", "Dairy"),
    ("Pasta", 65, "packet", "Grocery"),
    ("Pasta Sauce", 90, "packet", "Grocery"),
    ("Tea Powder", 180, "packet", "Beverages"),
    ("Coffee Powder", 220, "packet", "Beverages"),
    ("Biscuits", 30, "packet", "Snacks"),
]


def create_tables(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            price REAL NOT NULL,
            unit TEXT NOT NULL,
            category TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            quantity REAL NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            total REAL NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity REAL NOT NULL,
            price_at_purchase REAL NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders (id),
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    """)

    conn.commit()


def seed_products(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.executemany(
        "INSERT OR IGNORE INTO products (name, price, unit, category) VALUES (?, ?, ?, ?)",
        SAMPLE_PRODUCTS,
    )
    conn.commit()


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    create_tables(conn)
    seed_products(conn)
    count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    print(f"Database ready at {DB_PATH} with {count} products.")
    conn.close()


if __name__ == "__main__":
    main()
