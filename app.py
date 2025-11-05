from flask import Flask, render_template, request, redirect, url_for, flash
import mysql.connector
from mysql.connector import Error
import os
import pandas as pd

app = Flask(__name__)
app.secret_key = 'your_secret_key'


# Connect to the MySQL database
def connect_db():
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="devika@2004",
            database="grocery_billing"
        )
        if conn.is_connected():
            return conn
    except Error as e:
        print(f"Database connection error: {e}")
        return None

# Function to create tables if they don't exist
def create_tables():
    conn = connect_db()
    if conn is None:
        return
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS groceries (
            id INT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            price DECIMAL(10, 2) NOT NULL
        );
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id INT PRIMARY KEY AUTO_INCREMENT,
            name VARCHAR(255) NOT NULL,
            phone VARCHAR(15)
        );
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bills (
            id INT PRIMARY KEY AUTO_INCREMENT,
            customer_id INT,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bill_items (
            id INT PRIMARY KEY AUTO_INCREMENT,
            bill_id INT,
            item_id INT,
            quantity INT NOT NULL,
            FOREIGN KEY (bill_id) REFERENCES bills(id),
            FOREIGN KEY (item_id) REFERENCES groceries(id)
        );
    ''')

    conn.commit()
    cursor.close()
    conn.close()

# Call create_tables to ensure tables exist at app startup
create_tables()

# Route to add a grocery item
@app.route('/add_grocery', methods=['GET', 'POST'])
def add_grocery():
    if request.method == 'POST':
        # Check if Excel file upload form was submitted
        if 'upload_excel' in request.form and 'excel_file' in request.files:
            excel_file = request.files['excel_file']
            if excel_file.filename.endswith('.xlsx'):
                try:
                    df = pd.read_excel(excel_file)
                    if not {'name', 'price'}.issubset(df.columns):
                        flash('Excel file must contain columns: name, price', 'error')
                        return redirect(url_for('add_grocery'))
                    conn = connect_db()
                    cursor = conn.cursor()
                    added = []
                    skipped = []
                    for _, row in df.iterrows():
                        name = str(row['name']).strip()
                        try:
                            price = float(row['price'])
                        except (ValueError, TypeError):
                            skipped.append(name)
                            continue
                        cursor.execute('SELECT id FROM groceries WHERE name = %s', (name,))
                        if cursor.fetchone():
                            skipped.append(name)
                            continue
                        cursor.execute('SELECT MAX(id) FROM groceries')
                        max_id = cursor.fetchone()[0]
                        next_id = 1 if max_id is None else max_id + 1
                        cursor.execute('INSERT INTO groceries (id, name, price) VALUES (%s, %s, %s)', (next_id, name, price))
                        added.append(name)
                    conn.commit()
                    cursor.close()
                    conn.close()
                    if added:
                        flash('Excel upload successful!', 'success')
                    if not added and skipped:
                        flash('No new items were added. All items already exist or are invalid.', 'error')
                    return redirect(url_for('add_grocery'))
                except Exception as e:
                    flash(f'Error processing Excel file: {e}', 'error')
                    return redirect(url_for('add_grocery'))
            else:
                flash('Please upload a valid .xlsx file.', 'error')
                return redirect(url_for('add_grocery'))
        # Default: single item add
        name = request.form.get('name')
        price = request.form.get('price')
        if name and price:
            try:
                price = float(price)
                conn = connect_db()
                cursor = conn.cursor()
                cursor.execute("SELECT MAX(id) FROM groceries")
                max_id = cursor.fetchone()[0]
                next_id = 1 if max_id is None else max_id + 1
                cursor.execute('INSERT INTO groceries (id, name, price) VALUES (%s, %s, %s)', (next_id, name, price))
                conn.commit()
                cursor.close()
                conn.close()
                flash(f'Added {name} to groceries.', 'success')
                return redirect(url_for('add_grocery'))
            except ValueError:
                flash('Invalid price format. Please enter a valid number.', 'error')
    return render_template('add_grocery.html')

# Route to display the customer billing page
@app.route('/customer_billing', methods=['GET', 'POST'])
def customer_billing():
    if request.method == 'POST':
        customer_name = request.form['customer_name']
        customer_phone = request.form.get('customer_phone')
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO customers (name, phone) VALUES (%s, %s)', (customer_name, customer_phone))
        conn.commit()
        customer_id = cursor.lastrowid
        cursor.execute('INSERT INTO bills (customer_id) VALUES (%s)', (customer_id,))
        conn.commit()
        bill_id = cursor.lastrowid
        cursor.close()
        conn.close()
        return redirect(url_for('add_items_to_bill', bill_id=bill_id))
    return render_template('customer_billing.html')

# Route to add items to a bill
@app.route('/add_items_to_bill/<int:bill_id>', methods=['GET', 'POST'])
def add_items_to_bill(bill_id):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, price FROM groceries')
    groceries = cursor.fetchall()
    cursor.close()
    conn.close()

    if request.method == 'POST':
        item_ids = request.form.getlist('item_id')
        quantities = request.form.getlist('quantity')
        
        conn = connect_db()
        cursor = conn.cursor()
        
        for item_id, quantity in zip(item_ids, quantities):
            try:
                quantity = int(quantity)
                if quantity > 0:  # Ensure valid quantity
                    cursor.execute('INSERT INTO bill_items (bill_id, item_id, quantity) VALUES (%s, %s, %s)', (bill_id, item_id, quantity))
            except ValueError:
                flash('Invalid quantity. Please enter a valid number.')
        
        conn.commit()
        cursor.close()
        conn.close()
        flash('Items added. You can continue adding more or finalize the bill.')
        
    return render_template('add_items_to_bill.html', groceries=groceries, bill_id=bill_id)

# Route to view the bill
@app.route('/view_bill/<int:bill_id>', methods=['GET'])
def view_bill(bill_id):
    conn = connect_db()
    cursor = conn.cursor()

    # Get bill items along with grocery details
    cursor.execute('''
        SELECT g.name, g.price, bi.quantity
        FROM bill_items bi
        JOIN groceries g ON bi.item_id = g.id
        WHERE bi.bill_id = %s
    ''', (bill_id,))
    items = cursor.fetchall()

    # Get bill creation time
    cursor.execute('SELECT date FROM bills WHERE id = %s', (bill_id,))
    bill_date = cursor.fetchone()[0]  # Fetch the date of bill generation

    # Calculate total cost
    total_cost = sum(price * quantity for _, price, quantity in items)

    cursor.close()
    conn.close()

    # Pass bill_date to the template
    return render_template('view_bill.html', items=items, total_cost=total_cost, bill_id=bill_id, bill_date=bill_date)

# Payment page route
@app.route('/payment/<int:bill_id>', methods=['GET'])
def payment_page(bill_id):
    conn = connect_db()
    cursor = conn.cursor()
    
    # Calculate the total cost of the bill
    cursor.execute("SELECT SUM(g.price * bi.quantity) FROM bill_items bi JOIN groceries g ON bi.item_id = g.id WHERE bi.bill_id = %s", (bill_id,))
    total_cost = cursor.fetchone()[0]
    
    cursor.close()
    conn.close()
    return render_template('payment.html', bill_id=bill_id, total_cost=total_cost)

# Thank you page for cash payment
@app.route('/thank_you_cash')
def thank_you_cash():
    return render_template('thank_you_cash.html')

# Thank you page for UPI payment
@app.route('/thank_you_upi')
def thank_you_upi():
    return render_template('thank_you_upi.html')

# Home route
@app.route('/')
def home():
    return render_template('index.html')

# Run the app
if __name__ == '__main__':
    app.run(debug=True)
