from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
from datetime import datetime
import threading
import time

app = Flask(__name__, static_url_path='/static')
app.secret_key = 'your_secret_key'

def init_db():
    conn = sqlite3.connect('cafe.db')
    c = conn.cursor()
    
    # Создание таблицы гостей
    c.execute('''CREATE TABLE IF NOT EXISTS guests
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  phone TEXT,
                  email TEXT,
                  visit_date DATETIME NOT NULL)''')
    
    # Создание таблицы официантов
    c.execute('''CREATE TABLE IF NOT EXISTS waiters
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  phone TEXT NOT NULL,
                  experience INTEGER,
                  hire_date DATE NOT NULL)''')
    
    # Создание таблицы категорий меню
    c.execute('''CREATE TABLE IF NOT EXISTS menu_categories
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL)''')
    
    # Создание таблицы блюд меню
    c.execute('''CREATE TABLE IF NOT EXISTS menu_items
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  description TEXT,
                  price REAL NOT NULL,
                  category_id INTEGER,
                  preparation_time INTEGER,
                  active BOOLEAN DEFAULT 1,
                  FOREIGN KEY (category_id) REFERENCES menu_categories (id))''')
    
    # Создание таблицы заказов
    c.execute('''CREATE TABLE IF NOT EXISTS orders
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  guest_id INTEGER,
                  waiter_id INTEGER,
                  table_number INTEGER NOT NULL,
                  status TEXT NOT NULL,
                  order_date DATETIME NOT NULL,
                  total_amount REAL NOT NULL,
                  FOREIGN KEY (guest_id) REFERENCES guests (id),
                  FOREIGN KEY (waiter_id) REFERENCES waiters (id))''')
    
    # Создание таблицы позиций заказа
    c.execute('''CREATE TABLE IF NOT EXISTS order_items
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  order_id INTEGER,
                  menu_item_id INTEGER,
                  quantity INTEGER NOT NULL,
                  price REAL NOT NULL,
                  status TEXT NOT NULL,
                  FOREIGN KEY (order_id) REFERENCES orders (id),
                  FOREIGN KEY (menu_item_id) REFERENCES menu_items (id))''')
    
    # Создание таблицы платежей
    c.execute('''CREATE TABLE IF NOT EXISTS payments
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  order_id INTEGER,
                  amount REAL NOT NULL,
                  payment_method TEXT NOT NULL,
                  payment_date DATETIME NOT NULL,
                  status TEXT NOT NULL,
                  FOREIGN KEY (order_id) REFERENCES orders (id))''')
    
    # Добавление тестовых данных
    if c.execute("SELECT COUNT(*) FROM menu_categories").fetchone()[0] == 0:
        categories = [
            ('Горячие блюда',),
            ('Салаты',),
            ('Супы',),
            ('Напитки',),
            ('Десерты',)
        ]
        c.executemany("INSERT INTO menu_categories (name) VALUES (?)", categories)
        
    if c.execute("SELECT COUNT(*) FROM waiters").fetchone()[0] == 0:
        waiters = [
            ('Иванов Иван', '+79001234567', 3, '2021-01-15'),
            ('Петрова Мария', '+79009876543', 2, '2022-03-20'),
            ('Сидоров Петр', '+79007894561', 1, '2023-06-10')
        ]
        c.executemany("INSERT INTO waiters (name, phone, experience, hire_date) VALUES (?, ?, ?, ?)", waiters)

    if c.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0] == 0:
        menu_items = [
            ('Стейк из говядины', 'Сочный стейк medium rare с овощами гриль', 890.00, 1, 25),
            ('Паста Карбонара', 'Классическая итальянская паста с беконом', 520.00, 1, 20),
            ('Цезарь с курицей', 'Салат с куриным филе и соусом Цезарь', 450.00, 2, 15),
            ('Борщ', 'Традиционный борщ со сметаной', 320.00, 3, 15),
            ('Капучино', 'Кофе с молочной пенкой', 180.00, 4, 5),
            ('Чизкейк', 'Классический Нью-Йорк чизкейк', 350.00, 5, 10)
        ]
        c.executemany("INSERT INTO menu_items (name, description, price, category_id, preparation_time) VALUES (?, ?, ?, ?, ?)", menu_items)
    
    conn.commit()
    conn.close()

def update_order_status():
    while True:
        try:
            conn = sqlite3.connect('cafe.db')
            c = conn.cursor()
            
            # Обновляем статусы заказов
            c.execute("""UPDATE orders 
                        SET status = 'готов' 
                        WHERE status = 'в обработке' 
                        AND julianday('now') - julianday(order_date) > 0.02""")  # ~30 минут
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error in update_order_status: {e}")
        
        time.sleep(60)  # Проверяем каждую минуту

# Запускаем фоновый поток для обновления статусов
background_thread = threading.Thread(target=update_order_status, daemon=True)
background_thread.start()

