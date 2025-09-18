# Beauty Chatbot Systems

AI-powered chatbots for beauty salon businesses built with Flask, OpenAI GPT-4, and Redis.

## 🏢 Business Systems

### WAX! Baby Chatbot
- **Service**: Waxing and laser treatments
- **Language**: German (primary), English support
- **Features**: Service information, booking assistance, pricing, location help
- **Port**: 8000

### EUNOIA Urban Beauty Chatbot
- **Service**: Comprehensive beauty treatments
- **Language**: German (primary), English support
- **Features**: Treatment info, appointment booking, FAQ support
- **Port**: 8001

## 🚀 Production Deployment

**Server**: `chat.wax-baby.one`
**Management**: Systemd services
**Security**: Secure environment files (no .env in repo)

### Services
```bash
# WAX! Baby
systemctl status gunicorn-wax
systemctl start gunicorn-wax
systemctl restart gunicorn-wax

# EUNOIA
systemctl status gunicorn-eunoia
systemctl start gunicorn-eunoia
systemctl restart gunicorn-eunoia
```

### Environment Setup
Credentials managed via systemd environment file:
- `/etc/systemd/system/chatbot.env` (production only)
- Contains: `OPENAI_API_KEY`, `WAXBABY_API_KEY`, `EUNOIA_API_KEY`

## 🔧 Development Workflow

### Local Development Setup
```bash
# 1. Clone repository
git clone https://github.com/oichtental/beauty-chatbots.git
cd beauty-chatbots

# 2. Set up environment
cp .env.example .env
# Edit .env with your API keys

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run locally
python wax-baby-chatbot_api.py    # WAX! Baby on localhost:8000
python eunoia/chatbot_api.py      # EUNOIA on localhost:8001
```

### Deployment to Production
```bash
# After making changes and testing locally:
git add .
git commit -m "Your changes"
git push

# Deploy to production server
./deploy.sh
```

**Deployment Flow:**
1. 🔧 Develop locally with `.env` file
2. 🧪 Test changes locally
3. 📤 Commit to GitHub
4. 🚀 Deploy to production with `./deploy.sh`
5. ✅ Automatic backup, restart, and health check

## 🏗️ Architecture

- **Framework**: Flask + Gunicorn
- **AI**: OpenAI GPT-4
- **Cache**: Redis (business data, user sessions)
- **Features**: Multi-language, context memory, business data integration

## 📊 Features

- **Smart Conversations**: Context-aware responses with user memory
- **Business Integration**: Real-time service data from APIs
- **Multi-language**: Automatic language detection and switching
- **Public Transport**: Location-based transit information
- **Service Recommendations**: AI-powered treatment suggestions

## 🔒 Security

- ✅ Secure credential management via systemd
- ✅ No API keys in repository
- ✅ Production environment isolation
- ✅ Proper file permissions and access controls

## 📝 Development Status

**Status**: ✅ Production Ready
- Both chatbots operational and stable
- Secure deployment with proper credential management
- Regular monitoring and health checks
- Automated service management via systemd

---

*Generated with Claude Code - Daily Automation System Integration*