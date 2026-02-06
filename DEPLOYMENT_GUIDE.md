# AWS Deployment Guide for P2P CAS System

## Deployment Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         AWS Cloud                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  │   EC2 Instance   │  │   EC2 Instance   │  │   EC2 Instance   │
│  │   (Node 1)       │  │   (Node 2)       │  │   (Node 3)       │
│  │  Port 9000       │  │  Port 9000       │  │  Port 9000       │
│  │  DHT 8468        │  │  DHT 8469        │  │  DHT 8470        │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘
│         ↑                    ↑                      ↑
│         └────────────────────┼──────────────────────┘
│                 P2P Network (DHT + TCP)
│
│  Storage: EBS Volume (shared or replicated)
│           └─ storage/hashed_files/
│              └─ cas_index.json
│
│  Database (Optional): RDS for metadata
│
└─────────────────────────────────────────────────────────────────┘

Local Machine (Your Computer)
┌──────────────────────────────────────┐
│  Development & Management            │
├──────────────────────────────────────┤
│  - main.py (store files locally)     │
│  - download_file.py (test downloads) │
│  - Configuration files               │
│  - Local copy of source code         │
│  - Logs & monitoring tools           │
└──────────────────────────────────────┘
```

---

## Option 1: EC2 Deployment (Simple - Recommended for Learning)

### What to Upload to AWS EC2:

**Required on Server:**
```
p2p-cas-research/
├── src/                          # Core source code (REQUIRED)
│   ├── cas/                      # Chunking & erasure coding
│   ├── dht/                      # DHT implementation
│   └── network/                  # P2P node code
├── run_node.py                   # Node startup script (REQUIRED)
├── requirements.txt              # Python dependencies (REQUIRED)
├── storage/                      # CAS storage directory (REQUIRED)
│   └── hashed_files/             # Chunk storage
│       └── cas_index.json        # File index
├── .env                          # Configuration (create on server)
└── systemd/                      # Service files (create on server)
    └── p2p-node.service
```

**NOT needed on Server:**
```
❌ download_file.py              # Client only
❌ main.py                       # Local CAS management
❌ run_node1.py, run_node2.py, run_node3.py  # Local convenience scripts
❌ examples.py, COMPLETE_EXAMPLE.py          # Examples/docs
❌ *.md (documentation)           # Reference only
❌ test_files/                    # Local testing
```

### Step-by-Step EC2 Deployment:

#### **1. Create EC2 Instance**

```bash
# Use AWS Console or AWS CLI
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type t3.medium \
  --key-name your-key-pair \
  --security-groups p2p-cas-sg \
  --count 1
```

**Security Group Rules (Port Access):**
```
Inbound:
  - TCP 9000    (Chunk serving)      from 0.0.0.0/0
  - UDP 8468    (DHT)                from 0.0.0.0/0
  - SSH 22      (Management)         from YOUR_IP
```

#### **2. SSH into EC2 and Setup**

```bash
# Connect to instance
ssh -i your-key-pair.pem ec2-user@<EC2_PUBLIC_IP>

# Update system
sudo yum update -y

# Install Python 3.9+
sudo yum install python39 python39-pip git -y

# Create app directory
mkdir -p /opt/p2p-cas
cd /opt/p2p-cas

# Clone/upload your project
git clone https://github.com/your-username/p2p-cas-research.git .
# OR: scp -r -i your-key.pem local/p2p-cas-research/* ec2-user@IP:/opt/p2p-cas/

# Install dependencies
pip install -r requirements.txt

# Create storage directory
mkdir -p storage/hashed_files
chmod 755 storage
```

#### **3. Configure Environment Variables**

Create `/opt/p2p-cas/.env`:
```bash
# Node configuration
NODE_ID=aws-node-1
DHT_PORT=8468
SERVE_PORT=9000
STORAGE_DIR=/opt/p2p-cas/storage/hashed_files

# Bootstrap nodes (for multi-region setup)
BOOTSTRAP_NODES=52.1.2.3:8468,52.4.5.6:8468

