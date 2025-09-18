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

## 🔧 Local Development

1. Clone repository
2. Install requirements: `pip install -r requirements.txt`
3. Create `.env` file with your API keys
4. Run: `python chatbot_api.py`

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