# 💰 Expense Tracker

A modern, full-stack expense tracking application built with Python (FastAPI) and Docker. Manage your personal finances, track budgets, and analyze spending habits with an intuitive dashboard.

## ✨ Features

- **Expense Management**: Easily add, edit, and delete daily expenses.
- **Budget Tracking**: Set monthly budgets and track your progress in real-time.
- **Interactive Dashboard**: Visual breakdown of your spending by category using dynamic charts.
- **Data Export/Import**: Seamlessly export your data to Excel or import existing records.
- **Recurring Expenses**: Automated handling of monthly recurring payments.
- **Responsive Design**: Mobile-friendly interface for tracking on the go.

## 🛠️ Technologies Used

### Backend
- **Python 3.12**: Core programming language.
- **FastAPI**: High-performance web framework for building APIs.
- **Uvicorn**: ASGI web server implementation.
- **SQLite**: Lightweight, file-based relational database.
- **SQLAlchemy**: ORM for database interactions.
- **APScheduler**: Advanced Python Scheduler for recurring tasks.
- **OpenPyXL**: Library to read/write Excel 2010 xlsx/xlsm files.

### Frontend
- **Jinja2**: Templating engine for Python.
- **HTML5 & CSS3**: Structure and styling.
- **JavaScript**: Interactive client-side logic.
- **Chart.js**: (Implied) Visualization library for the dashboard.

### DevOps & Tools
- **Docker**: Containerization for consistent environments.
- **Docker Compose**: Multi-container Docker application tool.

## 🚀 Installation & Usage

### Method 1: Docker (Recommended)

The easiest way to run the application is using Docker.

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/josefcohen96/expense_tracker.git
    cd expense_tracker
    ```

2.  **Run with Docker Compose:**
    ```bash
    docker-compose up --build
    ```

3.  **Access the application:**
    Open your browser and navigate to `http://localhost:8080`.

### Method 2: Manual Setup

If you prefer running it locally without Docker:

1.  **Prerequisites:** Ensure Python 3.12+ is installed.

2.  **Create a virtual environment:**
    ```bash
    python -m venv .venv
    # Windows
    .venv\Scripts\activate
    # macOS/Linux
    source .venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the application:**
    ```bash
    uvicorn app.backend.app.main:app --host 0.0.0.0 --port 8080 --reload
    ```

5.  **Access the application:**
    Open `http://localhost:8080` in your browser.

## 📂 Project Structure

```
expense_tracker/
├── app/
│   ├── backend/        # FastAPI application logic, database models, and API routes
│   └── frontend/       # Jinja2 templates and static assets (CSS, JS)
├── docker-compose.yml  # Container orchestration config
├── Dockerfile          # Docker image definition
└── requirements.txt    # Python dependencies
```

## 🛡️ License

This project is open-source and available for personal and educational use.