# Logging
LOG_LEVEL=INFO
LOG_FILE=/var/log/p2p-cas/node.log
```

#### **4. Create Systemd Service**

Create `/etc/systemd/system/p2p-node.service`:
```ini
[Unit]
Description=P2P CAS Node
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/opt/p2p-cas
Environment="PATH=/usr/local/bin:/usr/bin"
EnvironmentFile=/opt/p2p-cas/.env
ExecStart=/usr/bin/python3 run_node.py --node-id %i --dht-port %i --serve-port 9000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### **5. Start Service**

```bash
# Reload systemd
sudo systemctl daemon-reload

# Start node
sudo systemctl start p2p-node

# Enable auto-start on reboot
sudo systemctl enable p2p-node

# Check status
sudo systemctl status p2p-node

# View logs
sudo journalctl -u p2p-node -f
```

#### **6. Test Node is Running**

```bash
# From another terminal, test connection
python download_file.py <file_hash> --server ec2_public_ip
```

---

## Option 2: Docker Deployment (Scalable - Recommended for Production)

### Docker Setup:

#### **1. Create Dockerfile**

Create `Dockerfile` in project root:
```dockerfile
FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY run_node.py .

# Create storage directory
RUN mkdir -p storage/hashed_files

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import socket; socket.create_connection(('127.0.0.1', 8468), timeout=2)"

# Run node (override at runtime)
CMD ["python", "run_node.py", "--node-id", "docker-node", "--dht-port", "8468", "--serve-port", "9000"]
```

#### **2. Create docker-compose.yml**

```yaml
version: '3.8'

services:
  node1:
    build: .
    container_name: p2p-node-1
    ports:
      - "8468:8468/udp"  # DHT
      - "9000:9000/tcp"  # Serve
    environment:
      NODE_ID: node1
      DHT_PORT: 8468
      SERVE_PORT: 9000
    volumes:
      - node1_storage:/app/storage/hashed_files
    networks:
      - p2p-network
    restart: unless-stopped

  node2:
    build: .
    container_name: p2p-node-2
    ports:
      - "8469:8468/udp"
      - "9001:9000/tcp"
    environment:
      NODE_ID: node2
      DHT_PORT: 8468
      SERVE_PORT: 9000
      BOOTSTRAP_NODES: "node1:8468"
    volumes:
      - node2_storage:/app/storage/hashed_files
    networks:
      - p2p-network
    depends_on:
      - node1
    restart: unless-stopped

  node3:
    build: .
    container_name: p2p-node-3
    ports:
      - "8470:8468/udp"
      - "9002:9000/tcp"
    environment:
      NODE_ID: node3
      DHT_PORT: 8468
      SERVE_PORT: 9000
      BOOTSTRAP_NODES: "node1:8468"
    volumes:
      - node3_storage:/app/storage/hashed_files
    networks:
      - p2p-network
    depends_on:
      - node1
    restart: unless-stopped

volumes:
  node1_storage:
  node2_storage:
  node3_storage:

networks:
  p2p-network:
    driver: bridge
```

#### **3. Deploy to AWS ECS**

```bash
# Build image
docker build -t p2p-cas:latest .

# Tag for ECR
docker tag p2p-cas:latest 123456789.dkr.ecr.us-east-1.amazonaws.com/p2p-cas:latest

# Push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 123456789.dkr.ecr.us-east-1.amazonaws.com
docker push 123456789.dkr.ecr.us-east-1.amazonaws.com/p2p-cas:latest

# Create ECS task definition (AWS Console or CLI)
# Scale to multiple tasks, each becomes a P2P node
```

---

## Option 3: Auto-Scaling Deployment

### Architecture for Scaling:

```
┌─────────────────────────────────────────────┐
│  AWS Load Balancer (Optional)               │
│  (For client requests, not DHT)             │
└──────────────┬──────────────────────────────┘
               │
    ┌──────────┼──────────┐
    ↓          ↓          ↓
  Node1      Node2      Node3    ... NodeN
(Auto Scaling Group)
    │          │          │
    └──────────┼──────────┘
               ↓
        EBS/EFS Storage
      (Shared chunk storage)
```

