#!/bin/bash

# DigitalOcean Droplet Setup Script for NexFarm Backend
# Run this script on your droplet: sudo bash setup_droplet.sh

echo "🚀 Setting up NexFarm Backend on DigitalOcean Droplet..."

# Update system
echo "📦 Updating system packages..."
apt update && apt upgrade -y

# Install Python 3.12 and pip
echo "🐍 Installing Python 3.12..."
apt install software-properties-common -y
add-apt-repository ppa:deadsnakes/ppa -y
apt update
apt install python3.12 python3.12-venv python3.12-pip -y

# Install git
echo "📥 Installing Git..."
apt install git -y

# Install nginx
echo "🌐 Installing Nginx..."
apt install nginx -y

# Create directory and clone repository
echo "📁 Setting up application directory..."
cd /var/www
rm -rf crispy-rotary-phone 2>/dev/null
git clone https://github.com/chrispine6/crispy-rotary-phone.git
cd crispy-rotary-phone
git checkout ui-changes

# Create virtual environment
echo "🔧 Creating Python virtual environment..."
python3.12 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create environment file
echo "⚙️ Creating environment configuration..."
cp .env.example .env

# Update .env file with production values
cat > .env << EOF
MONGODB_URL=mongodb+srv://nexfarm_admin:sgFeiUpVjWwuv84W@cluster0.aicbbge.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0
DB_NAME=nexfarm_db
PYTHONPATH=/var/www/crispy-rotary-phone/src
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,https://oyster-app-btoc9.ondigitalocean.app/login
PORT=8000
ENVIRONMENT=production
EOF

# Run database migration
echo "🗄️ Running database migrations..."
python update_dealer_credit_limit.py

# Create systemd service
echo "⚙️ Creating systemd service..."
cat > /etc/systemd/system/nexfarm.service << EOF
[Unit]
Description=NexFarm FastAPI application
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/crispy-rotary-phone
Environment=PATH=/var/www/crispy-rotary-phone/venv/bin
Environment=PYTHONPATH=/var/www/crispy-rotary-phone/src
EnvironmentFile=/var/www/crispy-rotary-phone/.env
ExecStart=/var/www/crispy-rotary-phone/venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# Configure Nginx
echo "🌐 Configuring Nginx..."
cat > /etc/nginx/sites-available/nexfarm << EOF
server {
    listen 80;
    server_name 209.38.122.225;
    
    # API routes
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # CORS headers
        add_header Access-Control-Allow-Origin *;
        add_header Access-Control-Allow-Methods "GET, POST, OPTIONS, PUT, DELETE";
        add_header Access-Control-Allow-Headers "Content-Type, Authorization";
        
        # Handle preflight requests
        if (\$request_method = OPTIONS) {
            add_header Access-Control-Allow-Origin *;
            add_header Access-Control-Allow-Methods "GET, POST, OPTIONS, PUT, DELETE";
            add_header Access-Control-Allow-Headers "Content-Type, Authorization";
            return 204;
        }
    }
    
    # Health check and root
    location / {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# Enable nginx site
ln -sf /etc/nginx/sites-available/nexfarm /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test nginx configuration
nginx -t

# Set permissions
echo "🔐 Setting permissions..."
chown -R www-data:www-data /var/www/crispy-rotary-phone

# Start services
echo "🚀 Starting services..."
systemctl daemon-reload
systemctl enable nexfarm
systemctl start nexfarm
systemctl enable nginx
systemctl restart nginx

# Show status
echo "📊 Service Status:"
systemctl status nexfarm --no-pager
systemctl status nginx --no-pager

echo ""
echo "✅ Setup complete!"
echo ""
echo "🔗 Your API endpoints:"
echo "   Health Check: http://209.38.122.225/health"
echo "   API Base: http://209.38.122.225/api"
echo "   Admin Salesmen: http://209.38.122.225/api/orders/admin/salesmen"
echo ""
echo "📝 To check logs:"
echo "   Backend: sudo journalctl -u nexfarm -f"
echo "   Nginx: sudo tail -f /var/log/nginx/error.log"
echo ""
echo "🔄 To restart services:"
echo "   sudo systemctl restart nexfarm"
echo "   sudo systemctl restart nginx"