# Инициализация базы данных
init_db()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/menu')
def menu():
    conn = sqlite3.connect('cafe.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute("""
        SELECT 
            c.name as category_name,
            m.name as item_name,
            m.description,
            m.price,
            m.preparation_time
        FROM menu_categories c
        LEFT JOIN menu_items m ON c.id = m.category_id
        WHERE m.active = 1
        ORDER BY c.id, m.name
    """)
    
    menu_items = c.fetchall()
    
    menu_by_category = {}
    for item in menu_items:
        if item['category_name'] not in menu_by_category:
            menu_by_category[item['category_name']] = []
        menu_by_category[item['category_name']].append(item)
    
    conn.close()
    return render_template('menu.html', menu=menu_by_category)

@app.route('/order', methods=['GET', 'POST'])
def order():
    conn = sqlite3.connect('cafe.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    if request.method == 'POST':
        guest_name = request.form['guest_name']
        table_number = request.form['table_number']
        waiter_id = request.form['waiter']
        menu_items = request.form.getlist('menu_items')
        quantities = request.form.getlist('quantities')
        
        # Создаем запись гостя
        c.execute("INSERT INTO guests (name, visit_date) VALUES (?, ?)",
                 (guest_name, datetime.now()))
        guest_id = c.lastrowid
        
        # Создаем заказ
        total_amount = 0
        for item_id, quantity in zip(menu_items, quantities):
            if int(quantity) > 0:
                c.execute("SELECT price FROM menu_items WHERE id = ?", (item_id,))
                price = c.fetchone()[0]
                total_amount += price * int(quantity)
        
        c.execute("""INSERT INTO orders 
                     (guest_id, waiter_id, table_number, status, order_date, total_amount)
                     VALUES (?, ?, ?, ?, ?, ?)""",
                 (guest_id, waiter_id, table_number, 'в обработке', datetime.now(), total_amount))
        order_id = c.lastrowid
        
        # Добавляем позиции заказа
        for item_id, quantity in zip(menu_items, quantities):
            if int(quantity) > 0:
                c.execute("SELECT price FROM menu_items WHERE id = ?", (item_id,))
                price = c.fetchone()[0]
                c.execute("""INSERT INTO order_items 
                           (order_id, menu_item_id, quantity, price, status)
                           VALUES (?, ?, ?, ?, ?)""",
                         (order_id, item_id, quantity, price, 'в обработке'))
        
        conn.commit()
        flash('Заказ успешно создан!')
        return redirect(url_for('order'))
    
    # Получаем данные для формы
    c.execute("SELECT * FROM menu_items WHERE active = 1")
    menu_items = c.fetchall()
    
    c.execute("SELECT * FROM waiters")
    waiters = c.fetchall()
    
    # Получаем активные заказы
    c.execute("""
        SELECT o.*, g.name as guest_name, w.name as waiter_name
        FROM orders o
        JOIN guests g ON o.guest_id = g.id
        JOIN waiters w ON o.waiter_id = w.id
        WHERE o.status != 'завершен'
        ORDER BY o.order_date DESC
    """)
    active_orders = c.fetchall()
    
    conn.close()
    return render_template('order.html',
                         menu_items=menu_items,
                         waiters=waiters,
                         active_orders=active_orders)
@app.route('/models')
def models():
    return render_template('models.html')
@app.route('/update_order_status/<int:order_id>', methods=['POST'])
def update_order_status(order_id):
    conn = sqlite3.connect('cafe.db')
    c = conn.cursor()
    
    new_status = request.form['status']
    
    c.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, order_id))
    conn.commit()
    conn.close()
    
    flash(f'Статус заказа успешно обновлен на "{new_status}"')
    return redirect(url_for('order'))

@app.route('/cancel_order/<int:order_id>', methods=['POST'])
def cancel_order(order_id):
    conn = sqlite3.connect('cafe.db')
    c = conn.cursor()
    
    c.execute("UPDATE orders SET status = 'отменен' WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()
    
    flash('Заказ отменен')
    return redirect(url_for('order'))
@app.route('/payment/<int:order_id>', methods=['POST'])
def payment(order_id):
    conn = sqlite3.connect('cafe.db')
    c = conn.cursor()
    
    payment_method = request.form['payment_method']
    
    # Получаем сумму заказа
    c.execute("SELECT total_amount FROM orders WHERE id = ?", (order_id,))
    amount = c.fetchone()[0]
    
    # Создаем платеж
    c.execute("""INSERT INTO payments 
                 (order_id, amount, payment_method, payment_date, status)
                 VALUES (?, ?, ?, ?, ?)""",
             (order_id, amount, payment_method, datetime.now(), 'оплачен'))
    
    # Обновляем статус заказа
    c.execute("UPDATE orders SET status = 'завершен' WHERE id = ?", (order_id,))
    
    conn.commit()
    conn.close()
    
    flash('Оплата прошла успешно!')
    return redirect(url_for('order'))

if __name__ == '__main__':
    app.run(debug=True)