**Setup:**
```bash
# 1. Create AMI from configured EC2 instance
# 2. Create Launch Template (uses AMI + startup script)
# 3. Create Auto Scaling Group (3-10 instances min/max)
# 4. Each instance runs: python run_node.py --node-id auto-$INSTANCE_ID
# 5. Instances auto-join DHT network via bootstrap node
# 6. Share storage via EBS Multi-Attach or EFS
```

---

## File Deployment Checklist

### **Upload to AWS:**
- ✅ `src/` (all subdirectories)
- ✅ `run_node.py`
- ✅ `requirements.txt`
- ✅ `storage/` directory (can be empty initially)
- ✅ `Dockerfile` (if using Docker)
- ✅ `.env` (create on server, not in repo)

### **Keep Locally (Your Machine):**
- ✅ `main.py` (for local CAS management)
- ✅ `download_file.py` (for testing)
- ✅ `*.md` documentation
- ✅ `examples.py`, `COMPLETE_EXAMPLE.py`
- ✅ `.git/` (version control)
- ✅ Local copy of everything for development

### **Do NOT Upload:**
- ❌ Virtual environment (`venv/`, `.venv/`)
- ❌ `__pycache__/`, `*.pyc`
- ❌ `.env` (create it on server)
- ❌ Large test files
- ❌ `downloads/` directory
- ❌ Logs

---

## Storage Options

### **Option A: EBS Volume (Simpler)**
```bash
# Each instance has own EBS volume
# Good for: Single region, moderate data
# Cost: Lower, pay for volume size
```

### **Option B: EFS (Network Shared)**
```bash
# Shared across all instances
# Good for: Multi-instance, file replication
# Cost: Higher, pay for usage

# Mount on EC2:
sudo mount -t nfs4 -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2 \
  fs-12345678.efs.us-east-1.amazonaws.com:/ /mnt/efs
```

### **Option C: S3 (Cloud Storage)**
```bash
# Store chunks in S3 instead of local disk
# Good for: Archive, redundancy, multi-region
# Cost: Higher per-request

# Modify to use S3:
# Replace: os.path.join(storage_dir, chunk_hash)
# With: s3_client.get_object(Bucket='p2p-cas', Key=chunk_hash)
```

---

## Networking Configuration

### **Multi-Region Setup:**

```
Region 1 (us-east-1)          Region 2 (eu-west-1)
┌─────────────────┐           ┌─────────────────┐
│  Node 1         │           │  Node 4         │
│  Node 2         │◄──────────┤  Node 5         │
│  Node 3         │           │  Node 6         │
└─────────────────┘           └─────────────────┘
     ↓                             ↓
  Storage1                      Storage2
(Replicate via AWS DataSync)
```

**Setup:**
```bash
# Each region has bootstrap node
BOOTSTRAP_NODES="
  52.1.2.3:8468,        # us-east-1
  eu52.1.2.3:8468       # eu-west-1
"
```

---

## Security Best Practices

### **Security Groups:**
```
Inbound Rules:
  - TCP 9000  from 0.0.0.0/0 (Chunk serving - public)
  - UDP 8468  from 0.0.0.0/0 (DHT - public)
  - SSH 22    from YOUR_IP_ONLY (Private)

Outbound:
  - All (allow any)
```

### **IAM Roles:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::p2p-cas/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "*"
    }
  ]
}
```

### **Encryption:**
```bash
# EBS encryption (at rest)
aws ec2 create-volume --encrypted --size 100 --availability-zone us-east-1a

# SSL/TLS for chunk transfers (optional)
# Modify p2p_node.py to use SSL sockets
```

---

## Monitoring & Logging

### **CloudWatch Logs:**
```bash
# Install CloudWatch agent on EC2
wget https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/amd64/latest/amazon-cloudwatch-agent.rpm
sudo rpm -U ./amazon-cloudwatch-agent.rpm

