# SubTranscribe Production Deployment Guide

## 🚀 Production-Ready Docker Setup

This guide will help you deploy SubTranscribe to production using Docker with enterprise-grade features.

## 📁 Files Overview

### Core Files
- **`Dockerfile`** - Multi-stage production build with security optimizations
- **`docker-compose.prod.yml`** - Production orchestration with scaling
- **`nginx.prod.conf`** - Production web server with SSL and security
- **`.dockerignore`** - Optimized build context

### Scripts
- **`deploy-prod.sh`** - Automated production deployment
- **`monitor-prod.sh`** - Health monitoring and maintenance

## 🔧 Production Features

### Security
- ✅ Non-root user execution
- ✅ Multi-stage build for minimal attack surface
- ✅ Security headers and SSL/TLS
- ✅ Rate limiting and DDoS protection
- ✅ Input validation and sanitization

### Performance
- ✅ Multi-replica scaling (3 instances)
- ✅ Load balancing with Nginx
- ✅ Redis caching
- ✅ Optimized Gunicorn configuration
- ✅ Health checks and monitoring

### Reliability
- ✅ Automatic restarts on failure
- ✅ Graceful shutdowns
- ✅ Resource limits and monitoring
- ✅ Database persistence
- ✅ Log aggregation

## 🚀 Quick Start

### 1. Prerequisites
```bash
# Install Docker and Docker Compose
# Ensure you have SSL certificates ready
```

### 2. Environment Setup
```bash
# Copy environment template
cp .env.prod.example .env.prod

# Edit with your actual values
nano .env.prod
```

### 3. Deploy to Production
```bash
# Run deployment script
./deploy-prod.sh

# Or manually:
docker-compose -f docker-compose.prod.yml up -d
```

### 4. Monitor Health
```bash
# Check status
./monitor-prod.sh

# View logs
docker-compose -f docker-compose.prod.yml logs -f
```

## 📊 Production Configuration

### Resource Limits
- **App**: 2GB RAM, 2 CPU cores per replica
- **Redis**: 512MB RAM, 0.5 CPU cores
- **MongoDB**: 1GB RAM, 1 CPU core
- **Nginx**: 256MB RAM, 0.5 CPU cores

### Scaling
- **App Replicas**: 3 instances
- **Load Balancing**: Round-robin with least connections
- **Auto-scaling**: Manual (can be automated with Kubernetes)

### Security
- **SSL/TLS**: TLS 1.2+ with modern ciphers
- **Rate Limiting**: 10 req/s API, 5 req/m auth, 2 req/s upload
- **Headers**: HSTS, CSP, XSS protection
- **Network**: Isolated Docker network

## 🔍 Monitoring

### Health Checks
- **App**: HTTP endpoint `/health`
- **Redis**: `redis-cli ping`
- **MongoDB**: `mongosh ping`
- **Nginx**: Built-in health check

### Metrics
- Container resource usage
- Request/response times
- Error rates and logs
- Database performance

### Alerts
- Unhealthy containers
- High error rates
- Resource exhaustion
- SSL certificate expiry

## 🛠️ Maintenance

### Updates
```bash
# Update application
git pull
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml up -d

# Update dependencies
docker-compose -f docker-compose.prod.yml pull
docker-compose -f docker-compose.prod.yml up -d
```

### Scaling
```bash
# Scale app instances
docker-compose -f docker-compose.prod.yml up --scale app=5

# Scale down
docker-compose -f docker-compose.prod.yml up --scale app=2
```

### Backup
```bash
# Backup MongoDB
docker-compose -f docker-compose.prod.yml exec mongodb mongodump --out /backup

# Backup Redis
docker-compose -f docker-compose.prod.yml exec redis redis-cli BGSAVE
```

## 🔒 Security Checklist

- [ ] Change default passwords
- [ ] Update SSL certificates
- [ ] Configure firewall rules
- [ ] Enable log monitoring
- [ ] Set up intrusion detection
- [ ] Regular security updates
- [ ] Backup encryption
- [ ] Access control

## 📈 Performance Optimization

### Database
- MongoDB indexing
- Redis memory optimization
- Connection pooling

### Application
- Gunicorn worker tuning
- Memory management
- Cache optimization

### Network
- CDN integration
- Compression
- Keep-alive connections

## 🆘 Troubleshooting

### Common Issues
1. **Container won't start**: Check logs and resource limits
2. **SSL errors**: Verify certificate paths and permissions
3. **Database connection**: Check MongoDB authentication
4. **High memory usage**: Monitor and adjust limits

### Debug Commands
```bash
# Check container logs
docker-compose -f docker-compose.prod.yml logs app

# Check resource usage
docker stats

# Check network connectivity
docker-compose -f docker-compose.prod.yml exec app curl localhost:8000/health
```

## 📞 Support

For production support:
- Check logs first: `docker-compose -f docker-compose.prod.yml logs`
- Monitor resources: `./monitor-prod.sh`
- Review configuration files
- Contact system administrator

---

**🎉 Your SubTranscribe application is now production-ready!**
