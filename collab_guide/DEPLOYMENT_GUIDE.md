# Self-Hosted Deployment Guide

Guide for deploying the collaborative workspace server to your own infrastructure.

## Prerequisites

- Linux server (Ubuntu 22.04 LTS recommended) or VM
- Node.js 20+ installed
- Git installed
- Domain name (optional but recommended)
- SSL certificate (for production wss://)

## Deployment Options

### Option A: Basic VM Deployment (Quickest)

**Best for:** Small teams, internal use, Phase 0 testing

#### 1. Prepare Your Server

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Node.js 20
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Install build tools
sudo apt install -y build-essential

# Install PM2 (process manager)
sudo npm install -g pm2
```

#### 2. Clone and Setup

```bash
# Clone your repo
git clone <your-repo-url>
cd withai-application/collab-server

# Install dependencies
npm install

# Build TypeScript
npm run build
```

#### 3. Configure Environment

```bash
# Create production .env
cat > .env << EOF
PORT=8080
HOST=0.0.0.0
ADMIN_TOKEN=$(openssl rand -hex 32)
WORKSPACE_ROOT=/var/lib/collab-workspace/workspaces
EOF

# Create storage directory
sudo mkdir -p /var/lib/collab-workspace/workspaces/ws_default/files
sudo chown -R $USER:$USER /var/lib/collab-workspace
```

#### 4. Start Server with PM2

```bash
# Start server
pm2 start dist/server.js --name collab-server

# Save PM2 configuration
pm2 save

# Setup PM2 to start on boot
pm2 startup
# Follow the command it outputs

# Check status
pm2 status
pm2 logs collab-server
```

#### 5. Configure Firewall

```bash
# Allow WebSocket port
sudo ufw allow 8080/tcp
sudo ufw enable
```

#### 6. Access from Clients

In VS Code settings:
```json
{
  "collabWorkspace.serverUrl": "ws://YOUR_SERVER_IP:8080",
  "collabWorkspace.workspaceId": "ws_default",
  "collabWorkspace.token": "YOUR_ADMIN_TOKEN_FROM_ENV"
}
```

---

### Option B: Docker Deployment (Recommended)

**Best for:** Easy deployment, portability, isolation

#### 1. Create Dockerfile

Create `collab-server/Dockerfile`:

```dockerfile
FROM node:20-alpine

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci --only=production

# Copy source and build
COPY . .
RUN npm run build

# Create storage directory
RUN mkdir -p /data/workspaces

# Expose port
EXPOSE 8080

# Start server
CMD ["node", "dist/server.js"]
```

#### 2. Create Docker Compose

Create `collab-server/docker-compose.yml`:

```yaml
version: '3.8'

services:
  collab-server:
    build: .
    container_name: collab-server
    ports:
      - "8080:8080"
    volumes:
      - ./storage:/app/storage
      - ./data:/data
    environment:
      - PORT=8080
      - HOST=0.0.0.0
      - ADMIN_TOKEN=${ADMIN_TOKEN}
      - WORKSPACE_ROOT=/data/workspaces
    restart: unless-stopped
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

volumes:
  data:
```

#### 3. Deploy

```bash
cd collab-server

# Generate secure token
export ADMIN_TOKEN=$(openssl rand -hex 32)
echo "ADMIN_TOKEN=$ADMIN_TOKEN" > .env.prod

# Build and start
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

---

### Option C: Reverse Proxy with HTTPS (Production-Ready)

**Best for:** Production use, multiple clients, security

#### Setup Nginx + Let's Encrypt

**1. Install Nginx**

```bash
sudo apt install nginx certbot python3-certbot-nginx -y
```

**2. Configure Nginx for WebSocket**

Create `/etc/nginx/sites-available/collab-workspace`:

```nginx
# HTTP redirect to HTTPS
server {
    listen 80;
    server_name workspace.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS + WebSocket
server {
    listen 443 ssl http2;
    server_name workspace.yourdomain.com;

    # SSL certificates (Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/workspace.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/workspace.yourdomain.com/privkey.pem;

    # WebSocket proxying
    location / {
        proxy_pass http://localhost:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket timeout
        proxy_read_timeout 86400;
    }
}
```

**3. Enable Site and Get SSL**

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/collab-workspace /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Get SSL certificate
sudo certbot --nginx -d workspace.yourdomain.com

# Auto-renewal is setup automatically by certbot
```

**4. Update Client Configuration**

```json
{
  "collabWorkspace.serverUrl": "wss://workspace.yourdomain.com",
  "collabWorkspace.workspaceId": "ws_default",
  "collabWorkspace.token": "your-secure-token"
}
```

---

## Security Hardening

### 1. Change Default Token

```bash
# Generate strong token
openssl rand -hex 32

# Update .env
ADMIN_TOKEN=your-new-secure-token-here
```

### 2. Restrict Access by IP (Optional)

In nginx config:
```nginx
location / {
    allow 192.168.1.0/24;  # Your office network
    deny all;

    proxy_pass http://localhost:8080;
    # ... rest of config
}
```

### 3. Enable Firewall

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### 4. Setup Automated Backups

```bash
# Create backup script
cat > /usr/local/bin/backup-collab-workspace.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/backups/collab-workspace"
WORKSPACE_DIR="/var/lib/collab-workspace/workspaces"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR
tar -czf $BACKUP_DIR/workspace_$DATE.tar.gz $WORKSPACE_DIR

# Keep only last 7 days
find $BACKUP_DIR -name "workspace_*.tar.gz" -mtime +7 -delete
EOF

chmod +x /usr/local/bin/backup-collab-workspace.sh

# Add to crontab (daily at 2am)
(crontab -l 2>/dev/null; echo "0 2 * * * /usr/local/bin/backup-collab-workspace.sh") | crontab -
```

---

## Monitoring

### View Logs

**PM2:**
```bash
pm2 logs collab-server
pm2 monit
```

**Docker:**
```bash
docker-compose logs -f
```

**System:**
```bash
journalctl -u collab-server -f
```

### Health Checks

Create a simple health check endpoint (add to server later):

```bash
# Check if server is responding
curl -I http://localhost:8080
```

---

## Scaling Considerations

### Current Limitations (Phase 0)

- Single server instance
- In-memory session storage
- No horizontal scaling

### Future Improvements (Phase 1)

- Move sessions to Redis
- Load balance across multiple instances
- Move files to S3/object storage
- Add PostgreSQL for metadata

---

## Troubleshooting

### Server Won't Start

```bash
# Check logs
pm2 logs collab-server

# Check port availability
sudo lsof -i :8080

# Check permissions
ls -la /var/lib/collab-workspace
```

### Clients Can't Connect

```bash
# Test WebSocket connection
wscat -c ws://YOUR_SERVER_IP:8080

# Check firewall
sudo ufw status

# Check if server is listening
sudo netstat -tulpn | grep 8080
```

### Performance Issues

```bash
# Check resource usage
pm2 monit

# Check disk space
df -h

# Check memory
free -h
```

---

## Maintenance

### Update Server

```bash
cd withai-application
git pull
cd collab-server
npm install
npm run build
pm2 restart collab-server
```

### Rotate Logs

PM2 handles this automatically, but you can configure:

```bash
pm2 install pm2-logrotate
pm2 set pm2-logrotate:max_size 10M
pm2 set pm2-logrotate:retain 7
```

---

## Cost Estimates

### Self-Hosted Options

**Option 1: Home Server / Office Server**
- Cost: $0 (use existing hardware)
- Good for: Small teams, internal use

**Option 2: VPS (DigitalOcean, Linode, Vultr)**
- Cost: $6-12/month (Basic droplet)
- CPU: 1-2 cores
- RAM: 1-2GB
- Storage: 25-50GB
- Good for: Small-medium teams (5-20 users)

**Option 3: Cloud VM (AWS EC2, Azure, GCP)**
- Cost: $10-30/month (t3.small - t3.medium)
- Good for: Production use, need reliability

**Option 4: Dedicated Server**
- Cost: $30-100/month
- Good for: Large teams, high performance needs

---

## Next Steps After Deployment

1. **Test from multiple clients**
   - Connect from different machines
   - Verify file locking works
   - Test concurrent edits

2. **Setup monitoring**
   - Use PM2 monitoring
   - Setup alerts for downtime
   - Monitor disk space

3. **Create backups**
   - Automate workspace backups
   - Test restore process

4. **Document for your team**
   - Connection instructions
   - Token distribution
   - Support contact

5. **Plan for Phase 1**
   - User accounts
   - PostgreSQL migration
   - Better authentication

---

## Support

For issues with deployment:
1. Check logs first
2. Review this guide
3. Check [PROJECT_BRIEF.md](PROJECT_BRIEF.md) for architecture details
4. Review [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