# Configure to send logs:
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -s \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
```

### **Metrics to Monitor:**
```
- Network in/out (Mbps)
- Chunk upload/download count
- DHT query latency
- Storage usage (GB)
- Node uptime
- Active connections
```

---

## Cost Estimation

### **Option 1: EC2 Standalone**
```
3 x t3.medium (EC2):    $0.0416/hr × 3 = $0.125/hr
3 x 100GB EBS:          $10/month × 3 = $30/month
Data transfer:          ~$0.02/GB

Monthly: ~$90-150
```

### **Option 2: Docker on ECS**
```
3 x t3.medium (ECS):    $0.0416/hr × 3 = $0.125/hr
ECS task overhead:      ~$10/month
EBS + Data transfer:    ~$40/month

Monthly: ~$100-150
```

### **Option 3: Auto-Scaling (6 instances):**
```
6 x t3.small (EC2):     $0.0208/hr × 6 = $0.125/hr
EFS storage:            ~$0.30/GB/month
Data transfer:          ~$0.02/GB

Monthly: ~$150-250
```

---

## Deployment Commands Summary

### **Quick Deploy (EC2):**
```bash
# 1. Create EC2 instance with t3.medium, Ubuntu 20.04
# 2. SSH in:
ssh -i key.pem ubuntu@<IP>

# 3. Clone and setup:
git clone https://github.com/your-repo/p2p-cas-research.git
cd p2p-cas-research
pip install -r requirements.txt
mkdir -p storage/hashed_files

# 4. Start node:
python run_node.py --node-id aws-node1 --dht-port 8468 --serve-port 9000

# 5. Test from local machine:
python download_file.py <hash> --server <EC2_IP>
```

### **Quick Deploy (Docker):**
```bash
# 1. On your machine:
docker build -t p2p-cas:latest .
docker run -p 8468:8468/udp -p 9000:9000/tcp p2p-cas:latest

# 2. Or use docker-compose:
docker-compose up -d

# 3. Or push to ECR and deploy on ECS (AWS Console)
```

---

## Rollback & Updates

### **Update Code:**
```bash
# SSH into EC2
ssh -i key.pem ec2-user@<IP>

# Pull latest code
cd /opt/p2p-cas
git pull origin main

# Restart service
sudo systemctl restart p2p-node

# Verify
sudo systemctl status p2p-node
```

### **Rollback:**
```bash
# Revert to previous version
git revert <commit>
git push origin main

# Auto-redeploy (via CI/CD)
```

---

## Recommended Deployment Path

### **For Testing/Learning:**
1. Use **EC2 (Single Instance)** with SSH access
2. Manual file upload via scp
3. Monitor via SSH terminal

### **For Small Deployment (3-5 nodes):**
1. Use **EC2 + Auto Scaling Group**
2. Deploy via script/terraform
3. Monitor via CloudWatch

### **For Production (10+ nodes, Multi-region):**
1. Use **Docker on ECS Fargate**
2. Auto-scaling with load balancer
3. Centralized logging + monitoring
4. Multi-region replication with S3

---

## Files Needed: Final Summary

### **On AWS Server:**
```
/opt/p2p-cas/
├── src/                    ✅ UPLOAD
├── run_node.py             ✅ UPLOAD
├── requirements.txt        ✅ UPLOAD
├── storage/                ✅ CREATE (empty)
├── .env                    ✅ CREATE on server
├── Dockerfile              ✅ UPLOAD (if using Docker)
└── docker-compose.yml      ✅ UPLOAD (if using Docker)
```

### **On Local Machine (Keep):**
```
p2p-cas-research/
├── src/                    ✅ KEEP (development)
├── main.py                 ✅ KEEP (local CAS)
├── download_file.py        ✅ KEEP (testing)
├── *.md                    ✅ KEEP (reference)
├── examples/               ✅ KEEP (learning)
└── .git/                   ✅ KEEP (version control)
```

### **Never Upload to Server:**
```
❌ .venv/
❌ __pycache__/
❌ *.pyc
❌ downloads/
❌ .env (create on server)
❌ Large test files
```

