# Product Importer

A Flask application for importing and managing products via CSV upload with asynchronous processing.

## Features

- CSV upload with real-time progress tracking
- Product CRUD operations with filtering
- Bulk delete functionality
- Webhook management and testing
- Asynchronous processing with Celery
- PostgreSQL database with SQLAlchemy ORM

## Tech Stack

- **Framework**: Flask
- **Database**: PostgreSQL + SQLAlchemy
- **Task Queue**: Celery + Redis
- **Frontend**: Vanilla HTML/CSS/JavaScript

## Local Setup

### Prerequisites
- Python 3.11+
- PostgreSQL
- Redis

### Installation

1. Clone the repository:
```bash
git clone <your-repo-url>
cd product-importer
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set environment variables:
```bash
export DATABASE_URL="postgresql://localhost/products_db"
export REDIS_URL="redis://localhost:6379/0"
```

5. Create database:
```bash
createdb products_db
```

6. Run the application:

Terminal 1 (Web server):
```bash
python app.py
```

Terminal 2 (Celery worker):
```bash
celery -A app.celery worker --loglevel=info
```

7. Open browser: `http://localhost:5000`

## Deployment (Heroku)

### Prerequisites
- Heroku CLI installed
- Git repository initialized

### Steps

1. Create Heroku app:
```bash
heroku create your-app-name
```

2. Add PostgreSQL addon:
```bash
heroku addons:create heroku-postgresql:essential-0
```

3. Add Redis addon:
```bash
heroku addons:create heroku-redis:mini
```

4. Deploy:
```bash
git add .
git commit -m "Initial commit"
git push heroku main
```

5. Scale worker:
```bash
heroku ps:scale worker=1
```

6. Open app:
```bash
heroku open
```

## Deployment (Render)

1. Create new Web Service on Render
2. Connect your GitHub repository
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `gunicorn app:app`
5. Add PostgreSQL database
6. Add Redis instance
7. Add environment variables:
   - `DATABASE_URL` (from PostgreSQL)
   - `REDIS_URL` (from Redis)
8. Create Background Worker service:
   - Build command: `pip install -r requirements.txt`
   - Start command: `celery -A app.celery worker --loglevel=info`

## CSV Format

The CSV file should have the following columns:
- `sku` (required, unique, case-insensitive)
- `name` (required)
- `description` (optional)
- `price` (optional, numeric)

Example:
```csv
sku,name,description,price
ABC123,Product 1,Description here,29.99
DEF456,Product 2,Another product,49.99
```

## API Endpoints

### Products
- `GET /api/products` - List products (with pagination & filters)
- `POST /api/products` - Create product
- `PUT /api/products/<id>` - Update product
- `DELETE /api/products/<id>` - Delete product
- `DELETE /api/products/bulk-delete` - Delete all products

### Upload
- `POST /api/upload` - Upload CSV file
- `GET /api/upload/<upload_id>/progress` - Check upload progress

### Webhooks
- `GET /api/webhooks` - List webhooks
- `POST /api/webhooks` - Create webhook
- `PUT /api/webhooks/<id>` - Update webhook
- `DELETE /api/webhooks/<id>` - Delete webhook
- `POST /api/webhooks/<id>/test` - Test webhook

## Architecture

The application uses:
- **Flask** for web server and API
- **Celery** for asynchronous CSV processing (handles 30s timeout)
- **Redis** as Celery broker and result backend
- **PostgreSQL** for persistent data storage
- **SQLAlchemy** for database ORM

CSV uploads are processed asynchronously in batches of 1000 records to handle large files efficiently while providing real-time progress updates.

## Notes

- SKUs are case-insensitive and must be unique
- Duplicate SKUs in uploads will overwrite existing products
- All products default to active status
- Webhooks are triggered on product import batches