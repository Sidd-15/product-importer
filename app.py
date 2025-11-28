import os
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from celery import Celery
import csv
import io
from datetime import datetime


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///products.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['CELERY_BROKER_URL'] = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
app.config['CELERY_RESULT_BACKEND'] = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

db = SQLAlchemy(app)
# celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
# celery.conf.update(app.config)
celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'], backend=app.config['CELERY_RESULT_BACKEND'])

# Models
class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(100), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Numeric(10, 2))
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Webhook(db.Model):
    __tablename__ = 'webhooks'
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    event_type = db.Column(db.String(50), nullable=False)
    enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class UploadProgress(db.Model):
    __tablename__ = 'upload_progress'
    id = db.Column(db.String(100), primary_key=True)
    total_rows = db.Column(db.Integer, default=0)
    processed_rows = db.Column(db.Integer, default=0)
    status = db.Column(db.String(50), default='pending')
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Celery Tasks
@celery.task(bind=True)
def process_csv_upload(self, file_content, upload_id):
    with app.app_context():
        progress = None
        try:
            progress = UploadProgress.query.get(upload_id)
            progress.status = 'parsing'
            db.session.commit()
            
            csv_file = io.StringIO(file_content)
            reader = csv.DictReader(csv_file)
            rows = list(reader)
            
            progress.total_rows = len(rows)
            progress.status = 'processing'
            db.session.commit()
            
            batch_size = 1000
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i + batch_size]
                for row in batch:
                    sku = row.get('sku', '').strip().lower()
                    if not sku:
                        continue
                        
                    product = Product.query.filter(func.lower(Product.sku) == sku).first()
                    if product:
                        product.name = row.get('name', '')
                        product.description = row.get('description', '')
                        product.price = float(row.get('price', 0))
                        product.updated_at = datetime.utcnow()
                    else:
                        product = Product(
                            sku=sku,
                            name=row.get('name', ''),
                            description=row.get('description', ''),
                            price=float(row.get('price', 0)),
                            active=True
                        )
                        db.session.add(product)
                
                db.session.commit()
                progress.processed_rows = min(i + batch_size, len(rows))
                db.session.commit()
                
                trigger_webhooks.delay('product.imported', {'batch': i // batch_size})
            
            progress.status = 'completed'
            db.session.commit()
            
        except Exception as e:
            if progress:
                progress.status = 'failed'
                progress.error_message = str(e)
                db.session.commit()
            raise
@celery.task
def trigger_webhooks(event_type, data):
    with app.app_context():
        import requests
        webhooks = Webhook.query.filter_by(event_type=event_type, enabled=True).all()
        for webhook in webhooks:
            try:
                requests.post(webhook.url, json=data, timeout=5)
            except:
                pass

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/products', methods=['GET'])
def get_products():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    sku = request.args.get('sku', '')
    name = request.args.get('name', '')
    active = request.args.get('active', '')
    
    query = Product.query
    
    if sku:
        query = query.filter(Product.sku.ilike(f'%{sku}%'))
    if name:
        query = query.filter(Product.name.ilike(f'%{name}%'))
    if active:
        query = query.filter_by(active=(active.lower() == 'true'))
    
    pagination = query.order_by(Product.id.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'products': [{
            'id': p.id,
            'sku': p.sku,
            'name': p.name,
            'description': p.description,
            'price': float(p.price) if p.price else 0,
            'active': p.active
        } for p in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page
    })

@app.route('/api/products', methods=['POST'])
def create_product():
    data = request.json
    sku = data.get('sku', '').strip().lower()
    
    if Product.query.filter(func.lower(Product.sku) == sku).first():
        return jsonify({'error': 'SKU already exists'}), 400
    
    product = Product(
        sku=sku,
        name=data.get('name'),
        description=data.get('description'),
        price=data.get('price'),
        active=data.get('active', True)
    )
    db.session.add(product)
    db.session.commit()
    
    return jsonify({'id': product.id, 'message': 'Product created'}), 201

@app.route('/api/products/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    product = Product.query.get_or_404(product_id)
    data = request.json
    
    product.name = data.get('name', product.name)
    product.description = data.get('description', product.description)
    product.price = data.get('price', product.price)
    product.active = data.get('active', product.active)
    
    db.session.commit()
    return jsonify({'message': 'Product updated'})

@app.route('/api/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    return jsonify({'message': 'Product deleted'})

@app.route('/api/products/bulk-delete', methods=['DELETE'])
def bulk_delete_products():
    Product.query.delete()
    db.session.commit()
    return jsonify({'message': 'All products deleted'})

@app.route('/api/upload', methods=['POST'])
def upload_csv():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if not file.filename.endswith('.csv'):
        return jsonify({'error': 'Only CSV files allowed'}), 400
    
    file_content = file.read().decode('utf-8')
    upload_id = f"upload_{datetime.utcnow().timestamp()}"
    
    progress = UploadProgress(id=upload_id, status='pending')
    db.session.add(progress)
    db.session.commit()
    
    process_csv_upload.delay(file_content, upload_id)
    
    return jsonify({'upload_id': upload_id})

@app.route('/api/upload/<upload_id>/progress', methods=['GET'])
def get_upload_progress(upload_id):
    progress = UploadProgress.query.get_or_404(upload_id)
    percentage = 0
    if progress.total_rows > 0:
        percentage = int((progress.processed_rows / progress.total_rows) * 100)
    
    return jsonify({
        'status': progress.status,
        'total': progress.total_rows,
        'processed': progress.processed_rows,
        'percentage': percentage,
        'error': progress.error_message
    })

@app.route('/api/webhooks', methods=['GET'])
def get_webhooks():
    webhooks = Webhook.query.all()
    return jsonify([{
        'id': w.id,
        'url': w.url,
        'event_type': w.event_type,
        'enabled': w.enabled
    } for w in webhooks])

@app.route('/api/webhooks', methods=['POST'])
def create_webhook():
    data = request.json
    webhook = Webhook(
        url=data.get('url'),
        event_type=data.get('event_type'),
        enabled=data.get('enabled', True)
    )
    db.session.add(webhook)
    db.session.commit()
    return jsonify({'id': webhook.id, 'message': 'Webhook created'}), 201

@app.route('/api/webhooks/<int:webhook_id>', methods=['PUT'])
def update_webhook(webhook_id):
    webhook = Webhook.query.get_or_404(webhook_id)
    data = request.json
    
    webhook.url = data.get('url', webhook.url)
    webhook.event_type = data.get('event_type', webhook.event_type)
    webhook.enabled = data.get('enabled', webhook.enabled)
    
    db.session.commit()
    return jsonify({'message': 'Webhook updated'})

@app.route('/api/webhooks/<int:webhook_id>', methods=['DELETE'])
def delete_webhook(webhook_id):
    webhook = Webhook.query.get_or_404(webhook_id)
    db.session.delete(webhook)
    db.session.commit()
    return jsonify({'message': 'Webhook deleted'})

@app.route('/api/webhooks/<int:webhook_id>/test', methods=['POST'])
def test_webhook(webhook_id):
    import requests
    webhook = Webhook.query.get_or_404(webhook_id)
    
    try:
        start_time = datetime.utcnow()
        response = requests.post(webhook.url, json={'test': True}, timeout=5)
        end_time = datetime.utcnow()
        response_time = (end_time - start_time).total_seconds()
        
        return jsonify({
            'success': True,
            'status_code': response.status_code,
            'response_time': response_time
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# if __name__ == '__main__':
#     with app.app_context():
#         db.create_all()
#     app.run(debug=True)

if __name__ == '__main__':
    # Auto-create database if not exists
    from sqlalchemy import create_engine
    from sqlalchemy_utils import database_exists, create_database
    
    engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'])
    if not database_exists(engine.url):
        create_database(engine.url)
    
    with app.app_context():
        db.create_all()
    app.run(debug=True)