import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    # Get user id
    uId = session.get("user_id")

    # Query portfolio data (stock symbols and shares)
    portfolio_data = db.execute("SELECT stock_symbol, shares FROM portfolio WHERE user_id = ?", uId)

    # Query user's cash balance
    user_data = db.execute("SELECT cash FROM users WHERE id = ?", uId)
    cash = user_data[0]["cash"]

    # Initialize an empty list to store stock information
    stocks = []
    total_stock_value = 0

    # Loop through the user's portfolio and fetch current prices
    for stock in portfolio_data:
        symbol = stock["stock_symbol"]
        shares = stock["shares"]

        # Lookup current stock price (assuming lookup function is available)
        stock_info = lookup(symbol)
        price = stock_info["price"]
        total_value = shares * price

        # Add this stock's information to the stocks list (dictionary)
        stocks.append({
            "symbol": symbol,
            "shares": shares,
            "price": price,
            "total": total_value
        })

        # Update total stock value
        total_stock_value += total_value

    # Calculate grand total (cash + total stock value)
    grand_total = total_stock_value + cash

    # Render the template and pass in the stocks and totals
    return render_template("index.html", stocks=stocks, cash=cash, grand_total=grand_total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    u_id = session.get("user_id")

    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        # Ensure symbol was submitted
        if not symbol:
            return apology("must provide stock symbol", 400)

        # Lookup the stock
        stock = lookup(symbol)
        if stock is None:
            return apology("invalid stock symbol", 400)

        # Check if the stock already exists in the stocks table
        stock_data = db.execute("SELECT symbol FROM stocks WHERE symbol = ?", stock["symbol"])
        if not stock_data:
            db.execute("INSERT INTO stocks (symbol, name) VALUES (?, ?)",
                       stock["symbol"], stock["name"])

        # Ensure shares is valid
        try:
            shares = int(shares)
            if shares < 1:
                return apology("must provide positive number of shares", 400)
        except ValueError:
            return apology("shares must be an integer", 400)

        # Calculate the total cost
        price_per_share = stock["price"]
        ticker = stock["symbol"]
        total_cost = shares * price_per_share  # Total cost of the shares

        # Get the user's available cash
        user_data = db.execute("SELECT cash FROM users WHERE id = ?", u_id)

        # Check if user_data is not empty
        if not user_data:
            return apology("User data not found", 500)

        available = user_data[0]["cash"]

        # Check if user can afford the purchase
        if total_cost > available:
            return apology("cannot afford the number of shares", 400)

        # Update user's cash
        remaining = round(available - total_cost, 2)
        db.execute("UPDATE users SET cash = ? WHERE id = ?", remaining, u_id)

        # Record the transaction: store price as total cost and total as shares bought
        db.execute("INSERT INTO transactions (user_id, stock, price, total, share_price, type) VALUES (?, ?, ?, ?, ?, 'buy')",
                   u_id, ticker, total_cost, shares, price_per_share)

        # Updating the portfolio
        portfolio_data = db.execute(
            "SELECT shares FROM portfolio WHERE stock_symbol = ? AND user_id = ?", ticker, u_id)

        if portfolio_data:
            # Update existing shares
            # Use [0] to access the first (and only) row
            updated_shares = shares + portfolio_data[0]["shares"]
            db.execute("UPDATE portfolio SET shares = ? WHERE stock_symbol = ? AND user_id = ?",
                       updated_shares, ticker, u_id)
        else:
            # Insert new stock if it doesn't exist in the portfolio
            db.execute(
                "INSERT INTO portfolio (user_id, stock_symbol, shares) VALUES (?, ?, ?)", u_id, ticker, shares)

        # Redirect to the homepage
        return redirect("/")

    else:
        return render_template("buy.html", u_id=u_id)


@app.route("/history")
@login_required
def history():
    # Get the user's ID from the session
    user_id = session.get("user_id")

    # Query the transactions table for the user's history
    transaction_data = db.execute(
        "SELECT stock, share_price, price, total, timestamp, type FROM transactions WHERE user_id = ? ORDER BY timestamp DESC", user_id)

    # Create a list to store stock transactions
    stocks = []

    # Loop through the query results
    for stock in transaction_data:
        symbol = stock["stock"]
        share_price = stock["share_price"]
        total_price = stock["price"]
        total_shares = stock["total"]  # Renamed to match what should be 'shares' column
        timestamp = stock["timestamp"]
        transaction_type = stock["type"]

        # Add each stock's transaction details to the list
        stocks.append({
            "symbol": symbol,
            "share_price": share_price,
            "price": total_price,
            "total": total_shares,  # Renamed to 'total_shares'
            "type": transaction_type,
            "timestamp": timestamp
        })

    # Render the history template and pass the transactions (stocks) to it
    return render_template("history.html", stocks=stocks)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 400)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        # Get the stock symbol from the form
        symbol = request.form.get("symbol")

        # Check if the symbol is empty
        if not symbol:
            return apology("Please enter a stock symbol", 400)

        # Look up the stock using the symbol
        stock = lookup(symbol)

        # Check if the stock symbol is valid
        if stock is None:
            return apology("Enter a valid stock symbol", 400)

        # If the stock is valid, extract details for rendering
        name = stock['name']      # Company name
        price = stock['price']    # Latest price

        # Render the quoted template with stock information
        return render_template("quoted.html", name=name, symbol=symbol, price=price)

    else:
        # If GET request, render the quote page
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        raw_password = request.form.get("password")
        confirmation_password = request.form.get("confirmation")

        # Checking for input validation
        if not username:
            return apology("You need to provide a Username", 400)
        elif not raw_password:
            return apology("Provide a Password", 400)
        elif not confirmation_password:
            return apology("Enter your password again", 400)
        elif confirmation_password != raw_password:
            return apology("Make sure both of your passwords match", 400)

        # Query database for existing username
        try:
            present_username = db.execute("SELECT username FROM users WHERE username = ?", username)
            if present_username:
                return apology("Please enter a unique username", 400)
        except ValueError:
            return apology("Database error occurred.", 500)

        # Create a hash for the password
        hash_pword = generate_password_hash(raw_password, "scrypt", 16)

        # Perform database action to insert user
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, hash_pword)

        # Get user_id after insertion
        user_id = db.execute("SELECT id FROM users WHERE username = ?", username)
        session["user_id"] = user_id[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # Render register page for GET requests
    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    user_id = session.get("user_id")

    # Get the distinct stock held by this user
    user_data = db.execute("SELECT stock_symbol, shares FROM portfolio WHERE user_id = ?", user_id)
    # Create a list of stock symbols held by the user
    symbols = [stock["stock_symbol"] for stock in user_data]

    if request.method == "POST":
        symbol = request.form.get("symbol")
        share = request.form.get("shares")

        # Check if user owns shares of the selected stock
        portfolio_data = db.execute(
            "SELECT shares FROM portfolio WHERE stock_symbol = ? AND user_id = ?", symbol, user_id)

        if not symbol:
            return apology("Kindly select a valid stock", 400)
        if not share.isdigit() or int(share) < 1:
            return apology("Must enter a positive integer for shares", 400)

        share = int(share)  # Convert to integer after checking
        if not portfolio_data or share > portfolio_data[0]["shares"]:
            return apology("You can't sell more shares than you own.", 400)

        # Calculate remaining shares
        remaining_share = portfolio_data[0]["shares"] - share

        # Lookup current stock price
        stock = lookup(symbol)
        if stock is None:
            return apology("Stock symbol is invalid", 400)

        # Calculate total price for the sold shares
        price = round(stock["price"] * share, 2)

        # Update user's cash and portfolio
        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", price, user_id)
        db.execute("UPDATE portfolio SET shares = ? WHERE user_id = ? AND stock_symbol = ?",
                   remaining_share, user_id, symbol)

        # delete the portfolio data if remaining share is 0
        if (remaining_share == 0):
            db.execute("DELETE from portfolio WHERE user_id = ? AND stock_symbol = ?", user_id, symbol)

        # Record the transaction: price is the total price for the share sold and share is the total number of shares sold
        db.execute("INSERT INTO transactions (user_id, stock, price, total, share_price, type) VALUES (?, ?, ?, ?, ?, 'sell')",
                   user_id, symbol, price, share, stock["price"])

        return redirect("/")
    else:
        return render_template("sell.html", symbols=symbols)
